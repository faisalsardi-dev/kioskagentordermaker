"""User-facing MCP server: a second front door for registered users.

A registered user mints a bearer token on the settings page and connects their
own MCP client (target: Claude Code). Their LLM calls two tools — view_menu and
place_order — and place_order returns a 4-hex pickup code redeemable at the
kiosk, reusing the same PENDING_ORDERS bridge the /orderai flow uses.

Stateless by design: no cart, no sessions. The client's LLM composes the order
from view_menu output; place_order is atomic (build the whole Order in one call,
reject on any error — never clamp). Identity is resolved by BearerAuthMiddleware
and passed to the tools via a ContextVar (NOT a module-level global — HTTP
requests interleave and a global would let one user's identity leak into
another's tool call).

This module must NOT import mainfast (mainfast imports it). It loads the menu
itself and talks to llmtools / sqlmanager / totaling / datapydentic.
"""

import hashlib
import json
import time
from contextvars import ContextVar
from pathlib import Path
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, TypeAdapter
from mcp.server.fastmcp import FastMCP

import llmtools
import sqlmanager
from datapydentic import Menu, Order
from llmtools import (
    PENDING_ORDERS,
    MCP_PENDING,
    CODE_TTL_SECONDS,
    _generate_unique_code,
    _reap_expired_pending,
    summarize_order_for_customer,
)
from totaling import price_order, TAX_RATE

ROOT = Path(__file__).parent
MENU_PATH = ROOT / "mcmenu.json"


def load_menu_dict() -> dict:
    with MENU_PATH.open() as f:
        return json.load(f)


def load_menu() -> Menu:
    """Load the menu fresh from disk. Mirrors mainfast.load_menu on purpose —
    importing it from mainfast would be a circular import (mainfast imports us)."""
    return Menu(**load_menu_dict())


# Identity for the in-flight MCP request, set by BearerAuthMiddleware before the
# tool runs and read by the tools. A ContextVar (not a global) so concurrent
# requests keep separate identities.
current_user_email: ContextVar[str] = ContextVar("current_user_email")


# ---------- place_order input schema ----------
# A tagged union mirroring datapydentic's OrderItem, discriminated by `type`.
# FastMCP builds the tool's JSON schema from this annotation.


class SandwichItemInput(BaseModel):
    type: Literal["sandwich"] = "sandwich"
    sandwich_id: str
    ingredients: dict[str, int] | None = None  # absolute counts; omit for defaults
    is_meal: bool = False
    meal_size_id: str | None = None  # 'S' | 'M' | 'L'
    meal_drink_type_id: str | None = None


class DrinkItemInput(BaseModel):
    type: Literal["drink"] = "drink"
    drink_type_id: str
    size_id: str  # 'S' | 'M' | 'L'


class WaterItemInput(BaseModel):
    type: Literal["water"] = "water"


class SauceItemInput(BaseModel):
    type: Literal["sauce"] = "sauce"
    sauce_id: str


class McCafeItemInput(BaseModel):
    type: Literal["mccafe"] = "mccafe"
    mccafe_id: str


OrderItemInput = Annotated[
    Union[
        SandwichItemInput,
        DrinkItemInput,
        WaterItemInput,
        SauceItemInput,
        McCafeItemInput,
    ],
    Field(discriminator="type"),
]

_ITEMS_ADAPTER = TypeAdapter(list[OrderItemInput])


# ---------- order building + busy check (importable, no network) ----------


def build_order_from_items(items, menu: Menu) -> tuple[Order | None, str]:
    """Build a fresh Order from tagged input items, reusing the llmtools add_*
    validators (min/max, unknown ids). Atomic: on the FIRST error return
    (None, error_string) — no partial orders. On success return (order, "").

    Accepts either the validated pydantic input models or plain dicts (the test
    passes models; a raw dict caller is coerced through the same union).
    """
    items = _ITEMS_ADAPTER.validate_python(items)
    order = Order()
    for item in items:
        if isinstance(item, SandwichItemInput):
            result = llmtools.add_sandwich(
                order, menu, item.sandwich_id, item.ingredients,
                item.is_meal, item.meal_size_id, item.meal_drink_type_id,
            )
        elif isinstance(item, DrinkItemInput):
            result = llmtools.add_drink(order, menu, item.drink_type_id, item.size_id)
        elif isinstance(item, WaterItemInput):
            result = llmtools.add_water(order, menu)
        elif isinstance(item, SauceItemInput):
            result = llmtools.add_sauce(order, menu, item.sauce_id)
        elif isinstance(item, McCafeItemInput):
            result = llmtools.add_mccafe(order, menu, item.mccafe_id)
        else:  # unreachable — the adapter only yields the union members
            return None, f"Error: unknown item type for {item!r}."
        if result.startswith("Error:"):
            return None, result
    return order, ""


def pending_code_for_user(email: str) -> tuple[str, int] | None:
    """If the user has a live pending code, return (code, seconds_remaining).

    Reaps expired entries first. A stale MCP_PENDING mapping (its code already
    gone from PENDING_ORDERS) counts as not-busy — presence in PENDING_ORDERS is
    the source of truth (decision 5).
    """
    _reap_expired_pending()
    code = MCP_PENDING.get(email)
    if code and code in PENDING_ORDERS:
        _, expires_at = PENDING_ORDERS[code]
        return code, max(0, int(expires_at - time.time()))
    return None


# ---------- the MCP server + tools ----------

