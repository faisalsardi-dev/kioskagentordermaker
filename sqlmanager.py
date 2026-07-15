"""SQLite storage for AI-order eval/analytics data.

One row per "readback" — every time the agent assembles an order and asks
the user "lock this in?". The row captures the full turn (question, reply,
metrics, assembled cart). A code is stamped on later when the user confirms
and finalize_order runs; `redeemed` flips to 'true' if that code is ever
plugged in at the landing page.

Lifecycle of a row:
  1. readback turn        -> insert_readback()  (code=NULL, redeemed='unassigned')
  2. user confirms (yes)  -> stamp_code()       (sets code on latest code-less row)
  3. code redeemed        -> mark_redeemed()    (redeemed='true' WHERE code=?)

All timestamps are ISO-8601 strings (SQLite has no native datetime type;
ISO strings sort chronologically and are unambiguous).
"""

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(os.getenv("KIOSK_DB_PATH", str(Path(__file__).parent / "kioskorders.db")))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_connection() -> sqlite3.Connection:
    """Open a connection. Row factory gives dict-like access by column name."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create the orders table if it doesn't exist. Safe to call on startup."""
    conn = get_connection()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS orders (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at        TEXT    NOT NULL,
                user_message      TEXT    NOT NULL,
                assistant_reply   TEXT    NOT NULL,
                order_json        TEXT    NOT NULL,
                prompt_tokens     INTEGER NOT NULL DEFAULT 0,
                completion_tokens INTEGER NOT NULL DEFAULT 0,
                loop_count        INTEGER NOT NULL DEFAULT 0,
                wall_clock_ms     INTEGER NOT NULL DEFAULT 0,
                code              TEXT,
                redeemed          TEXT    NOT NULL DEFAULT 'unassigned',
                user_email        TEXT,
                FLAG              TEXT
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def insert_readback(
    user_message: str,
    assistant_reply: str,
    order_json: str,
    prompt_tokens: int,
    completion_tokens: int,
    loop_count: int,
    wall_clock_ms: int,
    user_email: str | None = None,
    flag: str | None = None,
) -> int:
    """Write one readback row. Returns the new row id.

    Called by mainfast.py when a turn is detected as a readback (the agent
    called view_order and ended the turn in plain text).
    """
    conn = get_connection()
    try:
        cur = conn.execute(
            """
            INSERT INTO orders (
                created_at, user_message, assistant_reply, order_json,
                prompt_tokens, completion_tokens, loop_count, wall_clock_ms,
                code, redeemed, user_email, FLAG
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, 'unassigned', ?, ?)
            """,
            (
                _now_iso(),
                user_message,
                assistant_reply,
                order_json,
                prompt_tokens,
                completion_tokens,
                loop_count,
                wall_clock_ms,
                user_email,
                flag,
            ),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def stamp_code(code: str) -> bool:
    """Attach a finalize code to the most recent readback row that has none.

    Called right after finalize_order generates a code. The latest code-less
    row is the one the user just confirmed. Returns True if a row was stamped.
    """
    conn = get_connection()
    try:
        cur = conn.execute(
            """
            UPDATE orders
            SET code = ?
            WHERE id = (
                SELECT id FROM orders
                WHERE code IS NULL
                ORDER BY id DESC
                LIMIT 1
            )
            """,
            (code,),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def mark_redeemed(code: str, user_email: str | None = None) -> bool:
    """Flip redeemed to 'true' for the row carrying this code.

    If user_email is given (a logged-in user redeemed), also stamp it on the
    row — this is the moment an order becomes attributable to a user, which
    is what "your last order" reads back. Anonymous redeems pass None and
    leave user_email untouched. Returns True if a matching row was updated.
    """
    conn = get_connection()
    try:
        if user_email is None:
            cur = conn.execute(
                "UPDATE orders SET redeemed = 'true' WHERE code = ?",
                (code,),
            )
        else:
            cur = conn.execute(
                "UPDATE orders SET redeemed = 'true', user_email = ? WHERE code = ?",
                (user_email, code),
            )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def get_last_redeemed_order(user_email: str) -> dict | None:
    """Return this user's most recent redeemed order, or None.

    "Last order" = the newest row attributable to the user (user_email set)
    that actually reached redemption (redeemed='true'). Built-but-abandoned
    orders don't count. Returns the row as a dict (order_json is still a
    JSON string — the caller parses it); None if the user has none.
    """
    conn = get_connection()
    try:
        row = conn.execute(
            """
            SELECT * FROM orders
            WHERE user_email = ? AND redeemed = 'true'
            ORDER BY id DESC
            LIMIT 1
            """,
            (user_email,),
        ).fetchone()
        return dict(row) if row is not None else None
    finally:
        conn.close()


def set_flag(row_id: int, value: str | None) -> bool:
    """Set (or clear) the freeform flag on a row by id.

    The flag is a joker column for marking rows during analysis —
    e.g. 'out_of_scope', 'gate_slip', whatever scheme you land on.
    Pass None to clear it. Returns True if a row was updated.
    """
    conn = get_connection()
    try:
        cur = conn.execute(
            "UPDATE orders SET FLAG = ? WHERE id = ?",
            (value, row_id),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def init_users_table() -> None:
    """Create the users table if it doesn't exist. Safe to call on startup."""
    conn = get_connection()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                email             TEXT PRIMARY KEY,
                password_hash     TEXT NOT NULL,
                nickname          TEXT,
                created_at        TEXT NOT NULL,
                email_verified    INTEGER NOT NULL DEFAULT 0,
                verification_code TEXT,
                code_expires_at   TEXT
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def create_user(
    email: str,
    password_hash: str,
    nickname: str | None = None,
    verification_code: str | None = None,
    code_expires_at: str | None = None,
) -> bool:
    """Insert a new user. Returns True on success.

    Returns False (does not raise) if the email already exists.
    `verification_code` / `code_expires_at` are written as-is; the caller
    (the route) generates them and owns their format/TTL policy.
    """
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO users (
                email, password_hash, nickname, created_at, email_verified,
                verification_code, code_expires_at
            ) VALUES (?, ?, ?, ?, 0, ?, ?)
            """,
            (
                email,
                password_hash,
                nickname,
                _now_iso(),
                verification_code,
                code_expires_at,
            ),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def get_user(email: str) -> dict | None:
    """Look up a user by email. Returns the row as a dict, or None."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM users WHERE email = ?",
            (email,),
        ).fetchone()
        return dict(row) if row is not None else None
    finally:
        conn.close()
    

def verify_user(email: str, code: str) -> bool:
    """Verify a user's email by matching the stored 6-digit code.

    Returns True only if: the user exists, has a stored verification_code
    equal to `code`, and code_expires_at is still in the future. On success,
    sets email_verified=1 and clears the code columns. Any failure -> False.
    """
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT verification_code, code_expires_at FROM users WHERE email = ?",
            (email,),
        ).fetchone()

        if row is None:
            return False
        stored_code = row["verification_code"]
        expires_at = row["code_expires_at"]
        if not stored_code or not expires_at:
            return False
        if stored_code != code:
            return False
        if datetime.fromisoformat(expires_at) < datetime.now(timezone.utc):
            return False

        conn.execute(
            """
            UPDATE users
            SET email_verified = 1,
                verification_code = NULL,
                code_expires_at = NULL
            WHERE email = ?
            """,
            (email,),
        )
        conn.commit()
        return True
    finally:
        conn.close()


def set_nickname(email: str, nickname: str) -> bool:
    """Update the nickname for an existing user. Returns True if a row was updated."""
    conn = get_connection()
    try:
        cur = conn.execute(
            "UPDATE users SET nickname = ? WHERE email = ?",
            (nickname, email),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


# ============================================================================
# MCP layer: per-user bearer tokens + one row per MCP tool call.
#
# The MCP server (mcpserver.py) is a second front door for registered users to
# build orders with their own LLM. It reuses the code-redemption bridge but has
# its OWN analytics table (mcp_calls) — it never writes to `orders` and never
# calls stamp_code(). Auth is a per-user static bearer token; we store only its
# sha256 hex in users.mcp_token_hash (NULL = no MCP access).
# ============================================================================


def init_mcp_table() -> None:
    """Create the mcp_calls table if it doesn't exist. Safe to call on startup.

    One row per MCP tool call (view_menu or place_order). `code` is set only on
    a successful place_order; `redeemed` flips to 1 when that code is plugged in
    at the kiosk (mark_mcp_redeemed).
    """
    conn = get_connection()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS mcp_calls (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at        TEXT    NOT NULL,
                user_email        TEXT    NOT NULL,
                tool              TEXT    NOT NULL,
                args_json         TEXT,
                ok                INTEGER NOT NULL,
                error_or_summary  TEXT,
                code              TEXT,
                wall_clock_ms     INTEGER,
                redeemed          INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def migrate_users_add_mcp_token() -> None:
    """Add users.mcp_token_hash if missing. Idempotent — safe on every startup.

    SQLite has no 'ADD COLUMN IF NOT EXISTS', so we probe PRAGMA table_info
    first; a bare ALTER would raise on the second run and crash the droplet.
    """
    conn = get_connection()
    try:
        cols = [row["name"] for row in conn.execute("PRAGMA table_info(users)")]
        if "mcp_token_hash" not in cols:
            conn.execute("ALTER TABLE users ADD COLUMN mcp_token_hash TEXT")
            conn.commit()
    finally:
        conn.close()


def set_mcp_token_hash(email: str, token_hash: str | None) -> bool:
    """Set (or clear) a user's MCP token hash. Pass None to revoke.

    Returns True if a row was updated. Regenerating overwrites the old hash,
    which invalidates the previous token.
    """
    conn = get_connection()
    try:
        cur = conn.execute(
            "UPDATE users SET mcp_token_hash = ? WHERE email = ?",
            (token_hash, email),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def get_user_by_mcp_token_hash(token_hash: str) -> dict | None:
    """Look up a user by their MCP token hash. Returns the row dict, or None.

    NULL hashes never match (SQLite '= NULL' is never true), so revoked or
    never-provisioned users can't authenticate.
    """
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM users WHERE mcp_token_hash = ?",
            (token_hash,),
        ).fetchone()
        return dict(row) if row is not None else None
    finally:
        conn.close()


def insert_mcp_call(
    user_email: str,
    tool: str,
    args_json: str | None,
    ok: int,
    error_or_summary: str | None,
    code: str | None,
    wall_clock_ms: int | None,
) -> int:
    """Write one mcp_calls row. Returns the new row id."""
    conn = get_connection()
    try:
        cur = conn.execute(
            """
            INSERT INTO mcp_calls (
                created_at, user_email, tool, args_json, ok,
                error_or_summary, code, wall_clock_ms, redeemed
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
            """,
            (
                _now_iso(),
                user_email,
                tool,
                args_json,
                ok,
                error_or_summary,
                code,
                wall_clock_ms,
            ),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_mcp_calls(email: str, limit: int = 20) -> list[dict]:
    """Return this user's most recent MCP tool calls, newest first."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT * FROM mcp_calls
            WHERE user_email = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (email, limit),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def mark_mcp_redeemed(code: str, user_email: str | None = None) -> bool:
    """Flip redeemed=1 on the mcp_calls row carrying this code.

    Matches on the (unique) code; user_email is accepted for signature parity
    with mark_redeemed but isn't needed to find the row. No-op if no MCP row
    holds the code (e.g. the code came from the /orderai flow). Returns True if
    a row was updated.
    """
    conn = get_connection()
    try:
        cur = conn.execute(
            "UPDATE mcp_calls SET redeemed = 1 WHERE code = ?",
            (code,),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()