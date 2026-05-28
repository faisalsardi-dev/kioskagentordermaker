from datapydentic import (
    Menu,
    Order,
    SandwichOrderItem,
    DrinkOrderItem,
    WaterOrderItem,
    SauceOrderItem,
    McCafeOrderItem,
)


TAX_RATE = 0.15


def price_sandwich(item: SandwichOrderItem, menu: Menu) -> float:
    """Compute the total price for one sandwich order item."""
    sandwich = next(s for s in menu.sandwiches if s.id == item.item_id)

    total = sandwich.price

    if item.is_meal:
        meal_size = next(m for m in menu.meal_sizes if m.id == item.meal_size_id)
        total += meal_size.price

    for ingredient in sandwich.ingredients:
        count = item.ingredients.get(ingredient.id, ingredient.default)
        extra_units = max(0, count - ingredient.default)
        total += extra_units * ingredient.extra_price

    return round(total, 2)


def price_order(order: Order, menu: Menu) -> Order:
    """Return a new Order with computed_price set on sandwiches, and subtotal/tax/total filled in."""
    priced_items = []
    subtotal = 0.0

    for item in order.items:
        if isinstance(item, SandwichOrderItem):
            new_price = price_sandwich(item, menu)
            priced_item = item.model_copy(update={"computed_price": new_price})
            subtotal += new_price
            priced_items.append(priced_item)
        elif isinstance(item, (DrinkOrderItem, WaterOrderItem, SauceOrderItem, McCafeOrderItem)):
            subtotal += item.price
            priced_items.append(item)
        else:
            raise ValueError(f"Unknown order item kind: {item}")
    # decimal.Decimal with ROUND_HALF_UP would be more accurate
    subtotal = round(subtotal, 2)
    tax = round(subtotal * TAX_RATE, 2)
    total = round(subtotal + tax, 2)

    return Order(
        items=priced_items,
        subtotal=subtotal,
        tax=tax,
        total=total,
    )