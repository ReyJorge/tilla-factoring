from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.models import Invoice, OffsetEntry, Payment
from app.services import invoice_service, settings_service


def list_unmatched(db: Session):
    return db.query(Payment).filter(Payment.matched_invoice_id.is_(None)).order_by(Payment.payment_date.desc()).all()


def match_payment(db: Session, payment_id: int, invoice_id: int) -> Payment:
    pay = db.get(Payment, payment_id)
    inv = db.get(Invoice, invoice_id)
    if not pay or not inv:
        raise ValueError("Platba nebo faktura nenalezena.")
    if pay.matched_invoice_id:
        raise ValueError("Platba je již spárovaná.")
    pay.matched_invoice_id = invoice_id
    invoice_service.register_collection(db, inv, float(pay.amount))
    settings_service.log_audit(
        db,
        action="payment_match",
        entity_type="payment",
        entity_id=payment_id,
        detail=f"invoice={invoice_id}",
    )
    return pay


def offset_client_totals(db: Session, client_id: int) -> dict:
    rows = db.query(OffsetEntry).filter(OffsetEntry.client_id == client_id).all()
    bearing = sum(float(r.amount_czk) for r in rows if r.interest_bearing)
    nonbearing = sum(float(r.amount_czk) for r in rows if not r.interest_bearing)
    total = bearing + nonbearing
    significance = "ok"
    label = "vše v pořádku"
    if abs(total) > 500000:
        significance = "problem"
        label = "problém — významná nevyrovnanost"
    elif abs(total) > 25000:
        significance = "attention"
        label = "pozor — zkontrolujte položky"
    return {
        "bearing": bearing,
        "nonbearing": nonbearing,
        "total": total,
        "significance": significance,
        "label": label,
        "rows_interest": [r for r in rows if r.interest_bearing],
        "rows_noninterest": [r for r in rows if not r.interest_bearing],
    }


def add_manual_offset(
    db: Session,
    *,
    client_id: int,
    movement_date: date,
    description: str,
    original_amount: float,
    original_currency: str,
    fx_rate_to_czk: float,
    interest_bearing: bool,
    invoice_id: int | None = None,
):
    amount_czk = round(original_amount * fx_rate_to_czk, 2)
    row = OffsetEntry(
        client_id=client_id,
        invoice_id=invoice_id,
        movement_date=movement_date,
        description=description,
        original_amount=original_amount,
        original_currency=original_currency,
        fx_rate_to_czk=fx_rate_to_czk,
        amount_czk=amount_czk,
        interest_bearing=interest_bearing,
    )
    db.add(row)
    settings_service.log_audit(
        db,
        action="offset_manual_add",
        entity_type="client",
        entity_id=client_id,
        detail=description[:200],
    )
    return row
