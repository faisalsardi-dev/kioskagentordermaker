import json
from datapydentic import Menu, Order
from llmagent import run_turn
from llmtools import PENDING_ORDERS

with open("mcmenu.json") as f:
    menu = Menu(**json.load(f))

order = Order()
history = []

text, history = run_turn("I want a McChicken Spicy with extra cheese.", history, order, menu)
print("AGENT:", text)
print()

text, history = run_turn("Yes lock it in.", history, order, menu)
print("AGENT:", text)
print()

print(f"Pending orders: {len(PENDING_ORDERS)}")
print(f"Session order items: {len(order.items)} (should be 0)")