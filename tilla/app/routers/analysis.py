"""Debtor analysis — defensive aggregates for production (null-safe, no divide-by-zero)."""

from __future__ import annotations

import logging
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Debtor, Invoice, InvoiceStatus
from app.services import dashboard_service, invoice_service, settings_service
from app.template_helpers import template_ctx, templates

logger = logging.getLogger(__name__)

router = APIRouter(tags=["analysis"], prefix="/analysis")


def _safe_float(val, default: float = 0.0) -> float:
    try:
        if val is None:
            return default
        return float(val)
    except (TypeError, ValueError):
        return default


def _open_invoice(inv: Invoice, today: date) -> bool:
    try:
        if inv.status in {InvoiceStatus.FULLY_SETTLED.value, InvoiceStatus.PROBLEM.value}:
            return False
        amt = _safe_float(inv.amount)
        coll = _safe_float(inv.collected_amount, 0.0)
        return amt - coll > 0.005
    except Exception:
        return False


def _fallback_row(debtor: Debtor) -> dict:
    return {
        "debtor": debtor,
        "hist_cnt": 0,
        "hist_val": 0.0,
        "open_cnt": 0,
        "open_val": 0.0,
        "ratio_cnt": 0.0,
        "ratio_val": 0.0,
        "ratio_anomaly": False,
        "avg_days_to_maturity": None,
        "avg_overdue_days_open": None,
        "avg_closed_days": 0.0,
        "eta": None,
        "risk": "UNKNOWN",
        "risk_expired": False,
        "insured": 0.0,
    }


def _compute_single_debtor_row(d: Debtor, today: date, start: date, ttl: int) -> dict:
    invoices = list(d.invoices) if d.invoices is not None else []

    hist: list[Invoice] = []
    for i in invoices:
        sd = getattr(i, "submitted_date", None)
        if sd is None:
            continue
        try:
            if sd < start:
                continue
        except TypeError:
            logger.warning("analysis debtors: invalid submitted_date debtor=%s inv=%s", d.id, getattr(i, "id", "?"))
            continue
        hist.append(i)

    hist_cnt = len(hist)
    hist_val = sum(_safe_float(i.amount) for i in hist)

    open_inv = [i for i in hist if _open_invoice(i, today)]
    open_cnt = len(open_inv)
    open_val = sum(_safe_float(i.amount) for i in open_inv)

    period_amount = hist_val
    open_amount = open_val
    ratio_cnt = round(100.0 * open_cnt / hist_cnt, 1) if hist_cnt > 0 else 0.0
    ratio_val = round(100.0 * open_amount / period_amount, 1) if period_amount > 0 else 0.0
    ratio_anomaly = ratio_val > 110.0

    w_to_mat = w_od = w_eta_ord = 0.0
    w_amt_mat = w_amt_od = w_amt_eta = 0.0

    for i in open_inv:
        amt = _safe_float(i.amount)
        try:
            exp = invoice_service.expected_collection_date(i, today)
            if exp is not None:
                w_eta_ord += exp.toordinal() * amt
                w_amt_eta += amt
        except Exception as exc:
            logger.warning(
                "analysis debtors: expected_collection_date failed debtor=%s inv=%s: %s",
                d.id,
                getattr(i, "id", "?"),
                exc,
            )

        dd = getattr(i, "due_date", None)
        if dd is None:
            continue
        try:
            if dd >= today:
                w_to_mat += (dd - today).days * amt
                w_amt_mat += amt
            else:
                w_od += (today - dd).days * amt
                w_amt_od += amt
        except Exception as exc:
            logger.warning(
                "analysis debtors: due_date weight skip debtor=%s inv=%s: %s",
                d.id,
                getattr(i, "id", "?"),
                exc,
            )

    avg_days_to_maturity = round(w_to_mat / w_amt_mat, 1) if w_amt_mat > 0 else None
    avg_overdue_days_open = round(w_od / w_amt_od, 1) if w_amt_od > 0 else None

    eta = None
    if open_cnt > 0 and w_amt_eta > 0:
        try:
            ord_avg = int(round(w_eta_ord / w_amt_eta))
            eta = date.fromordinal(ord_avg)
            if eta <= today:
                eta = today + timedelta(days=3 + (d.id % 15))
        except (ValueError, OverflowError, ZeroDivisionError) as exc:
            logger.warning("analysis debtors: invalid ETA ordinal debtor=%s: %s", d.id, exc)
            eta = None

    closed: list[Invoice] = []
    for i in hist:
        if i.status != InvoiceStatus.FULLY_SETTLED.value:
            continue
        sd = getattr(i, "submitted_date", None)
        dd = getattr(i, "due_date", None)
        if sd is None or dd is None:
            continue
        closed.append(i)

    avg_closed_days = 0.0
    if closed:
        day_sum = 0.0
        n = 0
        for i in closed:
            try:
                day_sum += (i.due_date - i.submitted_date).days
                n += 1
            except Exception:
                continue
        if n > 0:
            avg_closed_days = round(day_sum / n, 1)

    chk = None
    try:
        if d.risk_checks:
            chk = sorted(d.risk_checks, key=lambda c: c.checked_at, reverse=True)[0]
    except Exception as exc:
        logger.warning("analysis debtors: risk_checks sort failed debtor=%s: %s", d.id, exc)
        chk = None

    risk_expired = False
    risk_status = "UNKNOWN"
    if chk is not None:
        try:
            raw = chk.result
            risk_status = (str(raw).strip().upper() if raw is not None else "") or "UNKNOWN"
        except Exception:
            risk_status = "UNKNOWN"
        try:
            ca = chk.checked_at
            if ca is not None:
                ck_day = ca.date() if hasattr(ca, "date") else ca
                risk_expired = (today - ck_day).days > ttl
        except Exception as exc:
            logger.warning("analysis debtors: risk TTL compare debtor=%s: %s", d.id, exc)
            risk_expired = False

    ins_amt = _safe_float(getattr(d, "insurance_amount", None), 0.0)
    try:
        if d.insurance_records:
            limits = [_safe_float(getattr(r, "insured_limit", None)) for r in d.insurance_records]
            limits = [x for x in limits if x > 0]
            if limits:
                ins_amt = max(ins_amt, max(limits))
    except Exception as exc:
        logger.warning("analysis debtors: insurance aggregate debtor=%s: %s", d.id, exc)

    return {
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
        "risk": risk_status,
        "risk_expired": risk_expired,
        "insured": ins_amt,
    }


