from datetime import datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Debtor, Invoice, InvoiceStatus
from app.services import invoice_service, risk_service, settings_service
from app.template_helpers import add_flash, template_ctx, templates

router = APIRouter(tags=["debtors"])


def debtor_metrics(db: Session, debtor: Debtor, period_days: int = 365):
    from datetime import date, timedelta

    today = date.today()
    start = today - timedelta(days=period_days)
    hist = [i for i in debtor.invoices if i.submitted_date >= start]
    open_inv = [
        i
        for i in debtor.invoices
        if i.status
        not in {InvoiceStatus.FULLY_SETTLED.value, InvoiceStatus.PROBLEM.value}
        and i.status != InvoiceStatus.NEW.value
    ]
    hist_cnt = len(hist)
    hist_val = sum(float(i.amount) for i in hist)
    open_cnt = len(open_inv)
    open_val = sum(float(i.amount) for i in open_inv)
    ratio_cnt = round(100.0 * open_cnt / hist_cnt, 1) if hist_cnt else 0.0
    ratio_val = round(100.0 * open_val / hist_val, 1) if hist_val else 0.0

    closed = [i for i in hist if i.status == InvoiceStatus.FULLY_SETTLED.value]
    weighted_days_open = 0.0
    w_sum = 0.0
    for i in open_inv:
        w = float(i.amount)
        weighted_days_open += invoice_service.days_relative_to_due(i, today) * w
        w_sum += w
    avg_open_days = round(weighted_days_open / w_sum, 1) if w_sum else 0.0

    avg_closed_days = 0.0
    if closed:
        avg_closed_days = round(
            sum((i.due_date - i.submitted_date).days for i in closed) / len(closed),
            1,
        )

    eta_days = max(int(avg_open_days), 0)
    eta_date = today
    from datetime import timedelta as td

    eta_date = today + td(days=eta_days)

    exp = invoice_service.debtor_open_exposure(db, debtor.id)

    return {
        "hist_cnt": hist_cnt,
        "hist_val": hist_val,
        "open_cnt": open_cnt,
        "open_val": open_val,
        "ratio_cnt": ratio_cnt,
        "ratio_val": ratio_val,
        "avg_open_days": avg_open_days,
        "avg_closed_days": avg_closed_days,
        "eta_date": eta_date,
        "exposure": exp,
    }


@router.get("/debtors")
def debtor_list(request: Request, db: Session = Depends(get_db)):
    rows = db.query(Debtor).order_by(Debtor.name.asc()).all()
    enriched = []
    for d in rows:
        chk = risk_service.latest_check(db, d.id)
        ttl = int(settings_service.global_map(db)["odberatel.riskTTL"].replace(",", "."))
        expired = False
        if chk:
            expired = (datetime.utcnow().date() - chk.checked_at.date()).days > ttl
        enriched.append({"debtor": d, "check": chk, "expired": expired})
    return templates.TemplateResponse(
        "debtors/list.html",
        template_ctx(request, nav_active="debtors", rows=enriched),
    )


@router.get("/debtors/{debtor_id}")
def debtor_detail(debtor_id: int, request: Request, db: Session = Depends(get_db)):
    debtor = db.get(Debtor, debtor_id)
    if not debtor:
        raise HTTPException(status_code=404)
    metrics = debtor_metrics(db, debtor)
    invoices = sorted(debtor.invoices, key=lambda i: i.due_date, reverse=True)
    return templates.TemplateResponse(
        "debtors/detail.html",
        template_ctx(
            request,
            nav_active="debtors",
            debtor=debtor,
            metrics=metrics,
            invoices=invoices[:40],
            InvoiceStatus=InvoiceStatus,
        ),
    )


@router.post("/debtors/create")
def debtor_create(
    request: Request,
    db: Session = Depends(get_db),
    name: str = Form(...),
    ic: str = Form(...),
    email: str | None = Form(None),
    country_code: str = Form("CZ"),
):
    d = Debtor(
        name=name.strip(),
        ic=ic.strip(),
        email=(email or "").strip() or None,
        country_code=country_code.strip().upper()[:2],
    )
    db.add(d)
    db.flush()
    settings_service.log_audit(db, action="debtor_create", entity_type="debtor", entity_id=d.id)
    db.commit()
    add_flash(request, "Odběratel založen.")
    return RedirectResponse(url=f"/debtors/{d.id}", status_code=303)


@router.post("/debtors/{debtor_id}/edit")
def debtor_edit(
    debtor_id: int,
    request: Request,
    db: Session = Depends(get_db),
    name: str = Form(...),
    ic: str = Form(...),
    email: str | None = Form(None),
    country_code: str = Form("CZ"),
    insurance_amount: float | None = Form(None),
):
    debtor = db.get(Debtor, debtor_id)
    if not debtor:
        raise HTTPException(status_code=404)
    debtor.name = name.strip()
    debtor.ic = ic.strip()
    debtor.email = (email or "").strip() or None
    debtor.country_code = country_code.strip().upper()[:2]
    debtor.insurance_amount = insurance_amount
    db.commit()
    add_flash(request, "Odběratel uložen.")
    return RedirectResponse(url=f"/debtors/{debtor_id}", status_code=303)


@router.post("/debtors/{debtor_id}/delete")
def debtor_delete(debtor_id: int, request: Request, db: Session = Depends(get_db)):
    debtor = db.get(Debtor, debtor_id)
    if not debtor:
        raise HTTPException(status_code=404)
    if debtor.invoices:
        add_flash(request, "Nelze smazat — existují faktury.")
        return RedirectResponse(url=f"/debtors/{debtor_id}", status_code=303)
    db.delete(debtor)
    db.commit()
    add_flash(request, "Odběratel smazán.")
    return RedirectResponse(url="/debtors", status_code=303)


@router.post("/debtors/{debtor_id}/screen")
def debtor_screen(debtor_id: int, request: Request, db: Session = Depends(get_db)):
    debtor = db.get(Debtor, debtor_id)
    if not debtor:
        raise HTTPException(status_code=404)
    risk_service.simulate_screening(db, debtor_id)
    db.commit()
    add_flash(request, "Nová lustrace dokončena.")
    return RedirectResponse(url=f"/debtors/{debtor_id}", status_code=303)

