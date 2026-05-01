from datetime import date, datetime
from pathlib import Path

from fastapi import Request
from starlette.templating import Jinja2Templates

from app.database import BASE_DIR

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def cs_money(amount, currency: str = "CZK") -> str:
    try:
        v = float(amount)
    except (TypeError, ValueError):
        return "—"
    rounded = round(v)
    neg = rounded < 0
    r = abs(int(rounded))
    parts = []
    while r >= 1000:
        parts.append(f"{r % 1000:03d}")
        r //= 1000
    parts.append(str(r))
    body = " ".join(reversed(parts))
    out = f"-{body}" if neg else body
    return f"{out} {currency.strip()}"


def cs_date(value) -> str:
    if value is None:
        return "—"
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, date):
        return value.strftime("%d.%m.%Y")
    return str(value)


def cs_pct(value, decimals: int = 1) -> str:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "—"
    return f"{v:.{decimals}f}".replace(".", ",")


def cs_int(amount) -> str:
    try:
        v = int(round(float(amount)))
    except (TypeError, ValueError):
        return "—"
    neg = v < 0
    r = abs(v)
    groups = []
    while r >= 1000:
        groups.append(f"{r % 1000:03d}")
        r //= 1000
    groups.append(str(r))
    body = " ".join(reversed(groups))
    out = f"-{body}" if neg else body
    return out


templates.env.filters["cs_money"] = cs_money
templates.env.filters["cs_date"] = cs_date
templates.env.filters["cs_pct"] = cs_pct
templates.env.filters["cs_int"] = cs_int


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
