import json
from datapydentic import Menu, Order, SandwichOrderItem, DrinkOrderItem, WaterOrderItem
from totaling import price_order

with open('mcmenu.json') as f:
    data = json.load(f)
menu = Menu(**data)

order = Order()
order.items.append(SandwichOrderItem(
    item_id='mcchicken_spicy', name='McChicken Spicy',
    base_price=19.00, is_meal=True, meal_size_id='M', meal_drink_type_id='coke_zero',
    ingredients={'chicken_patty': 2, 'cheese': 1, 'lettuce': 1, 'tomato': 0, 'mayo': 1},
    computed_price=0.0,
))
order.items.append(DrinkOrderItem(
    drink_type_id='sprite_regular', name='Sprite Regular',
    size_id='L', size_name='Large', price=5.50,
))
order.items.append(WaterOrderItem(price=2.00))

priced = price_order(order, menu)

print(f'Subtotal: {priced.subtotal}')
print(f'Tax (15%): {priced.tax}')
print(f'Total: {priced.total}')