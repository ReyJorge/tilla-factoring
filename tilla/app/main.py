import os

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.database import BASE_DIR, init_db
from app.seed import seed_demo_if_empty
from app.routers import analysis, clients, dashboard, debtors, finance, home, invoices, settings

app = FastAPI(title="TILLA", description="Anchored in Trust — Invoice financing MVP")

STATIC_DIR = BASE_DIR / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
(STATIC_DIR / "uploads").mkdir(parents=True, exist_ok=True)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET", "tilla-dev-session-secret-change-me"),
)


@app.on_event("startup")
def _startup():
    init_db()
    seed_demo_if_empty()


@app.get("/health")
def health():
    return {"status": "ok", "service": "tilla"}


@app.get("/")
def root():
    return RedirectResponse(url="/home")


app.include_router(home.router)
app.include_router(dashboard.router)
app.include_router(clients.router)
app.include_router(debtors.router)
app.include_router(invoices.router)
app.include_router(finance.router)
app.include_router(analysis.router)
app.include_router(settings.router)
