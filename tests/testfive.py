"""Stress tests for the LLM agent's prompt rules.

Tests:
1. Cap enforcement (5 max, request 5 should pass, request 6 should refuse)
2. Universal 'extra' rule on tomato (default 0)
3. Phrasing variations all produce the same count
"""

import json
from datapydentic import Menu, Order
from llmagent import run_turn

with open("mcmenu.json") as f:
    menu = Menu(**json.load(f))


# ---------- Test 1: cap enforcement ----------
print("=" * 60)
print("TEST 1: cap enforcement")
print("=" * 60)

order = Order()
history = []

text, history = run_turn(
    "build me a mcchicken spicy extra extra extra extra patty "
    "extra extra extra extra cheese "
    "extra extra extra extra extra tomato",
    history, order, menu,
)
print("ASSISTANT:", text)
if order.items and hasattr(order.items[0], "ingredients"):
    ing = order.items[0].ingredients
    print(f"  patty:  {ing.get('chicken_patty', '?')} (expected 5)")
    print(f"  cheese: {ing.get('cheese', '?')} (expected 5)")
    print(f"  tomato: {ing.get('tomato', '?')} (expected 5)")
print()

text, history = run_turn(
    "actually make it six chicken patties",
    history, order, menu,
)
print("ASSISTANT:", text)
print("(expected: refusal mentioning maximum is 5)")
print()


# ---------- Test 2: 'extra tomato' = 1 ----------
print("=" * 60)
print("TEST 2: universal 'extra' on tomato")
print("=" * 60)

order2 = Order()
history2 = []

text, history2 = run_turn(
    "give me a mcchicken spicy with extra tomato",
    history2, order2, menu,
)
print("ASSISTANT:", text)
if order2.items and hasattr(order2.items[0], "ingredients"):
    print(f"  tomato: {order2.items[0].ingredients.get('tomato', '?')} (expected 1)")
print()


# ---------- Test 3: phrasing variations ----------
print("=" * 60)
print("TEST 3: phrasing variations all produce tomato=1")
print("=" * 60)

for phrase in [
    "mcchicken spicy with tomato",
    "mcchicken spicy add tomato",
    "mcchicken spicy and add tomato to it",
    "mcchicken spicy extra tomato",
]:
    order_n = Order()
    history_n = []
    text, history_n = run_turn(phrase, history_n, order_n, menu)
    if order_n.items and hasattr(order_n.items[0], "ingredients"):
        tomato = order_n.items[0].ingredients.get("tomato", "?")
        print(f"  '{phrase[:50]}...' -> tomato={tomato}")
    else:
        print(f"  '{phrase[:50]}...' -> NO SANDWICH ADDED")