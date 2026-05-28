import json
from datapydentic import Menu, Order
from llmtools import add_sandwich, add_drink, add_water, view_order, remove_item, clear_order

with open('mcmenu.json') as f:
    menu = Menu(**json.load(f))

order = Order()

print(add_sandwich(order, menu, "mcchicken_spicy"))
print(add_sandwich(order, menu, "mcroyale", ingredients={"cheese": 3, "tomato": 0}))
print(add_sandwich(order, menu, "mcchicken_spicy",
    ingredients={"chicken_patty": 2},
    is_meal=True, meal_size_id="L", meal_drink_type_id="sprite_zero"))
print(add_drink(order, menu, "coke_zero", "M"))
print(add_water(order, menu))
print(view_order(order, menu))
print(add_sandwich(order, menu, "bigmac"))
print(add_drink(order, menu, "coke_zero", "XXL"))
print(add_sandwich(order, menu, "mcchicken_spicy", ingredients={"cheese": 99}))