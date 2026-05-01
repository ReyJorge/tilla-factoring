from fastapi import APIRouter, Depends, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Debtor, Invoice, InvoiceStatus
from app.services import dashboard_service
from app.template_helpers import template_ctx, templates

router = APIRouter(tags=["home"])


@router.get("/home")
def landing(request: Request, db: Session = Depends(get_db)):
    kpis = dashboard_service.dashboard_kpis(db)
    total_inv = db.query(func.count(Invoice.id)).scalar() or 0
    settled = (
        db.query(func.count(Invoice.id))
        .filter(Invoice.status == InvoiceStatus.FULLY_SETTLED.value)
        .scalar()
        or 0
    )
    success_rate = round(100.0 * settled / total_inv, 1) if total_inv else 0.0
    anchors = db.query(func.count(Debtor.id)).scalar() or 0
    metrics = {
        "czk_financed": kpis["exec_financed_exposure_czk"],
        "invoices_processed": total_inv,
        "settlement_success_rate": success_rate,
        "active_anchors": anchors,
    }
    return templates.TemplateResponse(
        "home.html",
        template_ctx(request, nav_active="home", metrics=metrics),
    )