# streamable_http_path="/" so mounting at "/mcp" in FastAPI yields the endpoint
# at exactly /mcp (the default "/mcp" here would double to /mcp/mcp).
mcp = FastMCP("kiosk", stateless_http=True, streamable_http_path="/")


@mcp.tool()
def view_menu() -> dict:
    """Return the full kiosk menu and the tax rate.

    Includes sandwiches (with each ingredient's default count and min/max),
    meal sizes, drink types/sizes, water, sauces, and McCafé items. All prices
    are in Saudi Riyals (SR). Call this first, then compose an order from these
    IDs and call place_order.
    """
    start = time.monotonic()
    email = current_user_email.get()
    payload = {
        "menu": load_menu_dict(),
        "tax_rate": TAX_RATE,
        "note": "All prices are in Saudi Riyals (SR).",
    }
    sqlmanager.insert_mcp_call(
        user_email=email, tool="view_menu", args_json=None, ok=1,
        error_or_summary="menu returned", code=None,
        wall_clock_ms=int((time.monotonic() - start) * 1000),
    )
    return payload


@mcp.tool()
def place_order(items: list[OrderItemInput]) -> dict:
    """Place an order and get a pickup code to redeem at the kiosk.

    `items` is a list of tagged objects (use IDs from view_menu):
      - {"type":"sandwich","sandwich_id":..., "ingredients":{id:count}?,
         "is_meal":bool?, "meal_size_id":"S|M|L"?, "meal_drink_type_id":...?}
      - {"type":"drink","drink_type_id":...,"size_id":"S|M|L"}
      - {"type":"water"}
      - {"type":"sauce","sauce_id":...}
      - {"type":"mccafe","mccafe_id":...}

    Ingredient counts are ABSOLUTE, not deltas; omit an ingredient to use its
    menu default; min/max come from the menu; prices are in SR. The order is
    atomic — if any item is invalid the whole order is rejected (nothing is
    saved). You may hold only ONE pending code at a time; redeem it or wait for
    it to expire before ordering again. On success returns
    {code, expires_in_seconds, summary, subtotal, tax, total}; show the code and
    total to the user and tell them to redeem it at the kiosk.
    """
    start = time.monotonic()
    email = current_user_email.get()
    menu = load_menu()
    args_json = json.dumps([i.model_dump() for i in items]) if items else "[]"

    def _log(ok: int, msg: str, code: str | None = None) -> None:
        sqlmanager.insert_mcp_call(
            user_email=email, tool="place_order", args_json=args_json, ok=ok,
            error_or_summary=msg, code=code,
            wall_clock_ms=int((time.monotonic() - start) * 1000),
        )

    if not items:
        msg = "Error: no items to order. Add at least one item."
        _log(0, msg)
        return {"error": msg}

    busy = pending_code_for_user(email)
    if busy is not None:
        code, remaining = busy
        msg = (
            f"You already have a pending code ({code}). Time left: {remaining}s. "
            f"Redeem it at the kiosk or wait for it to expire."
        )
        _log(0, msg)
        return {"error": msg}

    order, err = build_order_from_items(items, menu)
    if order is None:
        _log(0, err)
        return {"error": err}

    # Price + deep-copy into the shared pending store under a fresh code with
    # the standard 60s TTL — same bridge the kiosk /redeem route reads.
    priced = price_order(order, menu)
    snapshot = priced.model_copy(deep=True)
    code = _generate_unique_code()
    PENDING_ORDERS[code] = (snapshot, time.time() + CODE_TTL_SECONDS)
    MCP_PENDING[email] = code

    summary = summarize_order_for_customer(snapshot, menu)
    _log(1, summary, code=code)
    return {
        "code": code,
        "expires_in_seconds": CODE_TTL_SECONDS,
        "summary": summary,
        "subtotal": snapshot.subtotal,
        "tax": snapshot.tax,
        "total": snapshot.total,
    }


# Build the Starlette ASGI app now (this also creates mcp.session_manager, which
# mainfast's lifespan enters). Must happen before session_manager is accessed.
mcp_app = mcp.streamable_http_app()


class BearerAuthMiddleware:
    """Pure-ASGI gate in front of the MCP app.

    Resolves the per-user static bearer token to a user BEFORE any tool dispatch
    and stashes the email in a ContextVar. Missing/invalid token -> 401 with
    WWW-Authenticate: Bearer. Registered users only, by construction (the token
    hash only exists on a real user row).
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers") or [])
        auth = headers.get(b"authorization", b"").decode("latin-1")
        token = auth[len("Bearer "):].strip() if auth.startswith("Bearer ") else ""

        user = None
        if token:
            token_hash = hashlib.sha256(token.encode()).hexdigest()
            user = sqlmanager.get_user_by_mcp_token_hash(token_hash)

        if user is None:
            await self._unauthorized(send)
            return

        reset_token = current_user_email.set(user["email"])
        try:
            await self.app(scope, receive, send)
        finally:
            current_user_email.reset(reset_token)

    @staticmethod
    async def _unauthorized(send) -> None:
        body = b'{"error":"unauthorized"}'
        await send({
            "type": "http.response.start",
            "status": 401,
            "headers": [
                (b"content-type", b"application/json"),
                (b"www-authenticate", b"Bearer"),
                (b"content-length", str(len(body)).encode()),
            ],
        })
        await send({"type": "http.response.body", "body": body})


# The auth-wrapped app mainfast mounts at /mcp.
mounted_app = BearerAuthMiddleware(mcp_app)
