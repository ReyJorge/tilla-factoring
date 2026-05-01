from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from app.models import Debtor, Invoice, InvoiceStatus, Reminder, RiskCheck, RiskResult
from app.services import settings_service


def days_relative_to_due(inv: Invoice, today: date | None = None) -> int:
    today = today or date.today()
    return (inv.due_date - today).days


def expected_collection_date(inv: Invoice, today: date | None = None) -> date:
    """Reálnější ETA inkasa než pouhá splatnost — před splatností splatnost + typický lag, po splatnosti obnova od dneška."""
    today = today or date.today()
    open_amt = float(inv.amount) - float(inv.collected_amount or 0)
    if open_amt <= 0.005:
        return inv.due_date
    lag_after_due = 5 + (inv.id % 13)
    if inv.due_date >= today:
        return inv.due_date + timedelta(days=lag_after_due)
    recovery = 4 + (inv.id % 22)
    return today + timedelta(days=max(recovery, 3))


def refresh_auto_overdue(db: Session, inv: Invoice, today: date | None = None) -> bool:
    """Set OVERDUE if past due and status allows. Returns True if changed."""
    today = today or date.today()
    if inv.due_date >= today:
        return False
    terminal = {
        InvoiceStatus.FULLY_SETTLED.value,
        InvoiceStatus.PROBLEM.value,
    }
    if inv.status in terminal:
        return False
    active_financed = {
        InvoiceStatus.PURCHASED.value,
        InvoiceStatus.ADVANCE_FINANCED.value,
        InvoiceStatus.AWAITING_COLLECTION.value,
        InvoiceStatus.PARTIALLY_PAID.value,
        InvoiceStatus.OVERDUE.value,
        InvoiceStatus.PENDING_DEBTOR_CONFIRM.value,
        InvoiceStatus.DEBTOR_CONFIRMED.value,
        InvoiceStatus.PENDING_CHECK.value,
        InvoiceStatus.NEW.value,
    }
    if inv.status in active_financed and inv.status != InvoiceStatus.OVERDUE.value:
        inv.status = InvoiceStatus.OVERDUE.value
        return True
    return False


def compute_advance(amount: float, advance_pct: float) -> float:
    return round(amount * advance_pct / 100.0, 2)


def fee_percent_for_invoice(db: Session, inv: Invoice) -> float:
    debtor = db.get(Debtor, inv.debtor_id)
    insured = bool(debtor and debtor.insurance_amount and float(debtor.insurance_amount) > 0)
    settings = settings_service.merged_settings(db, inv.client_id)
    days_to_due = max((inv.due_date - inv.submitted_date).days, 0)
    p1 = float(settings["poplatek.pasmo1_dny"].replace(",", "."))
    p2 = float(settings["poplatek.pasmo2_dny"].replace(",", "."))
    p3 = float(settings["poplatek.pasmo3_dny"].replace(",", "."))
    key_base = "pojistene" if insured else "nepojistene"
    if days_to_due <= p1:
        return float(settings[f"poplatek.pasmo1_{key_base}"].replace(",", "."))
    if days_to_due <= p2:
        return float(settings[f"poplatek.pasmo2_{key_base}"].replace(",", "."))
    return float(settings[f"poplatek.pasmo3_{key_base}"].replace(",", "."))


def apply_fee_and_advance(db: Session, inv: Invoice):
    adv_pct = float(settings_service.merged_settings(db, inv.client_id)["faktura.zaloha"].replace(",", "."))
    inv.fee_percent = fee_percent_for_invoice(db, inv)
    inv.advance_amount = compute_advance(float(inv.amount), adv_pct)


