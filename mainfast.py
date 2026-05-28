"""FastAPI app: kiosk mimic + AI order builder."""
from pathlib import Path
import json
from totaling import price_order
from fastapi.responses import HTMLResponse, RedirectResponse
import uuid
from fastapi import FastAPI, Request, HTTPException, Cookie, Response
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from datapydentic import (
    Menu,
    Order,
    SandwichOrderItem,
    DrinkOrderItem,
    WaterOrderItem,
    SauceOrderItem,
    McCafeOrderItem,
)

ROOT = Path(__file__).parent
MENU_PATH = ROOT / "mcmenu.json"

app = FastAPI(
    title="mcmenumimic",
    description="A McDonald's-style self-service kiosk with optional AI order builder.",
)

app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
templates = Jinja2Templates(directory=ROOT / "templates")

# Single global order. Single-user demo only.
# Production would key orders by session ID.
ORDER: Order = Order()

# Per-session state for /orderai conversations.
# Key: session_id (UUID string). Value: (history, order).
# Lives in memory; dies on server restart.
SESSIONS: dict[str, tuple[list, Order]] = {}


def get_or_create_session(session_id: str | None) -> tuple[str, list, Order]:
    """Return (session_id, history, order). Creates new state if needed."""
    if session_id is None or session_id not in SESSIONS:
        session_id = str(uuid.uuid4())
        SESSIONS[session_id] = ([], Order())
    history, order = SESSIONS[session_id]
    return session_id, history, order


def load_menu_dict() -> dict:
    with MENU_PATH.open() as f:
        return json.load(f)


def load_menu() -> Menu:
    return Menu(**load_menu_dict())


@app.get("/", response_class=HTMLResponse)
def landing(request: Request):
    return templates.TemplateResponse(request, "kiosk.html", {})


@app.get("/category/{category}", response_class=HTMLResponse)
def category_page(request: Request, category: str):
    menu = load_menu_dict()

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
    menu = load_menu_dict()

    if kind == "sandwich":
        item = next((s for s in menu["sandwiches"] if s["id"] == item_id), None)
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
        if item_id == menu["water"]["id"]:
            return templates.TemplateResponse(
                request, "customize_water.html",
                {"item": menu["water"], "added": added},
            )
        item = next((d for d in menu["drink_types"] if d["id"] == item_id), None)
        if not item:
            raise HTTPException(404, f"Drink not found: {item_id}")
        return templates.TemplateResponse(
            request, "customize_drink.html",
            {"item": item, "drink_sizes": menu["drink_sizes"], "added": added},
        )

    elif kind == "sauce":
        item = next((s for s in menu["sauces"] if s["id"] == item_id), None)
        if not item:
            raise HTTPException(404, f"Sauce not found: {item_id}")
        return templates.TemplateResponse(
            request, "customize_sauce.html",
            {"item": item, "added": added},
        )

    elif kind == "mccafe":
        item = next((m for m in menu["mccafe"] if m["id"] == item_id), None)
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
    sandwich = next((s for s in menu.sandwiches if s.id == item_id), None)
    if not sandwich:
        raise HTTPException(404, f"Sandwich not found: {item_id}")

    form = await request.form()
    ingredients = {}
    for ing in sandwich.ingredients:
        raw = form.get(f"ing_{ing.id}", str(ing.default))
        ingredients[ing.id] = max(ing.min, min(ing.max, int(raw)))

    meal_size_id = form.get("meal_size") or None
    is_meal = meal_size_id is not None
    meal_drink_type_id = form.get("meal_drink") if is_meal else None
    quantity = max(1, int(form.get("quantity", "1")))

    for _ in range(quantity):
        ORDER.items.append(SandwichOrderItem(
            item_id=sandwich.id,
            name=sandwich.name,
            base_price=sandwich.price,
            is_meal=is_meal,
            meal_size_id=meal_size_id,
            meal_drink_type_id=meal_drink_type_id,
            ingredients=ingredients,
            computed_price=0.0,  # filled in by price_order() at /order
        ))

    menu_dict = load_menu_dict()
    item_dict = next(s for s in menu_dict["sandwiches"] if s["id"] == item_id)
    return templates.TemplateResponse(
        request, "customize_sandwich.html",
        {
            "item": item_dict,
            "meal_sizes": menu_dict["meal_sizes"],
            "drink_types": menu_dict["drink_types"],
            "added": True,
        },
    )


