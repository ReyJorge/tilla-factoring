import logging
import os

from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

import app.models  # noqa: F401 — tabulky na Base.metadata před drop_all/create_all

from app.middleware.attach_user import AttachUserMiddleware
from app.database import BASE_DIR, Base, engine, get_db, init_db, reset_demo_schema
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
from app.routers import analysis, auth_router, clients, credit_risk_agent, dashboard, debtors, finance, home, invoices, settings

logger = logging.getLogger(__name__)


def _demo_rebuild_allowed() -> bool:
    """Refuse destructive rebuild in production unless explicitly opted in."""
    env = os.getenv("ENVIRONMENT", "").strip().lower()
    if env == "production":
        return os.getenv("TILLA_ALLOW_DEMO_REBUILD", "").strip() == "1"
    return True


app = FastAPI(title="TILLA", description="Anchored in Trust — Invoice financing MVP")

STATIC_DIR = BASE_DIR / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
(STATIC_DIR / "uploads").mkdir(parents=True, exist_ok=True)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# AttachUser runs inside SessionMiddleware so request.session is populated first (SessionMiddleware registered last = outermost).
app.add_middleware(AttachUserMiddleware)
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET", "tilla-dev-session-secret-change-me"),
)


@app.on_event("startup")
def _startup():
    force_rebuild = os.getenv("TILLA_FORCE_REBUILD", "").strip() == "1"
    if force_rebuild:
        logger.info("FORCE REBUILD ENABLED")
        if not _demo_rebuild_allowed():
            raise RuntimeError(
                "TILLA_FORCE_REBUILD refused: ENVIRONMENT=production requires "
                "TILLA_ALLOW_DEMO_REBUILD=1 for destructive schema reset."
            )
        import app.models  # noqa: F401 — ensure Base.metadata lists every table before create_all

        reset_demo_schema(engine)
        Base.metadata.create_all(bind=engine)
        logger.info("DATABASE RECREATED")
        seed(skip_schema_reset=True)
        logger.info("SEED COMPLETE")
        return

    init_db()
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


@app.get("/debug/analysis-check")
def debug_analysis_check(db: Session = Depends(get_db)):
    """Smoke JSON for debtor analysis aggregation — never raises."""
    try:
        payload = analysis.build_debtors_analysis_payload(db)
        return {
            "ok": True,
            "debtors": payload["debtor_count"],
            "rows": payload["rows_count"],
            "chart_points": payload["chart_points"],
        }
    except Exception as exc:
        logger.exception("debug/analysis-check failed")
        return JSONResponse(status_code=200, content={"ok": False, "error": str(exc)})


@app.get("/")
def root():
    return RedirectResponse(url="/home")


app.include_router(auth_router.router)
app.include_router(credit_risk_agent.pages)
app.include_router(credit_risk_agent.api)

app.include_router(home.router)
app.include_router(dashboard.router)
app.include_router(clients.router)
app.include_router(debtors.router)
app.include_router(invoices.router)
app.include_router(finance.router)
app.include_router(analysis.router)
app.include_router(settings.router)
