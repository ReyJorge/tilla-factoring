from pathlib import Path

from fastapi import Request
from starlette.templating import Jinja2Templates

from app.database import BASE_DIR

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def template_ctx(request: Request, **kwargs):
    flashes = request.session.pop("_flash", [])
    kwargs.setdefault("nav_active", "")
    return {"request": request, "flashes": flashes, **kwargs}


def add_flash(request: Request, message: str) -> None:
    msgs = request.session.get("_flash", [])
    msgs.append(message)
    request.session["_flash"] = msgs


def uploads_dir() -> Path:
    d = BASE_DIR / "static" / "uploads"
    d.mkdir(parents=True, exist_ok=True)
    return d
