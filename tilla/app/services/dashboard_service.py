from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Client, Invoice, InvoiceStatus, OffsetEntry, Payment, Reminder
from app.services import invoice_service


def refresh_dashboard_invoices(db: Session) -> None:
    today = date.today()
    for inv in db.query(Invoice).all():
        if invoice_service.refresh_auto_overdue(db, inv, today):
            db.add(inv)


def overdue_rows(db: Session, limit: int = 12) -> list[Invoice]:
    today = date.today()
    return (
        db.query(Invoice)
        .filter(Invoice.due_date < today, Invoice.status != InvoiceStatus.FULLY_SETTLED.value)
        .order_by(Invoice.due_date.asc())
        .limit(limit)
        .all()
    )


def finalize_candidates(db: Session, limit: int = 12) -> list[Invoice]:
    candidates: list[Invoice] = []
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
        .order_by(Invoice.due_date.asc())
        .all()
    ):
        if float(inv.collected_amount or 0) >= float(inv.amount) * 0.999:
            candidates.append(inv)
        if len(candidates) >= limit:
            break
    return candidates


def unmatched_payment_rows(db: Session, limit: int = 15) -> list[Payment]:
    return (
        db.query(Payment)
        .filter(Payment.matched_invoice_id.is_(None))
        .order_by(Payment.payment_date.desc())
        .limit(limit)
        .all()
    )


def unsettled_offsets_clients(db: Session, limit: int = 10) -> list[dict]:
    totals: dict[int, float] = {}
    for cid, total in (
        db.query(OffsetEntry.client_id, func.sum(OffsetEntry.amount_czk)).group_by(OffsetEntry.client_id).all()
    ):
        totals[cid] = float(total or 0)
    flagged = [(cid, bal) for cid, bal in totals.items() if abs(bal) > 5000]
    flagged.sort(key=lambda x: abs(x[1]), reverse=True)
    out: list[dict] = []
    for cid, bal in flagged[:limit]:
        c = db.get(Client, cid)
        if c:
            out.append({"client": c, "balance": bal})
    return out


def reminders_due(db: Session, limit: int = 12) -> list[Reminder]:
    today = date.today()
    return (
        db.query(Reminder)
        .filter(Reminder.sent_at.is_(None), Reminder.scheduled_for <= today)
        .order_by(Reminder.scheduled_for.asc())
        .limit(limit)
        .all()
    )
