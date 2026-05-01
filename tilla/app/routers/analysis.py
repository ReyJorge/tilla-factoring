from datetime import date, timedelta

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Debtor, Invoice, InvoiceStatus
from app.services import invoice_service, settings_service
from app.template_helpers import template_ctx, templates

router = APIRouter(tags=["analysis"], prefix="/analysis")


@router.get("/debtors")
def analysis_debtors(request: Request, db: Session = Depends(get_db)):
    today = date.today()
    period_days = 365
    start = today - timedelta(days=period_days)
    ttl = int(settings_service.global_map(db)["odberatel.riskTTL"].replace(",", "."))
    rows_out: list[dict] = []
    duration_weighted = 0.0
    duration_amt = 0.0

    debtors = db.query(Debtor).order_by(Debtor.name.asc()).all()
    for d in debtors:
        hist = [i for i in d.invoices if i.submitted_date >= start]
        open_inv = [
            i
            for i in d.invoices
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
        weighted_days_open = 0.0
        w_sum = 0.0
        for i in open_inv:
            w = float(i.amount)
            weighted_days_open += invoice_service.days_relative_to_due(i, today) * w
            w_sum += w
        avg_open_days = round(weighted_days_open / w_sum, 1) if w_sum else 0.0
        closed = [i for i in hist if i.status == InvoiceStatus.FULLY_SETTLED.value]
        avg_closed_days = (
            round(sum((i.due_date - i.submitted_date).days for i in closed) / len(closed), 1)
            if closed
            else 0.0
        )
        eta = today + timedelta(days=max(int(avg_open_days), 0))

        chk = (
            sorted(d.risk_checks, key=lambda c: c.checked_at, reverse=True)[0]
            if d.risk_checks
            else None
        )
        risk_expired = False
        if chk:
            risk_expired = (today - chk.checked_at.date()).days > ttl

        ins_amt = float(d.insurance_amount or 0)
        if d.insurance_records:
            ins_amt = max(ins_amt, max(float(r.insured_limit) for r in d.insurance_records))

        rows_out.append(
            {
                "debtor": d,
                "hist_cnt": hist_cnt,
                "hist_val": hist_val,
                "open_cnt": open_cnt,
                "open_val": open_val,
                "ratio_cnt": ratio_cnt,
                "ratio_val": ratio_val,
                "avg_open_days": avg_open_days,
                "avg_closed_days": avg_closed_days,
                "eta": eta,
                "risk": chk.result if chk else "—",
                "risk_expired": risk_expired,
                "insured": ins_amt,
            }
        )

        for i in open_inv:
            duration_amt += float(i.amount)
            duration_weighted += invoice_service.days_relative_to_due(i, today) * float(i.amount)

    rows_out.sort(key=lambda r: r["hist_val"], reverse=True)
    avg_asset_duration = round(duration_weighted / duration_amt, 1) if duration_amt else 0.0

    top_vol = rows_out[:10]
    chart_performance_labels = [r["debtor"].name[:28] for r in top_vol]
    chart_performance_values = [round(r["hist_val"], 2) for r in top_vol]
    top_open = sorted(rows_out, key=lambda r: r["open_val"], reverse=True)[:10]
    chart_duration_labels = [r["debtor"].name[:28] for r in top_open]
    chart_duration_values = [r["avg_open_days"] for r in top_open]

    chart_eta_labels = [r["debtor"].name[:28] for r in top_open]
    chart_eta_values = [max((r["eta"] - today).days, 0) for r in top_open]

    inv_open_cnt = db.query(Invoice).filter(Invoice.status != InvoiceStatus.FULLY_SETTLED.value).count()
    inv_closed_cnt = db.query(Invoice).filter(Invoice.status == InvoiceStatus.FULLY_SETTLED.value).count()

    return templates.TemplateResponse(
        "analysis/debtors.html",
        template_ctx(
            request,
            nav_active="analysis",
            rows=rows_out,
            chart_duration_labels=chart_duration_labels,
            chart_duration_values=chart_duration_values,
            chart_eta_labels=chart_eta_labels,
            chart_eta_values=chart_eta_values,
            chart_performance_labels=chart_performance_labels,
            chart_performance_values=chart_performance_values,
            pie_open=inv_open_cnt,
            pie_closed=inv_closed_cnt,
            avg_asset_duration=avg_asset_duration,
            period_days=period_days,
            today=today,
        ),
    )
