#models
import json
from datapydentic import Menu, Cart, SandwichCartItem, DrinkCartItem, WaterCartItem

with open('mcmenu.json') as f:
    data = json.load(f)
menu = Menu(**data)
print(f'Menu OK: {len(menu.sandwiches)} sandwiches')

cart = Cart()

cart.items.append(SandwichCartItem(
    item_id='mcchicken_spicy',
    name='McChicken Spicy',
    base_price=19.00,
    is_meal=True,
    meal_size_id='M',
    meal_drink_type_id='coke_zero',
    ingredients={'chicken_patty': 2, 'cheese': 1, 'lettuce': 1, 'tomato': 0, 'mayo': 1},
    computed_price=31.00,
))

cart.items.append(DrinkCartItem(
    drink_type_id='sprite_regular',
    name='Sprite Regular',
    size_id='L',
    size_name='Large',
    price=5.50,
))

cart.items.append(WaterCartItem(price=2.00))

print(f'Cart has {len(cart.items)} items')
for item in cart.items:
    print(f'  - kind={item.kind} name={item.name}')

print(cart.model_dump_json(indent=2))
