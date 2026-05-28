from typing import Literal
from pydantic import BaseModel, Field


# ----------------------- MENU TYPES -----------------------


class Ingredient(BaseModel):
    id: str
    name: str
    default: int = Field(ge=0, le=5)
    min: int = Field(ge=0, le=5)
    max: int = Field(ge=0, le=5)
    extra_price: float = Field(ge=0)


class Sandwich(BaseModel):
    id: str
    name: str
    price: float = Field(ge=0)
    image: str
    ingredients: list[Ingredient]


class MealSize(BaseModel):
    id: str
    name: str
    price: float = Field(ge=0)


class DrinkSize(BaseModel):
    id: str
    name: str
    price: float = Field(ge=0)


class DrinkType(BaseModel):
    id: str
    name: str


class Water(BaseModel):
    id: str
    name: str
    price: float = Field(ge=0)


class Sauce(BaseModel):
    id: str
    name: str
    price: float = Field(ge=0)


class McCafeItem(BaseModel):
    id: str
    name: str
    price: float = Field(ge=0)


class Menu(BaseModel):
    sandwiches: list[Sandwich]
    meal_sizes: list[MealSize]
    drink_sizes: list[DrinkSize]
    drink_types: list[DrinkType]
    water: Water
    sauces: list[Sauce]
    mccafe: list[McCafeItem]


# ----------------------- CART TYPES -----------------------


class SandwichCartItem(BaseModel):
    kind: Literal["sandwich"] = "sandwich"
    item_id: str
    name: str
    base_price: float = Field(ge=0)
    is_meal: bool = False
    meal_size_id: str | None = None
    meal_drink_type_id: str | None = None
    ingredients: dict[str, int]
    computed_price: float = Field(ge=0)


class DrinkCartItem(BaseModel):
    kind: Literal["drink"] = "drink"
    drink_type_id: str
    name: str
    size_id: str
    size_name: str
    price: float = Field(ge=0)


class WaterCartItem(BaseModel):
    kind: Literal["water"] = "water"
    name: str = "Water"
    price: float = Field(ge=0)


class SauceCartItem(BaseModel):
    kind: Literal["sauce"] = "sauce"
    sauce_id: str
    name: str
    price: float = Field(ge=0)


class McCafeCartItem(BaseModel):
    kind: Literal["mccafe"] = "mccafe"
    item_id: str
    name: str
    price: float = Field(ge=0)


CartItem = (
    SandwichCartItem
    | DrinkCartItem
    | WaterCartItem
    | SauceCartItem
    | McCafeCartItem
)


class Cart(BaseModel):
    items: list[CartItem] = Field(default_factory=list)
    subtotal: float = Field(default=0.0, ge=0)
    tax: float = Field(default=0.0, ge=0)
    total: float = Field(default=0.0, ge=0)