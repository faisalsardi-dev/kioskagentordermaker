"""Tool functions the AI agent can call to build an order.

Each function takes the current Order (a Pydantic Order object)
and the Menu, mutates the order in place, and returns a short
human-readable result string. The result strings are what the
LLM reads back to decide what to do next or what to tell the user.
"""

from datapydentic import (
    Menu,
    Order,
    SandwichOrderItem,
    DrinkOrderItem,
    WaterOrderItem,
    SauceOrderItem,
    McCafeOrderItem,
)
from totaling import price_order


# ---------- internal helpers ----------


def _find_sandwich(menu: Menu, sandwich_id: str):
    return next((s for s in menu.sandwiches if s.id == sandwich_id), None)


def _find_drink_type(menu: Menu, drink_type_id: str):
    return next((d for d in menu.drink_types if d.id == drink_type_id), None)


def _find_drink_size(menu: Menu, size_id: str):
    return next((s for s in menu.drink_sizes if s.id == size_id), None)


def _find_meal_size(menu: Menu, meal_size_id: str):
    return next((m for m in menu.meal_sizes if m.id == meal_size_id), None)


def _find_sauce(menu: Menu, sauce_id: str):
    return next((s for s in menu.sauces if s.id == sauce_id), None)


def _find_mccafe(menu: Menu, mccafe_id: str):
    return next((m for m in menu.mccafe if m.id == mccafe_id), None)


# ---------- tools ----------


def add_sandwich(
    order: Order,
    menu: Menu,
    sandwich_id: str,
    ingredients: dict[str, int] | None = None,
    is_meal: bool = False,
    meal_size_id: str | None = None,
    meal_drink_type_id: str | None = None,
) -> str:
    """Add a sandwich to the order.

    `ingredients` is a dict of ingredient_id -> absolute count.
    Omitted ingredients use defaults from the menu.
    `is_meal` requires `meal_size_id` and `meal_drink_type_id`.
    """
    sandwich = _find_sandwich(menu, sandwich_id)
    if not sandwich:
        return f"Error: unknown sandwich '{sandwich_id}'. Use one from the menu."

    # Start from defaults, then apply user-specified overrides
    final_ingredients = {ing.id: ing.default for ing in sandwich.ingredients}
    if ingredients:
        for ing_id, count in ingredients.items():
            spec = next((i for i in sandwich.ingredients if i.id == ing_id), None)
            if not spec:
                return f"Error: '{ing_id}' is not an ingredient of {sandwich.name}."
            if count < spec.min or count > spec.max:
                return (
                    f"Error: {spec.name} must be between {spec.min} and {spec.max}. "
                    f"You asked for {count}."
                )
            final_ingredients[ing_id] = count

    if is_meal:
        if not meal_size_id or not meal_drink_type_id:
            return (
                "Error: a meal requires both meal_size_id "
                "('S', 'M', or 'L') and meal_drink_type_id."
            )
        if not _find_meal_size(menu, meal_size_id):
            return f"Error: unknown meal size '{meal_size_id}'."
        if not _find_drink_type(menu, meal_drink_type_id):
            return f"Error: unknown meal drink '{meal_drink_type_id}'."

    order.items.append(SandwichOrderItem(
        item_id=sandwich.id,
        name=sandwich.name,
        base_price=sandwich.price,
        is_meal=is_meal,
        meal_size_id=meal_size_id if is_meal else None,
        meal_drink_type_id=meal_drink_type_id if is_meal else None,
        ingredients=final_ingredients,
        computed_price=0.0,
    ))

    meal_note = ""
    if is_meal:
        size = _find_meal_size(menu, meal_size_id)
        drink = _find_drink_type(menu, meal_drink_type_id)
        meal_note = f" ({size.name} meal with {drink.name})"
    return f"Added {sandwich.name}{meal_note}."


def add_drink(order: Order, menu: Menu, drink_type_id: str, size_id: str) -> str:
    """Add a standalone (non-meal) drink to the order."""
    drink = _find_drink_type(menu, drink_type_id)
    if not drink:
        return f"Error: unknown drink '{drink_type_id}'."
    size = _find_drink_size(menu, size_id)
    if not size:
        return f"Error: unknown drink size '{size_id}'. Use 'S', 'M', or 'L'."

    order.items.append(DrinkOrderItem(
        drink_type_id=drink.id,
        name=drink.name,
        size_id=size.id,
        size_name=size.name,
        price=size.price,
    ))
    return f"Added {size.name} {drink.name} for SR {size.price}."


def add_water(order: Order, menu: Menu) -> str:
    """Add a water to the order."""
    order.items.append(WaterOrderItem(price=menu.water.price))
    return f"Added Water for SR {menu.water.price}."


def add_sauce(order: Order, menu: Menu, sauce_id: str) -> str:
    """Add a sauce to the order."""
    sauce = _find_sauce(menu, sauce_id)
    if not sauce:
        return f"Error: unknown sauce '{sauce_id}'."

    order.items.append(SauceOrderItem(
        sauce_id=sauce.id,
        name=sauce.name,
        price=sauce.price,
    ))
    return f"Added {sauce.name} for SR {sauce.price}."


def add_mccafe(order: Order, menu: Menu, mccafe_id: str) -> str:
    """Add a McCafé item to the order."""
    mccafe = _find_mccafe(menu, mccafe_id)
    if not mccafe:
        return f"Error: unknown McCafé item '{mccafe_id}'."

    order.items.append(McCafeOrderItem(
        item_id=mccafe.id,
        name=mccafe.name,
        price=mccafe.price,
    ))
    return f"Added {mccafe.name} for SR {mccafe.price}."


def view_order(order: Order, menu: Menu) -> str:
    """Return a full text summary of the current order with prices and totals."""
    if not order.items:
        return "Order is empty."

    priced = price_order(order, menu)
    lines = []
    for i, item in enumerate(priced.items):
        if item.kind == "sandwich":
            ing_str = ", ".join(f"{k}={v}" for k, v in item.ingredients.items())
            meal_str = ""
            if item.is_meal:
                size = _find_meal_size(menu, item.meal_size_id)
                drink = _find_drink_type(menu, item.meal_drink_type_id)
                meal_str = f" ({size.name} meal, {drink.name})"
            lines.append(
                f"{i}: {item.name}{meal_str} [{ing_str}] — SR {item.computed_price}"
            )
        elif item.kind == "drink":
            lines.append(f"{i}: {item.size_name} {item.name} — SR {item.price}")
        elif item.kind == "water":
            lines.append(f"{i}: {item.name} — SR {item.price}")
        elif item.kind == "sauce":
            lines.append(f"{i}: {item.name} — SR {item.price}")
        elif item.kind == "mccafe":
            lines.append(f"{i}: {item.name} — SR {item.price}")

    lines.append(f"\nSubtotal: SR {priced.subtotal}")
    lines.append(f"Tax (15%): SR {priced.tax}")
    lines.append(f"Total: SR {priced.total}")
    return "\n".join(lines)


def remove_item(order: Order, index: int) -> str:
    """Remove the item at the given 0-based index from the order."""
    if index < 0 or index >= len(order.items):
        return f"Error: no item at index {index}. Order has {len(order.items)} items."
    removed = order.items.pop(index)
    return f"Removed: {removed.name}."


def clear_order(order: Order) -> str:
    """Remove all items from the order."""
    n = len(order.items)
    order.items.clear()
    return f"Cleared {n} item(s) from order."


#one more function for code redemption