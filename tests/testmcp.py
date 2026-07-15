"""Standalone test of the MCP place_order builder + busy logic (no network).

Exercises mcpserver.build_order_from_items and pending_code_for_user directly —
the pieces the /mcp place_order tool is built from — without an HTTP server or
LLM. Run from the repo ROOT: python tests/testmcp.py
"""

import os
import sys
import time
import tempfile
from pathlib import Path

# Throwaway DB so we never touch the real analytics file. Must be set BEFORE
# importing sqlmanager/mcpserver (DB_PATH is read at import time).
os.environ["KIOSK_DB_PATH"] = str(Path(tempfile.gettempdir()) / "kiosk_testmcp.db")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from datapydentic import Order
import llmtools
import mcpserver

menu = mcpserver.load_menu()

print("=" * 60)
print("TEST 1: build a valid order (sandwich meal + drink)")
print("=" * 60)
order, err = mcpserver.build_order_from_items(
    [
        {"type": "sandwich", "sandwich_id": "mcroyale", "is_meal": True,
         "meal_size_id": "M", "meal_drink_type_id": "coke_zero"},
        {"type": "drink", "drink_type_id": "coke_zero", "size_id": "M"},
    ],
    menu,
)
assert err == "", f"expected no error, got {err!r}"
assert order is not None and len(order.items) == 2, "expected 2 items"
assert order.items[0].is_meal, "first item should be a meal"
print("OK: 2 items, no error")

print("\nTEST 2: invalid ingredient count rejects the WHOLE order")
order2, err2 = mcpserver.build_order_from_items(
    [
        {"type": "sandwich", "sandwich_id": "mcchicken_spicy"},           # valid
        {"type": "sandwich", "sandwich_id": "mcchicken_spicy",
         "ingredients": {"cheese": 9}},                                   # invalid
    ],
    menu,
)
assert order2 is None, "order must be rejected entirely (no partials)"
assert err2.startswith("Error:"), f"expected Error string, got {err2!r}"
print(f"OK: rejected -> {err2}")

print("\nTEST 3: busy logic (one live code per user)")
email = "tester@example.com"
llmtools.PENDING_ORDERS.clear()
llmtools.MCP_PENDING.clear()

# No pending code -> not busy.
assert mcpserver.pending_code_for_user(email) is None, "should start not-busy"

# Seed a live pending code for the user.
code = "AB12"
llmtools.PENDING_ORDERS[code] = (Order(), time.time() + llmtools.CODE_TTL_SECONDS)
llmtools.MCP_PENDING[email] = code
busy = mcpserver.pending_code_for_user(email)
assert busy is not None and busy[0] == code and busy[1] > 0, f"expected busy, got {busy}"
print(f"OK: busy -> code {busy[0]}, {busy[1]}s left")

# Remove the pending entry: the stale MCP_PENDING mapping must count as not-busy.
del llmtools.PENDING_ORDERS[code]
assert mcpserver.pending_code_for_user(email) is None, "stale mapping must be not-busy"
print("OK: stale mapping is not busy")

print("\nPASS: all MCP builder + busy tests passed")