@app.post("/customize/drink/{item_id}", response_class=HTMLResponse)
async def customize_drink_post(request: Request, item_id: str):
    menu = load_menu()
    form = await request.form()
    quantity = max(1, int(form.get("quantity", "1")))

    if item_id == menu.water.id:
        for _ in range(quantity):
            ORDER.items.append(WaterOrderItem(price=menu.water.price))
        return templates.TemplateResponse(
            request, "customize_water.html",
            {"item": menu.water.model_dump(), "added": True},
        )

    drink_type = next((d for d in menu.drink_types if d.id == item_id), None)
    if not drink_type:
        raise HTTPException(404, f"Drink not found: {item_id}")

    size_id = form.get("size", "M")
    size = next((s for s in menu.drink_sizes if s.id == size_id), None)
    if not size:
        raise HTTPException(400, f"Invalid drink size: {size_id}")

    for _ in range(quantity):
        ORDER.items.append(DrinkOrderItem(
            drink_type_id=drink_type.id,
            name=drink_type.name,
            size_id=size.id,
            size_name=size.name,
            price=size.price,
        ))

    menu_dict = load_menu_dict()
    item_dict = next(d for d in menu_dict["drink_types"] if d["id"] == item_id)
    return templates.TemplateResponse(
        request, "customize_drink.html",
        {"item": item_dict, "drink_sizes": menu_dict["drink_sizes"], "added": True},
    )


@app.post("/customize/sauce/{item_id}", response_class=HTMLResponse)
async def customize_sauce_post(request: Request, item_id: str):
    menu = load_menu()
    sauce = next((s for s in menu.sauces if s.id == item_id), None)
    if not sauce:
        raise HTTPException(404, f"Sauce not found: {item_id}")

    form = await request.form()
    quantity = max(1, int(form.get("quantity", "1")))

    for _ in range(quantity):
        ORDER.items.append(SauceOrderItem(
            sauce_id=sauce.id,
            name=sauce.name,
            price=sauce.price,
        ))

    return templates.TemplateResponse(
        request, "customize_sauce.html",
        {"item": sauce.model_dump(), "added": True},
    )


@app.post("/customize/mccafe/{item_id}", response_class=HTMLResponse)
async def customize_mccafe_post(request: Request, item_id: str):
    menu = load_menu()
    mccafe = next((m for m in menu.mccafe if m.id == item_id), None)
    if not mccafe:
        raise HTTPException(404, f"McCafé item not found: {item_id}")

    form = await request.form()
    quantity = max(1, int(form.get("quantity", "1")))

    for _ in range(quantity):
        ORDER.items.append(McCafeOrderItem(
            item_id=mccafe.id,
            name=mccafe.name,
            price=mccafe.price,
        ))

    return templates.TemplateResponse(
        request, "customize_mccafe.html",
        {"item": mccafe.model_dump(), "added": True},
    )


@app.get("/api/menu")
def get_menu() -> dict:
    return load_menu_dict()


@app.get("/api/order")
def get_order() -> Order:
    return ORDER


@app.get("/order", response_class=HTMLResponse)
def order_page(request: Request):
    menu = load_menu()
    priced = price_order(ORDER, menu)
    return templates.TemplateResponse(
        request, "order.html",
        {"order": priced},
    )


@app.post("/order/remove/{index}")
def order_remove(index: int):
    if 0 <= index < len(ORDER.items):
        ORDER.items.pop(index)
    return RedirectResponse(url="/order", status_code=303)


@app.post("/order/reset")
def order_reset():
    ORDER.items.clear()
    return RedirectResponse(url="/order", status_code=303)


@app.get("/orderai", response_class=HTMLResponse)
def orderai_page(
    request: Request,
    session_id: str | None = Cookie(default=None),
):
    session_id, history, order = get_or_create_session(session_id)

    # Filter to user-visible messages only (skip system + tool messages)
    visible = []
    for msg in history:
        role = type(msg).__name__
        if role == "HumanMessage":
            visible.append({"role": "user", "content": msg.content})
        elif role == "AIMessage" and msg.content:
            visible.append({"role": "assistant", "content": msg.content})

    response = templates.TemplateResponse(
        request, "orderai.html",
        {"messages": visible},
    )
    response.set_cookie("session_id", session_id, max_age=3600, httponly=True)
    return response


@app.post("/orderai/message")
async def orderai_message(
    request: Request,
    session_id: str | None = Cookie(default=None),
):
    from llmagent import run_turn  # local import to avoid loading LangChain at startup

    session_id, history, order = get_or_create_session(session_id)
    form = await request.form()
    user_message = (form.get("message") or "").strip()

    if user_message:
        menu = load_menu()
        _, new_history = run_turn(user_message, history, order, menu)
        SESSIONS[session_id] = (new_history, order)

    response = RedirectResponse(url="/orderai", status_code=303)
    response.set_cookie("session_id", session_id, max_age=3600, httponly=True)
    return response


@app.post("/orderai/reset")
def orderai_reset(session_id: str | None = Cookie(default=None)):
    if session_id and session_id in SESSIONS:
        del SESSIONS[session_id]
    response = RedirectResponse(url="/orderai", status_code=303)
    response.delete_cookie("session_id")
    return response