"""FastAPI app: kiosk mimic + AI order builder."""
from pathlib import Path
import json

from fastapi import FastAPI, Request, HTTPException
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


def load_menu() -> dict:
    with MENU_PATH.open() as f:
        return json.load(f)


@app.get("/", response_class=HTMLResponse)
def landing(request: Request):
    return templates.TemplateResponse(
        request,
        "kiosk.html",
        {},
    )


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
        request,
        "category.html",
        {"category": category, "items": items, "kind": kind},
    )


@app.get("/api/menu")
def get_menu() -> dict:
    return load_menu()