def client_open_exposure(db: Session, client_id: int) -> dict[str, float]:
    rows = (
        db.query(Invoice)
        .filter(
            Invoice.client_id == client_id,
            Invoice.status.in_(
                [
                    InvoiceStatus.PURCHASED.value,
                    InvoiceStatus.ADVANCE_FINANCED.value,
                    InvoiceStatus.AWAITING_COLLECTION.value,
                    InvoiceStatus.PARTIALLY_PAID.value,
                    InvoiceStatus.OVERDUE.value,
                ]
            ),
        )
        .all()
    )
    czk = 0.0
    eur = 0.0
    fx = settings_service.global_float(db, "kurz.EUR", settings_service.DEFAULT_KURZ_EUR)
    for inv in rows:
        amt = float(inv.amount) - float(inv.collected_amount or 0)
        if inv.currency == "CZK":
            czk += amt
        else:
            eur += amt
    return {"czk": czk, "eur": eur, "czk_equiv": czk + eur * fx}


def debtor_open_exposure(db: Session, debtor_id: int) -> dict[str, float]:
    rows = (
        db.query(Invoice)
        .filter(
            Invoice.debtor_id == debtor_id,
            Invoice.status.in_(
                [
                    InvoiceStatus.PURCHASED.value,
                    InvoiceStatus.ADVANCE_FINANCED.value,
                    InvoiceStatus.AWAITING_COLLECTION.value,
                    InvoiceStatus.PARTIALLY_PAID.value,
                    InvoiceStatus.OVERDUE.value,
                ]
            ),
        )
        .all()
    )
    czk = 0.0
    eur = 0.0
    fx = settings_service.global_float(db, "kurz.EUR", settings_service.DEFAULT_KURZ_EUR)
    for inv in rows:
        amt = float(inv.amount) - float(inv.collected_amount or 0)
        if inv.currency == "CZK":
            czk += amt
        else:
            eur += amt
    return {"czk": czk, "eur": eur, "czk_equiv": czk + eur * fx}


def concentration_ratio(db: Session, client_id: int, debtor_id: int) -> float:
    total = client_open_exposure(db, client_id)["czk_equiv"]
    if total <= 0:
        return 0.0
    dexp = debtor_open_exposure(db, debtor_id)["czk_equiv"]
    return round(100.0 * dexp / total, 2)


ALLOWED_TRANSITIONS: dict[str, list[str]] = {
    InvoiceStatus.NEW.value: [
        InvoiceStatus.PENDING_CHECK.value,
        InvoiceStatus.PENDING_DEBTOR_CONFIRM.value,
        InvoiceStatus.PROBLEM.value,
    ],
    InvoiceStatus.PENDING_CHECK.value: [
        InvoiceStatus.PENDING_DEBTOR_CONFIRM.value,
        InvoiceStatus.PROBLEM.value,
    ],
    InvoiceStatus.PENDING_DEBTOR_CONFIRM.value: [
        InvoiceStatus.DEBTOR_CONFIRMED.value,
        InvoiceStatus.PROBLEM.value,
    ],
    InvoiceStatus.DEBTOR_CONFIRMED.value: [
        InvoiceStatus.PURCHASED.value,
        InvoiceStatus.PROBLEM.value,
    ],
    InvoiceStatus.PURCHASED.value: [
        InvoiceStatus.ADVANCE_FINANCED.value,
        InvoiceStatus.AWAITING_COLLECTION.value,
        InvoiceStatus.PROBLEM.value,
    ],
    InvoiceStatus.ADVANCE_FINANCED.value: [
        InvoiceStatus.AWAITING_COLLECTION.value,
        InvoiceStatus.PROBLEM.value,
    ],
    InvoiceStatus.AWAITING_COLLECTION.value: [
        InvoiceStatus.PARTIALLY_PAID.value,
        InvoiceStatus.FULLY_SETTLED.value,
        InvoiceStatus.OVERDUE.value,
        InvoiceStatus.PROBLEM.value,
    ],
    InvoiceStatus.PARTIALLY_PAID.value: [
        InvoiceStatus.FULLY_SETTLED.value,
        InvoiceStatus.OVERDUE.value,
        InvoiceStatus.PROBLEM.value,
    ],
    InvoiceStatus.OVERDUE.value: [
        InvoiceStatus.PARTIALLY_PAID.value,
        InvoiceStatus.FULLY_SETTLED.value,
        InvoiceStatus.PROBLEM.value,
    ],
    InvoiceStatus.FULLY_SETTLED.value: [],
    InvoiceStatus.PROBLEM.value: [
        InvoiceStatus.PENDING_CHECK.value,
        InvoiceStatus.AWAITING_COLLECTION.value,
    ],
}


