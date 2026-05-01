from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Client, Debtor, Invoice, InvoiceStatus, OffsetEntry, Payment, Reminder, RiskCheck
from app.services import invoice_service, settings_service


def refresh_dashboard_invoices(db: Session) -> None:
    today = date.today()
    for inv in db.query(Invoice).all():
        if invoice_service.refresh_auto_overdue(db, inv, today):
            db.add(inv)


def overdue_rows(db: Session, limit: int = 10) -> list[Invoice]:
    """Nejdéle po splatnosti první — řazení podle splatnosti vzestupně (nejstarší = nejvíc dnů overdue)."""
    today = date.today()
    return (
        db.query(Invoice)
        .filter(Invoice.due_date < today, Invoice.status != InvoiceStatus.FULLY_SETTLED.value)
        .order_by(Invoice.due_date.asc())
        .limit(limit)
        .all()
    )


def finalize_candidates(db: Session, limit: int | None = 8) -> list[Invoice]:
    pool: list[Invoice] = []
    for inv in (
        db.query(Invoice)
        .filter(
            Invoice.status.in_(
                [
                    InvoiceStatus.PURCHASED.value,
                    InvoiceStatus.ADVANCE_FINANCED.value,
                    InvoiceStatus.AWAITING_COLLECTION.value,
                    InvoiceStatus.PARTIALLY_PAID.value,
                    InvoiceStatus.OVERDUE.value,
                ]
            )
        )
        .all()
    ):
        if float(inv.collected_amount or 0) >= float(inv.amount) * 0.999:
            pool.append(inv)
    pool.sort(key=lambda i: float(i.collected_amount or 0) / float(i.amount), reverse=True)
    return pool if limit is None else pool[:limit]


def unmatched_payment_rows(db: Session, limit: int = 8) -> list[Payment]:
    return (
        db.query(Payment)
        .filter(Payment.matched_invoice_id.is_(None))
        .order_by(Payment.payment_date.desc())
        .limit(limit)
        .all()
    )


def _offset_significance(balance: float) -> tuple[str, str]:
    a = abs(balance)
    if a > 500_000:
        return "danger", "problém"
    if a > 25_000:
        return "warning", "pozor"
    return "ok", "v pořádku"


def unsettled_offsets_clients(db: Session, limit: int = 6) -> list[dict]:
    totals: dict[int, float] = {}
    for cid, total in (
        db.query(OffsetEntry.client_id, func.sum(OffsetEntry.amount_czk)).group_by(OffsetEntry.client_id).all()
    ):
        totals[cid] = float(total or 0)
    flagged = [(cid, bal) for cid, bal in totals.items() if abs(bal) > 1]
    flagged.sort(key=lambda x: abs(x[1]), reverse=True)
    out: list[dict] = []
    for cid, bal in flagged[:limit]:
        c = db.get(Client, cid)
        if c:
            st, lbl = _offset_significance(bal)
            out.append({"client": c, "balance": bal, "status_key": st, "status_label": lbl})
    return out


def reminders_due(db: Session, limit: int = 10) -> list[Reminder]:
    today = date.today()
    return (
        db.query(Reminder)
        .filter(Reminder.sent_at.is_(None), Reminder.scheduled_for <= today)
        .order_by(Reminder.scheduled_for.asc())
        .limit(limit)
        .all()
    )


def portfolio_open_exposure_czk_equiv(db: Session) -> float:
    # Převod EUR expozice: kurz.EUR z tabulky global_settings; chybí-li záznam, demo výchozí 25.00 CZK/EUR.
    fx = settings_service.global_float(db, "kurz.EUR", settings_service.DEFAULT_KURZ_EUR)
    tot = 0.0
    for inv in (
        db.query(Invoice)
        .filter(
            Invoice.status.in_(
                [
                    InvoiceStatus.PURCHASED.value,
                    InvoiceStatus.ADVANCE_FINANCED.value,
                    InvoiceStatus.AWAITING_COLLECTION.value,
                    InvoiceStatus.PARTIALLY_PAID.value,
                    InvoiceStatus.OVERDUE.value,
                    InvoiceStatus.PENDING_DEBTOR_CONFIRM.value,
                    InvoiceStatus.DEBTOR_CONFIRMED.value,
                    InvoiceStatus.PENDING_CHECK.value,
                    InvoiceStatus.NEW.value,
                    InvoiceStatus.PROBLEM.value,
                ]
            )
        )
        .all()
    ):
        if inv.status == InvoiceStatus.FULLY_SETTLED.value:
            continue
        open_amt = float(inv.amount) - float(inv.collected_amount or 0)
        if open_amt <= 0:
            continue
        if inv.currency == "CZK":
            tot += open_amt
        else:
            tot += open_amt * fx
    return tot


