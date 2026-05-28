import json
from datapydentic import Menu, Order
from llmagent import run_turn

with open("mcmenu.json") as f:
    menu = Menu(**json.load(f))

order = Order()
history = []

# Turn 1
text, history = run_turn(
    "I want a McChicken Spicy with extra cheese and a large coke zero.",
    history, order, menu,
)
print("ASSISTANT:", text)
print()

# Turn 2
text, history = run_turn(
    "Make the sandwich a medium meal with sprite zero. Then show me the order.",
    history, order, menu,
)
print("ASSISTANT:", text)
print()

# Turn 3
text, history = run_turn(
    "What's the weather?",
    history, order, menu,
)
print("ASSISTANT:", text)
print()

print("FINAL ORDER ITEMS:", len(order.items))
for i, item in enumerate(order.items):
    print(f"  {i}: {item.kind} {item.name}")