"""End-to-end test of the redemption flow without LLM calls.

Uses FastAPI's TestClient to share module state (PENDING_ORDERS, ORDER)
with the routes. Seeds a finalized order directly via llmtools.finalize_order,
then exercises POST /redeem and verifies kiosk ORDER is populated.
"""

import json
from fastapi.testclient import TestClient

from datapydentic import Menu, Order
from llmtools import add_sandwich, add_drink, finalize_order, PENDING_ORDERS
import mainfast  # imports the app and shares ORDER state


client = TestClient(mainfast.app)

with open("mcmenu.json") as f:
    menu = Menu(**json.load(f))


# ---------- Test 1: happy path ----------
print("=" * 60)
print("TEST 1: build, finalize, redeem")
print("=" * 60)

# Clean slate
mainfast.ORDER.items.clear()
PENDING_ORDERS.clear()

# Build a session-side order
session_order = Order()
print(add_sandwich(session_order, menu, "mcchicken_spicy",
                   ingredients={"cheese": 2}))
print(add_drink(session_order, menu, "coke_zero", "M"))

# Finalize -> generates code, stashes in PENDING_ORDERS
result = finalize_order(session_order, menu)
print(result)

# Extract the code (last word minus trailing period)
code = result.split("Code: ")[1].split(".")[0]
print(f"Extracted code: {code}")

# Sanity: pending has it
assert code in PENDING_ORDERS, "Code missing from PENDING_ORDERS"
assert len(mainfast.ORDER.items) == 0, "Kiosk ORDER should be empty pre-redeem"

# Redeem
response = client.post("/redeem", data={"code": code}, follow_redirects=False)
print(f"Redeem status: {response.status_code} (expected 303)")
print(f"Redirect to: {response.headers.get('location')}")

# Verify kiosk now holds the order
print(f"Kiosk ORDER items: {len(mainfast.ORDER.items)} (expected 2)")
print(f"Pending entries: {len(PENDING_ORDERS)} (expected 0)")

for i, item in enumerate(mainfast.ORDER.items):
    print(f"  {i}: {item.kind} {item.name}")


# ---------- Test 2: bad code ----------
print()
print("=" * 60)
print("TEST 2: bad code")
print("=" * 60)

response = client.post("/redeem", data={"code": "NOPE"}, follow_redirects=False)
print(f"Bad code status: {response.status_code} (expected 303)")
print(f"Redirect to: {response.headers.get('location')} (expected /?error=bad_code)")


# ---------- Test 3: case insensitivity ----------
print()
print("=" * 60)
print("TEST 3: lowercase code should still redeem")
print("=" * 60)

# Build and finalize again
mainfast.ORDER.items.clear()
PENDING_ORDERS.clear()

session_order2 = Order()
add_sandwich(session_order2, menu, "mcroyale")
result = finalize_order(session_order2, menu)
code = result.split("Code: ")[1].split(".")[0]
print(f"Code generated: {code}")

# Submit lowercase
response = client.post("/redeem", data={"code": code.lower()}, follow_redirects=False)
print(f"Lowercase redeem status: {response.status_code} (expected 303)")
print(f"Redirect to: {response.headers.get('location')}")
print(f"Kiosk has McRoyale: {any('McRoyale' in item.name for item in mainfast.ORDER.items)}")