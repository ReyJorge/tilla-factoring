from datetime import date, timedelta

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Debtor, Invoice, InvoiceStatus
from app.services import dashboard_service, invoice_service, settings_service
from app.template_helpers import template_ctx, templates

router = APIRouter(tags=["analysis"], prefix="/analysis")


def _open_invoice(inv: Invoice, today: date) -> bool:
    if inv.status in {InvoiceStatus.FULLY_SETTLED.value, InvoiceStatus.PROBLEM.value}:
        return False
    return float(inv.amount) - float(inv.collected_amount or 0) > 0.005


@router.get("/debtors")
def analysis_debtors(request: Request, db: Session = Depends(get_db)):
    today = date.today()
    period_days = 365
    start = today - timedelta(days=period_days)
    ttl = settings_service.global_int(db, "odberatel.riskTTL", settings_service.DEFAULT_ODBERATEL_RISK_TTL)
    rows_out: list[dict] = []

    debtors = db.query(Debtor).order_by(Debtor.name.asc()).all()
    for d in debtors:
        hist = [i for i in d.invoices if i.submitted_date >= start]
        hist_cnt = len(hist)
        hist_val = sum(float(i.amount) for i in hist)

        open_inv = [i for i in hist if _open_invoice(i, today)]
        open_cnt = len(open_inv)
        open_val = sum(float(i.amount) for i in open_inv)

        ratio_cnt = round(100.0 * open_cnt / hist_cnt, 1) if hist_cnt else 0.0
        ratio_val = round(100.0 * open_val / hist_val, 1) if hist_val else 0.0
        ratio_anomaly = ratio_val > 110.0

        w_to_mat = w_od = w_eta_ord = 0.0
        w_amt_mat = w_amt_od = 0.0
        for i in open_inv:
            amt = float(i.amount)
            exp = invoice_service.expected_collection_date(i, today)
            w_eta_ord += exp.toordinal() * amt
            w_amt_eta += amt
            if i.due_date >= today:
                w_to_mat += (i.due_date - today).days * amt
                w_amt_mat += amt
            else:
                w_od += (today - i.due_date).days * amt
                w_amt_od += amt

        avg_days_to_maturity = round(w_to_mat / w_amt_mat, 1) if w_amt_mat else 0.0
        avg_overdue_days_open = round(w_od / w_amt_od, 1) if w_amt_od else 0.0

        if open_val > 0:
            eta = date.fromordinal(int(round(w_eta_ord / open_val)))
            if eta <= today:
                eta = today + timedelta(days=3 + (d.id % 15))
        else:
            eta = today + timedelta(days=14)

        closed = [i for i in hist if i.status == InvoiceStatus.FULLY_SETTLED.value]
        avg_closed_days = (
            round(sum((i.due_date - i.submitted_date).days for i in closed) / len(closed), 1)
            if closed
            else 0.0
        )

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
                "ratio_anomaly": ratio_anomaly,
                "avg_days_to_maturity": avg_days_to_maturity,
                "avg_overdue_days_open": avg_overdue_days_open,
                "avg_closed_days": avg_closed_days,
                "eta": eta,
                "risk": chk.result if chk else "—",
                "risk_expired": risk_expired,
                "insured": ins_amt,
            }
        )

    rows_out.sort(key=lambda r: r["hist_val"], reverse=True)

    avg_to_mat_pf = dashboard_service.weighted_avg_days_to_maturity(db)
    avg_od_pf = dashboard_service.weighted_avg_overdue_days(db)

    top_vol = rows_out[:10]
    chart_performance_labels = [r["debtor"].name[:28] for r in top_vol]
    chart_performance_values = [round(r["hist_val"], 2) for r in top_vol]

    top_open = sorted(rows_out, key=lambda r: r["open_val"], reverse=True)[:10]
    chart_duration_labels = [r["debtor"].name[:28] for r in top_open]
    chart_duration_values = [r["avg_days_to_maturity"] for r in top_open]

    chart_eta_labels = [r["debtor"].name[:28] for r in top_open]
    chart_eta_days = []
    for r in top_open:
        dd = (r["eta"] - today).days
        chart_eta_days.append(max(dd, 1))

    chart_performance_ok = bool(chart_performance_labels) and sum(chart_performance_values) > 0
    chart_duration_ok = bool(chart_duration_labels) and sum(chart_duration_values) > 0
    chart_eta_ok = bool(chart_eta_labels) and sum(chart_eta_days) > 0

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
            chart_eta_days=chart_eta_days,
            chart_performance_labels=chart_performance_labels,
            chart_performance_values=chart_performance_values,
            chart_performance_ok=chart_performance_ok,
            chart_duration_ok=chart_duration_ok,
            chart_eta_ok=chart_eta_ok,
            pie_open=inv_open_cnt,
            pie_closed=inv_closed_cnt,
            avg_to_maturity_portfolio=avg_to_mat_pf,
            avg_overdue_portfolio=avg_od_pf,
            period_days=period_days,
            today=today,
        ),
    )
