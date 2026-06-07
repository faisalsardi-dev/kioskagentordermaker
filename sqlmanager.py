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

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent / "kioskorders.db"


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
                code, redeemed, user_email
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, 'unassigned', ?)
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


def mark_redeemed(code: str) -> bool:
    """Flip redeemed to 'true' for the row carrying this code.

    Called by /redeem when a code is successfully plugged in at the landing
    page. Returns True if a matching row was updated.
    """
    conn = get_connection()
    try:
        cur = conn.execute(
            "UPDATE orders SET redeemed = 'true' WHERE code = ?",
            (code,),
        )
        conn.commit()
        return cur.rowcount > 0
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
    email: str, password_hash: str, nickname: str | None = None
) -> bool:
    """Insert a new user. Returns True on success.

    Returns False (does not raise) if the email already exists.
    """
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO users (
                email, password_hash, nickname, created_at, email_verified
            ) VALUES (?, ?, ?, ?, 0)
            """,
            (email, password_hash, nickname, _now_iso()),
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