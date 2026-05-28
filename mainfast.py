"""FastAPI app: kiosk mimic + AI order builder."""
from pathlib import Path
import json

from fastapi import FastAPI, Request
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


@app.get("/", response_class=HTMLResponse)
def landing(request: Request):
    return templates.TemplateResponse(
        request,
        "kiosk.html",
        {"heading": "mcmenumimic"},
    )


@app.get("/api/menu")
def get_menu() -> dict:
    with MENU_PATH.open() as f:
        return json.load(f)