from datetime import date

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.services import dashboard_service
from app.template_helpers import template_ctx, templates

router = APIRouter(tags=["dashboard"])

_DASH_VIEWS = frozenset({"demo", "cfo", "partner"})


@router.get("/dashboard")
def dashboard(
    request: Request,
    db: Session = Depends(get_db),
    view: str | None = Query(None, description="demo | cfo | partner"),
):
    dashboard_service.refresh_dashboard_invoices(db)
    db.commit()
    dash_view = (view or "").strip().lower()
    if dash_view not in _DASH_VIEWS:
        dash_view = "demo"

    kpis = dashboard_service.dashboard_kpis(db)

    overdue = dashboard_service.overdue_rows(db, limit=8 if dash_view == "partner" else 10)

    if dash_view == "demo":
        finalize_list = dashboard_service.finalize_candidates(db)
        unmatched = dashboard_service.unmatched_payment_rows(db)
        offsets = dashboard_service.unsettled_offsets_clients(db)
        reminders = dashboard_service.reminders_due(db)
    elif dash_view == "cfo":
        finalize_list = []
        unmatched = dashboard_service.unmatched_payment_rows(db)
        offsets = dashboard_service.unsettled_offsets_clients(db)
        reminders = []
    else:
        finalize_list = []
        unmatched = []
        offsets = dashboard_service.unsettled_offsets_clients(db, limit=6)
        reminders = []

    view_labels = {
        "demo": "Kompletní provozní náhled — ukázková data.",
        "cfo": "Cashflow a rizika — bez operativní šumu.",
        "partner": "Metriky pro vložení do ERP — přehled pro integrátora.",
    }

    return templates.TemplateResponse(
        "dashboard.html",
        template_ctx(
            request,
            nav_active="dashboard",
            dash_view=dash_view,
            dash_view_label=view_labels[dash_view],
            overdue=overdue,
            finalize_list=finalize_list,
            unmatched=unmatched,
            offsets=offsets,
            reminders=reminders,
            kpis=kpis,
            today=date.today(),
        ),
    )
