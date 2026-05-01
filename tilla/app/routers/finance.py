from datetime import date

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    AdvanceInterestLine,
    BankStatement,
    InsuranceRecord,
    Invoice,
    InvoiceStatus,
    Payment,
    PaymentBatch,
    Reminder,
    TaxDocument,
)
from app.services import dashboard_service, finance_service, invoice_service
from app.template_helpers import add_flash, template_ctx, templates

router = APIRouter(tags=["finance"], prefix="/finance")


@router.get("/payments")
def finance_payments(request: Request, db: Session = Depends(get_db)):
    rows = db.query(Payment).order_by(Payment.payment_date.desc()).limit(400).all()
    return templates.TemplateResponse(
        "finance/payments.html",
        template_ctx(request, nav_active="finance", payments=rows),
    )


@router.get("/unmatched-payments")
def finance_unmatched(request: Request, db: Session = Depends(get_db)):
    rows = finance_service.list_unmatched(db)
    inv_candidates = (
        db.query(Invoice)
        .filter(Invoice.status != InvoiceStatus.FULLY_SETTLED.value)
        .order_by(Invoice.due_date.desc())
        .limit(400)
        .all()
    )
    return templates.TemplateResponse(
        "finance/unmatched.html",
        template_ctx(request, nav_active="finance", payments=rows, invoices=inv_candidates),
    )


@router.post("/unmatched-payments/match")
def finance_match(
    request: Request,
    db: Session = Depends(get_db),
    payment_id: int = Form(...),
    invoice_id: int = Form(...),
):
    try:
        finance_service.match_payment(db, payment_id, invoice_id)
        db.commit()
        add_flash(request, "Platba spárována.")
    except ValueError as e:
        db.rollback()
        add_flash(request, str(e))
    return RedirectResponse(url="/finance/unmatched-payments", status_code=303)


@router.get("/overdue-invoices")
def finance_overdue_invoices(request: Request, db: Session = Depends(get_db)):
    today = date.today()
    for inv in db.query(Invoice).all():
        invoice_service.refresh_auto_overdue(db, inv, today)
    db.commit()
    rows = (
        db.query(Invoice)
        .filter(Invoice.due_date < today, Invoice.status != InvoiceStatus.FULLY_SETTLED.value)
        .order_by(Invoice.due_date.asc())
        .limit(500)
        .all()
    )
    return templates.TemplateResponse(
        "finance/overdue_invoices.html",
        template_ctx(request, nav_active="finance", invoices=rows, today=today),
    )


@router.get("/finalize-candidates")
def finance_finalize_candidates(request: Request, db: Session = Depends(get_db)):
    rows = dashboard_service.finalize_candidates(db, limit=None)[:120]
    return templates.TemplateResponse(
        "finance/finalize_candidates.html",
        template_ctx(request, nav_active="finance", invoices=rows),
    )


@router.get("/reminders-due")
def finance_reminders_due(request: Request, db: Session = Depends(get_db)):
    today = date.today()
    rows = (
        db.query(Reminder)
        .filter(Reminder.sent_at.is_(None), Reminder.scheduled_for <= today)
        .order_by(Reminder.scheduled_for.asc())
        .limit(300)
        .all()
    )
    return templates.TemplateResponse(
        "finance/reminders_due.html",
        template_ctx(request, nav_active="finance", reminders=rows, today=today),
    )


@router.get("/settlement")
def finance_settlement(request: Request, db: Session = Depends(get_db)):
    agg = finance_service.settlement_global_aggregate(db)
    return templates.TemplateResponse(
        "finance/settlement.html",
        template_ctx(request, nav_active="finance", agg=agg),
    )


@router.get("/payment-batches")
def finance_batches(request: Request, db: Session = Depends(get_db)):
    rows = db.query(PaymentBatch).order_by(PaymentBatch.batch_date.desc()).all()
    return templates.TemplateResponse(
        "finance/batches.html",
        template_ctx(request, nav_active="finance", batches=rows),
    )


@router.get("/bank-statements")
def finance_bank_statements(request: Request, db: Session = Depends(get_db)):
    rows = db.query(BankStatement).order_by(BankStatement.period_to.desc()).all()
    return templates.TemplateResponse(
        "finance/statements.html",
        template_ctx(request, nav_active="finance", statements=rows),
    )


@router.get("/tax-documents")
def finance_tax_documents(request: Request, db: Session = Depends(get_db)):
    rows = db.query(TaxDocument).order_by(TaxDocument.issued_date.desc()).limit(500).all()
    totals = {"CZK": {"base": 0.0, "total": 0.0}, "EUR": {"base": 0.0, "total": 0.0}}
    for r in rows:
        totals[r.currency]["base"] += float(r.base_amount)
        totals[r.currency]["total"] += float(r.total_amount)
    return templates.TemplateResponse(
        "finance/tax_documents.html",
        template_ctx(request, nav_active="finance", rows=rows, totals=totals),
    )


@router.get("/advance-interest")
def finance_advance_interest(request: Request, db: Session = Depends(get_db)):
    rows = db.query(AdvanceInterestLine).order_by(AdvanceInterestLine.period_month.desc()).limit(400).all()
    return templates.TemplateResponse(
        "finance/advance_interest.html",
        template_ctx(request, nav_active="finance", rows=rows),
    )


@router.get("/insurance-reports")
def finance_insurance_reports(request: Request, db: Session = Depends(get_db)):
    rows = db.query(InsuranceRecord).order_by(InsuranceRecord.valid_from.desc()).all()
    return templates.TemplateResponse(
        "finance/insurance.html",
        template_ctx(request, nav_active="finance", rows=rows),
    )


@router.get("/overdue-insured")
def finance_overdue_insured(request: Request, db: Session = Depends(get_db)):
    today = date.today()
    q = []
    for inv in db.query(Invoice).filter(Invoice.due_date < today).all():
        if inv.status == InvoiceStatus.FULLY_SETTLED.value:
            continue
        if inv.debtor.insurance_amount and float(inv.debtor.insurance_amount) > 0:
            q.append(inv)
    q.sort(key=lambda x: x.due_date)
    return templates.TemplateResponse(
        "finance/overdue_insured.html",
        template_ctx(request, nav_active="finance", invoices=q[:200]),
    )


@router.get("/collections")
def finance_collections(request: Request, db: Session = Depends(get_db)):
    rows = (
        db.query(Payment)
        .filter(Payment.matched_invoice_id.is_not(None))
        .order_by(Payment.payment_date.desc())
        .limit(400)
        .all()
    )
    return templates.TemplateResponse(
        "finance/collections.html",
        template_ctx(request, nav_active="finance", payments=rows),
    )
