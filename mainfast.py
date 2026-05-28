"""FastAPI app: kiosk mimic + AI order builder."""
from pathlib import Path
import json

from fastapi import FastAPI, Request, HTTPException, Form
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

ROOT = Path(__file__).parent
MENU_PATH = ROOT / "mcmenu.json"

app = FastAPI(
    title="mcmenumimic",
    description="A McDonald's-style self-service kiosk with optional AI order builder.",
)

app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
templates = Jinja2Templates(directory=ROOT / "templates")

# Single global cart. Single-user demo only.
# Production would key carts by session ID.
CART: list[dict] = []


def load_menu() -> dict:
    with MENU_PATH.open() as f:
        return json.load(f)


def find_sandwich(menu: dict, sandwich_id: str) -> dict | None:
    return next((s for s in menu["sandwiches"] if s["id"] == sandwich_id), None)


def find_drink_type(menu: dict, drink_id: str) -> dict | None:
    return next((d for d in menu["drink_types"] if d["id"] == drink_id), None)


def find_sauce(menu: dict, sauce_id: str) -> dict | None:
    return next((s for s in menu["sauces"] if s["id"] == sauce_id), None)


def find_mccafe(menu: dict, item_id: str) -> dict | None:
    return next((m for m in menu["mccafe"] if m["id"] == item_id), None)


@app.get("/", response_class=HTMLResponse)
def landing(request: Request):
    return templates.TemplateResponse(request, "kiosk.html", {})


@app.get("/category/{category}", response_class=HTMLResponse)
def category_page(request: Request, category: str):
    menu = load_menu()

    if category == "sandwiches":
        items = [{"id": s["id"], "name": s["name"], "price": s["price"]} for s in menu["sandwiches"]]
        kind = "sandwich"
    elif category == "drinks":
        items = [{"id": d["id"], "name": d["name"], "price": None} for d in menu["drink_types"]]
        items.append({"id": menu["water"]["id"], "name": menu["water"]["name"], "price": menu["water"]["price"]})
        kind = "drink"
    elif category == "sauces":
        items = [{"id": s["id"], "name": s["name"], "price": s["price"]} for s in menu["sauces"]]
        kind = "sauce"
    elif category == "mccafe":
        items = [{"id": m["id"], "name": m["name"], "price": m["price"]} for m in menu["mccafe"]]
        kind = "mccafe"
    else:
        raise HTTPException(status_code=404, detail=f"Unknown category: {category}")

    return templates.TemplateResponse(
        request, "category.html",
        {"category": category, "items": items, "kind": kind},
    )


@app.get("/customize/{kind}/{item_id}", response_class=HTMLResponse)
def customize_get(request: Request, kind: str, item_id: str, added: bool = False):
    menu = load_menu()

    if kind == "sandwich":
        item = find_sandwich(menu, item_id)
        if not item:
            raise HTTPException(404, f"Sandwich not found: {item_id}")
        return templates.TemplateResponse(
            request, "customize_sandwich.html",
            {
                "item": item,
                "meal_sizes": menu["meal_sizes"],
                "drink_types": menu["drink_types"],
                "added": added,
            },
        )

    elif kind == "drink":
        # Water is a special case — no size, flat price
        if item_id == menu["water"]["id"]:
            return templates.TemplateResponse(
                request, "customize_water.html",
                {"item": menu["water"], "added": added},
            )
        item = find_drink_type(menu, item_id)
        if not item:
            raise HTTPException(404, f"Drink not found: {item_id}")
        return templates.TemplateResponse(
            request, "customize_drink.html",
            {"item": item, "drink_sizes": menu["drink_sizes"], "added": added},
        )

    elif kind == "sauce":
        item = find_sauce(menu, item_id)
        if not item:
            raise HTTPException(404, f"Sauce not found: {item_id}")
        return templates.TemplateResponse(
            request, "customize_sauce.html",
            {"item": item, "added": added},
        )

    elif kind == "mccafe":
        item = find_mccafe(menu, item_id)
        if not item:
            raise HTTPException(404, f"McCafé item not found: {item_id}")
        return templates.TemplateResponse(
            request, "customize_mccafe.html",
            {"item": item, "added": added},
        )

    else:
        raise HTTPException(404, f"Unknown kind: {kind}")