def transition_invoice(db: Session, inv: Invoice, new_status: str) -> None:
    allowed = ALLOWED_TRANSITIONS.get(inv.status, [])
    if new_status not in allowed:
        raise ValueError(f"Přechod z {inv.status} do {new_status} není povolen.")
    inv.status = new_status
    if new_status == InvoiceStatus.PURCHASED.value:
        inv.purchased_date = date.today()


def validate_purchase_allowed(db: Session, inv: Invoice) -> tuple[bool, str]:
    debtor = db.get(Debtor, inv.debtor_id)
    if not debtor:
        return False, "Odběratel neexistuje."
    chk = latest_risk_check(db, debtor.id)
    merged = settings_service.merged_settings(db, inv.client_id)
    ttl_raw = merged.get("odberatel.riskTTL", settings_service.DEFAULT_ODBERATEL_RISK_TTL)
    ttl = int(float(str(ttl_raw).replace(",", ".")))
    if not chk:
        return False, "Chybí risk check."
    age_days = (datetime.utcnow().date() - chk.checked_at.date()).days
    if age_days > ttl:
        return False, "Risk check expiroval."
    if chk.result == RiskResult.BLOCK.value:
        return False, "Risk check má výsledek BLOCK — odkup zakázán."
    max_raw = merged.get("faktura.maxKoncentrace", "20")
    max_k = float(str(max_raw).replace(",", "."))
    conc = concentration_ratio(db, inv.client_id, inv.debtor_id)
    if conc > max_k and conc > 0:
        return False, f"Překročena maximální koncentrace ({conc}% > {max_k}%)."
    return True, ""


def latest_risk_check(db: Session, debtor_id: int) -> RiskCheck | None:
    return (
        db.query(RiskCheck)
        .filter(RiskCheck.debtor_id == debtor_id)
        .order_by(RiskCheck.checked_at.desc())
        .first()
    )


def register_collection(db: Session, inv: Invoice, amount: float):
    inv.collected_amount = float(inv.collected_amount or 0) + amount
    if inv.collected_amount + 1e-6 >= float(inv.amount):
        inv.status = InvoiceStatus.FULLY_SETTLED.value
    elif inv.collected_amount > 0:
        inv.status = InvoiceStatus.PARTIALLY_PAID.value


def simulate_reminder_sent(db: Session, inv: Invoice) -> Reminder:
    inv.reminder_level = min(inv.reminder_level + 1, 5)
    rem = Reminder(
        invoice_id=inv.id,
        level=inv.reminder_level,
        scheduled_for=date.today(),
        sent_at=datetime.utcnow(),
    )
    db.add(rem)
    settings_service.log_audit(
        db,
        action="reminder_sent_simulated",
        entity_type="invoice",
        entity_id=inv.id,
        detail=f"level={inv.reminder_level}",
    )
    return rem


def finalize_if_collected(db: Session, inv: Invoice) -> None:
    if float(inv.collected_amount or 0) + 1e-6 < float(inv.amount):
        raise ValueError("Inkaso neodpovídá plné částce faktury.")
    inv.status = InvoiceStatus.FULLY_SETTLED.value


def purchase_invoice(db: Session, inv: Invoice) -> None:
    ok, msg = validate_purchase_allowed(db, inv)
    if not ok:
        raise ValueError(msg)
    if inv.status != InvoiceStatus.DEBTOR_CONFIRMED.value:
        raise ValueError("Odkoupit lze jen fakturu ve stavu Potvrzená odběratelem.")
    apply_fee_and_advance(db, inv)
    transition_invoice(db, inv, InvoiceStatus.PURCHASED.value)


def record_assignment(db: Session, inv: Invoice, note: str | None = None) -> None:
    settings_service.log_audit(
        db,
        action="invoice_assigned",
        entity_type="invoice",
        entity_id=inv.id,
        detail=note or "",
    )
