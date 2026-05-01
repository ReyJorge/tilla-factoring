from datetime import date

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.services import dashboard_service
from app.template_helpers import template_ctx, templates

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard")
def dashboard(request: Request, db: Session = Depends(get_db)):
    dashboard_service.refresh_dashboard_invoices(db)
    db.commit()
    overdue = dashboard_service.overdue_rows(db)
    finalize_list = dashboard_service.finalize_candidates(db)
    unmatched = dashboard_service.unmatched_payment_rows(db)
    offsets = dashboard_service.unsettled_offsets_clients(db)
    reminders = dashboard_service.reminders_due(db)
    return templates.TemplateResponse(
        "dashboard.html",
        template_ctx(
            request,
            nav_active="dashboard",
            overdue=overdue,
            finalize_list=finalize_list,
            unmatched=unmatched,
            offsets=offsets,
            reminders=reminders,
            today=date.today(),
        ),
    )