@app.post("/customize/sandwich/{item_id}", response_class=HTMLResponse)
async def customize_sandwich_post(request: Request, item_id: str):
    menu = load_menu()
    item = find_sandwich(menu, item_id)
    if not item:
        raise HTTPException(404, f"Sandwich not found: {item_id}")

    form = await request.form()
    ingredients = {}
    for ing in item["ingredients"]:
        raw = form.get(f"ing_{ing['id']}", str(ing["default"]))
        ingredients[ing["id"]] = max(ing["min"], min(ing["max"], int(raw)))

    meal_size = form.get("meal_size") or None
    meal_drink = form.get("meal_drink") if meal_size else None
    quantity = max(1, int(form.get("quantity", "1")))

    CART.append({
        "kind": "sandwich",
        "id": item["id"],
        "name": item["name"],
        "ingredients": ingredients,
        "meal_size": meal_size,
        "meal_drink": meal_drink,
        "quantity": quantity,
    })

    return templates.TemplateResponse(
        request, "customize_sandwich.html",
        {
            "item": item,
            "meal_sizes": menu["meal_sizes"],
            "drink_types": menu["drink_types"],
            "added": True,
        },
    )


@app.post("/customize/drink/{item_id}", response_class=HTMLResponse)
async def customize_drink_post(request: Request, item_id: str):
    menu = load_menu()
    form = await request.form()
    quantity = max(1, int(form.get("quantity", "1")))

    if item_id == menu["water"]["id"]:
        CART.append({
            "kind": "water",
            "id": menu["water"]["id"],
            "name": menu["water"]["name"],
            "quantity": quantity,
        })
        return templates.TemplateResponse(
            request, "customize_water.html",
            {"item": menu["water"], "added": True},
        )

    item = find_drink_type(menu, item_id)
    if not item:
        raise HTTPException(404, f"Drink not found: {item_id}")

    size = form.get("size", "M")
    CART.append({
        "kind": "drink",
        "id": item["id"],
        "name": item["name"],
        "size": size,
        "quantity": quantity,
    })
    return templates.TemplateResponse(
        request, "customize_drink.html",
        {"item": item, "drink_sizes": menu["drink_sizes"], "added": True},
    )


@app.post("/customize/sauce/{item_id}", response_class=HTMLResponse)
async def customize_sauce_post(request: Request, item_id: str):
    menu = load_menu()
    item = find_sauce(menu, item_id)
    if not item:
        raise HTTPException(404, f"Sauce not found: {item_id}")

    form = await request.form()
    quantity = max(1, int(form.get("quantity", "1")))

    CART.append({
        "kind": "sauce",
        "id": item["id"],
        "name": item["name"],
        "quantity": quantity,
    })
    return templates.TemplateResponse(
        request, "customize_sauce.html",
        {"item": item, "added": True},
    )


@app.post("/customize/mccafe/{item_id}", response_class=HTMLResponse)
async def customize_mccafe_post(request: Request, item_id: str):
    menu = load_menu()
    item = find_mccafe(menu, item_id)
    if not item:
        raise HTTPException(404, f"McCafé item not found: {item_id}")

    form = await request.form()
    quantity = max(1, int(form.get("quantity", "1")))

    CART.append({
        "kind": "mccafe",
        "id": item["id"],
        "name": item["name"],
        "quantity": quantity,
    })
    return templates.TemplateResponse(
        request, "customize_mccafe.html",
        {"item": item, "added": True},
    )


@app.get("/api/menu")
def get_menu() -> dict:
    return load_menu()


@app.get("/api/cart")
def get_cart() -> list[dict]:
    return CART