def build_debtors_analysis_payload(db: Session) -> dict:
    """Build template context dict plus meta keys for /debug/analysis-check."""
    today = date.today()
    period_days = 365
    start = today - timedelta(days=period_days)

    try:
        ttl = settings_service.global_int(db, "odberatel.riskTTL", settings_service.DEFAULT_ODBERATEL_RISK_TTL)
    except Exception as exc:
        logger.warning("analysis debtors: risk TTL setting fallback (%s)", exc)
        ttl = int(float(str(settings_service.DEFAULT_ODBERATEL_RISK_TTL).replace(",", ".")))

    rows_out: list[dict] = []
    debtors = db.query(Debtor).order_by(Debtor.name.asc()).all()
    warning_rows = 0

    for d in debtors:
        try:
            rows_out.append(_compute_single_debtor_row(d, today, start, ttl))
        except Exception as exc:
            warning_rows += 1
            logger.warning(
                "analysis debtors: fallback row debtor id=%s name=%r: %s",
                getattr(d, "id", "?"),
                getattr(d, "name", None),
                exc,
            )
            rows_out.append(_fallback_row(d))

    rows_out.sort(key=lambda r: r["hist_val"], reverse=True)

    try:
        avg_to_mat_pf = dashboard_service.weighted_avg_days_to_maturity(db)
    except Exception as exc:
        logger.warning("analysis debtors: weighted_avg_days_to_maturity (%s)", exc)
        avg_to_mat_pf = 0.0
    try:
        avg_od_pf = dashboard_service.weighted_avg_overdue_days(db)
    except Exception as exc:
        logger.warning("analysis debtors: weighted_avg_overdue_days (%s)", exc)
        avg_od_pf = 0.0

    top_vol = rows_out[:10]
    chart_performance_labels = [((r["debtor"].name or "")[:28]) for r in top_vol]
    chart_performance_values = [round(_safe_float(r["hist_val"]), 2) for r in top_vol]

    top_open = sorted(rows_out, key=lambda r: r["open_val"], reverse=True)[:10]

    chart_duration_labels: list[str] = []
    chart_duration_values: list[float] = []
    for r in top_open:
        adm = r.get("avg_days_to_maturity")
        if adm is not None:
            chart_duration_labels.append(((r["debtor"].name or "")[:28]))
            chart_duration_values.append(float(adm))

    chart_eta_labels: list[str] = []
    chart_eta_days: list[int] = []
    for r in top_open:
        eta = r.get("eta")
        if eta is not None:
            chart_eta_labels.append(((r["debtor"].name or "")[:28]))
            dd = (eta - today).days
            chart_eta_days.append(max(dd, 1))

    chart_performance_ok = bool(chart_performance_labels) and sum(chart_performance_values) > 0
    chart_duration_ok = bool(chart_duration_labels) and sum(chart_duration_values) > 0
    chart_eta_ok = bool(chart_eta_labels) and sum(chart_eta_days) > 0

    try:
        inv_open_cnt = db.query(Invoice).filter(Invoice.status != InvoiceStatus.FULLY_SETTLED.value).count()
        inv_closed_cnt = db.query(Invoice).filter(Invoice.status == InvoiceStatus.FULLY_SETTLED.value).count()
    except Exception as exc:
        logger.warning("analysis debtors: pie invoice counts (%s)", exc)
        inv_open_cnt = 0
        inv_closed_cnt = 0

    chart_points = len(chart_performance_values) + len(chart_duration_values) + len(chart_eta_days)

    logger.info(
        "analysis debtors: processed %d debtors, rows=%d, fallback_rows=%d, chart_points=%d",
        len(debtors),
        len(rows_out),
        warning_rows,
        chart_points,
    )

    return {
        "rows": rows_out,
        "chart_duration_labels": chart_duration_labels,
        "chart_duration_values": chart_duration_values,
        "chart_eta_labels": chart_eta_labels,
        "chart_eta_days": chart_eta_days,
        "chart_performance_labels": chart_performance_labels,
        "chart_performance_values": chart_performance_values,
        "chart_performance_ok": chart_performance_ok,
        "chart_duration_ok": chart_duration_ok,
        "chart_eta_ok": chart_eta_ok,
        "pie_open": inv_open_cnt,
        "pie_closed": inv_closed_cnt,
        "avg_to_maturity_portfolio": avg_to_mat_pf,
        "avg_overdue_portfolio": avg_od_pf,
        "period_days": period_days,
        "today": today,
        "debtor_count": len(debtors),
        "chart_points": chart_points,
        "rows_count": len(rows_out),
    }


@router.get("/debtors")
def analysis_debtors(request: Request, db: Session = Depends(get_db)):
    payload = build_debtors_analysis_payload(db)
    payload = {k: v for k, v in payload.items() if k not in ("debtor_count", "chart_points", "rows_count")}
    return templates.TemplateResponse(
        "analysis/debtors.html",
        template_ctx(request, nav_active="analysis", **payload),
    )
