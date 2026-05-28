
import json
from datapydentic import Menu, Cart, SandwichCartItem, DrinkCartItem, WaterCartItem
from totaling import price_cart

with open('mcmenu.json') as f:
    data = json.load(f)
menu = Menu(**data)

cart = Cart()
cart.items.append(SandwichCartItem(
    item_id='mcchicken_spicy', name='McChicken Spicy',
    base_price=19.00, is_meal=True, meal_size_id='M', meal_drink_type_id='coke_zero',
    ingredients={'chicken_patty': 2, 'cheese': 1, 'lettuce': 1, 'tomato': 0, 'mayo': 1},
    computed_price=0.0,
))
cart.items.append(DrinkCartItem(
    drink_type_id='sprite_regular', name='Sprite Regular',
    size_id='L', size_name='Large', price=5.50,
))
cart.items.append(WaterCartItem(price=2.00))

priced = price_cart(cart, menu)

print(f'Subtotal: {priced.subtotal}')
print(f'Tax (15%): {priced.tax}')
print(f'Total: {priced.total}')
