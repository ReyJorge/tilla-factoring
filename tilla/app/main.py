import logging
import os

from fastapi import Depends, FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

import app.models  # noqa: F401 — tabulky na Base.metadata před drop_all/create_all

from app.database import BASE_DIR, Base, engine, get_db, init_db
from app.models import (
    BankStatement,
    Client,
    Debtor,
    Invoice,
    OffsetEntry,
    Payment,
    PaymentBatch,
    Reminder,
    RiskCheck,
)
from app.seed import seed, seed_demo_if_empty
from app.routers import analysis, clients, dashboard, debtors, finance, home, invoices, settings

logger = logging.getLogger(__name__)

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
    if os.getenv("TILLA_FORCE_REBUILD", "").strip() == "1":
        logger.info("FORCE REBUILD ENABLED")
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        logger.info("DATABASE RECREATED")
        seed()
        logger.info("SEED COMPLETE")
        return
    seed_demo_if_empty()


@app.get("/health")
def health():
    return {"status": "ok", "service": "tilla"}


@app.get("/debug/db-counts")
def debug_db_counts(db: Session = Depends(get_db)):
    """Demo diagnostika — počty řádků v hlavních tabulkách."""
    return {
        "clients": db.query(Client).count(),
        "debtors": db.query(Debtor).count(),
        "invoices": db.query(Invoice).count(),
        "payments": db.query(Payment).count(),
        "payment_batches": db.query(PaymentBatch).count(),
        "reminders": db.query(Reminder).count(),
        "offset_entries": db.query(OffsetEntry).count(),
        "risk_checks": db.query(RiskCheck).count(),
        "bank_statements": db.query(BankStatement).count(),
    }


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