def active_invoices_count(db: Session) -> int:
    return (
        db.query(Invoice)
        .filter(Invoice.status != InvoiceStatus.FULLY_SETTLED.value)
        .count()
    )


def overdue_invoices_count(db: Session) -> int:
    today = date.today()
    return (
        db.query(Invoice)
        .filter(Invoice.due_date < today, Invoice.status != InvoiceStatus.FULLY_SETTLED.value)
        .count()
    )


def unmatched_payments_stats(db: Session) -> tuple[int, float]:
    rows = db.query(Payment).filter(Payment.matched_invoice_id.is_(None)).all()
    if not rows:
        return 0, 0.0
    fx = settings_service.global_float(db, "kurz.EUR", settings_service.DEFAULT_KURZ_EUR)
    czk_eq = 0.0
    for p in rows:
        amt = float(p.amount)
        if p.currency == "CZK":
            czk_eq += amt
        else:
            czk_eq += amt * fx
    return len(rows), czk_eq


def weighted_avg_days_to_maturity(db: Session) -> float:
    """Vážený počet dnů DO splatnosti jen pro otevřené položky před splatností (kladné hodnoty)."""
    today = date.today()
    wsum = 0.0
    wtot = 0.0
    for inv in db.query(Invoice).all():
        if inv.status == InvoiceStatus.FULLY_SETTLED.value:
            continue
        open_amt = float(inv.amount) - float(inv.collected_amount or 0)
        if open_amt <= 0:
            continue
        if inv.due_date < today:
            continue
        days_to = (inv.due_date - today).days
        wsum += days_to * open_amt
        wtot += open_amt
    return round(wsum / wtot, 1) if wtot else 0.0


def weighted_avg_overdue_days(db: Session) -> float:
    """Vážené zpoždění PO splatnosti (kladné = dnů po splatnosti)."""
    today = date.today()
    wsum = 0.0
    wtot = 0.0
    for inv in db.query(Invoice).all():
        if inv.status == InvoiceStatus.FULLY_SETTLED.value:
            continue
        open_amt = float(inv.amount) - float(inv.collected_amount or 0)
        if open_amt <= 0:
            continue
        if inv.due_date >= today:
            continue
        overdue_days = (today - inv.due_date).days
        wsum += overdue_days * open_amt
        wtot += open_amt
    return round(wsum / wtot, 1) if wtot else 0.0


def risk_ok_rate(db: Session) -> float:
    ttl = settings_service.global_int(db, "odberatel.riskTTL", settings_service.DEFAULT_ODBERATEL_RISK_TTL)
    debtors = db.query(Debtor).all()
    if not debtors:
        return 100.0
    ok_cnt = 0
    for d in debtors:
        chk = (
            db.query(RiskCheck)
            .filter(RiskCheck.debtor_id == d.id)
            .order_by(RiskCheck.checked_at.desc())
            .first()
        )
        if not chk:
            continue
        age = (datetime.utcnow().date() - chk.checked_at.date()).days
        if chk.result == "OK" and age <= ttl:
            ok_cnt += 1
    return round(100.0 * ok_cnt / len(debtors), 1)


def dashboard_kpis(db: Session) -> dict:
    today = date.today()
    unmatched_n, unmatched_czk = unmatched_payments_stats(db)
    return {
        "open_exposure_czk": round(portfolio_open_exposure_czk_equiv(db), 2),
        "active_invoices": active_invoices_count(db),
        "overdue_count": overdue_invoices_count(db),
        "unmatched_count": unmatched_n,
        "unmatched_czk_equiv": round(unmatched_czk, 2),
        # Průměrná durace aktiv = dny do splatnosti (otevřené, ještě nesplatné); overdue samostatně níže v šabloně.
        "avg_duration_open": weighted_avg_days_to_maturity(db),
        "avg_overdue_days": weighted_avg_overdue_days(db),
        "risk_ok_rate": risk_ok_rate(db),
        "today": today,
    }
