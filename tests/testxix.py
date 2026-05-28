import json
import time
from datapydentic import Menu, Order
from llmtools import (
    add_sandwich, add_drink, finalize_order,
    PENDING_ORDERS, CODE_TTL_SECONDS,
)

with open("mcmenu.json") as f:
    menu = Menu(**json.load(f))

# Build an order
order = Order()
print(add_sandwich(order, menu, "mcchicken_spicy"))
print(add_drink(order, menu, "coke_zero", "M"))

print(f"\nBefore finalize: order.items={len(order.items)}, pending={len(PENDING_ORDERS)}")

# Finalize
print("\n" + finalize_order(order, menu))

print(f"\nAfter finalize: order.items={len(order.items)}, pending={len(PENDING_ORDERS)}")

# Inspect the pending entry
code = list(PENDING_ORDERS.keys())[0]
pending_order, expires_at = PENDING_ORDERS[code]
print(f"\nPending under code {code}:")
print(f"  items: {len(pending_order.items)}")
print(f"  total: SR {pending_order.total}")
print(f"  expires in: {expires_at - time.time():.1f}s")

# Try finalizing an empty order
print("\nFinalizing empty order:")
print(finalize_order(Order(), menu))