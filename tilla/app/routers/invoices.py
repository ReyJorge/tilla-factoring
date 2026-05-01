import shutil
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from sqlalchemy import or_

from app.constants import INVOICE_STATUS_LABELS_CS as STATUS_LABELS_CS
from app.database import get_db
from app.models import EmailLog, Invoice, InvoiceFile, InvoiceStatus, Payment, TaxDocument
from app.services import finance_service, invoice_service, settings_service
from app.template_helpers import add_flash, template_ctx, templates, uploads_dir

router = APIRouter(tags=["invoices"])


@router.get("/invoices/{invoice_id}")
def invoice_detail(invoice_id: int, request: Request, db: Session = Depends(get_db)):
    inv = db.get(Invoice, invoice_id)
    if not inv:
        raise HTTPException(status_code=404)
    invoice_service.refresh_auto_overdue(db, inv)
    db.commit()
    payments = sorted(inv.payments, key=lambda p: p.payment_date, reverse=True)
    unmatched_for_inv = (
        db.query(Payment)
        .filter(Payment.matched_invoice_id.is_(None))
        .filter(or_(Payment.probable_invoice_id == invoice_id, Payment.currency == inv.currency))
        .order_by(Payment.payment_date.desc())
        .limit(40)
        .all()
    )
    return templates.TemplateResponse(
        "invoices/detail.html",
        template_ctx(
            request,
            nav_active="clients",
            invoice=inv,
            status_labels=STATUS_LABELS_CS,
            payments=payments,
            unmatched_for_inv=unmatched_for_inv,
            days=invoice_service.days_relative_to_due(inv),
            InvoiceStatus=InvoiceStatus,
        ),
    )


@router.post("/invoices/{invoice_id}/payment-match")
def invoice_payment_match(
    invoice_id: int,
    request: Request,
    db: Session = Depends(get_db),
    payment_id: int = Form(...),
):
    try:
        finance_service.match_payment(db, payment_id, invoice_id)
        db.commit()
        add_flash(request, "Platba spárována s fakturou.")
    except ValueError as e:
        db.rollback()
        add_flash(request, str(e))
    return RedirectResponse(url=f"/invoices/{invoice_id}", status_code=303)


@router.get("/invoices/{invoice_id}/edit")
def invoice_edit_form(invoice_id: int, request: Request, db: Session = Depends(get_db)):
    inv = db.get(Invoice, invoice_id)
    if not inv:
        raise HTTPException(status_code=404)
    unmatched_for_inv = (
        db.query(Payment)
        .filter(Payment.matched_invoice_id.is_(None))
        .filter(or_(Payment.probable_invoice_id == invoice_id, Payment.currency == inv.currency))
        .order_by(Payment.payment_date.desc())
        .limit(40)
        .all()
    )
    return templates.TemplateResponse(
        "invoices/edit.html",
        template_ctx(
            request,
            nav_active="clients",
            invoice=inv,
            status_labels=STATUS_LABELS_CS,
            unmatched_for_inv=unmatched_for_inv,
        ),
    )


@router.post("/invoices/{invoice_id}/edit")
def invoice_edit_save(
    invoice_id: int,
    request: Request,
    db: Session = Depends(get_db),
    variable_symbol: str = Form(...),
    invoice_number: str | None = Form(None),
    amount: float = Form(...),
    currency: str = Form(...),
    issued_date: str = Form(...),
    submitted_date: str = Form(...),
    due_date: str = Form(...),
    note: str | None = Form(None),
):
    from datetime import date as dt_date

    inv = db.get(Invoice, invoice_id)
    if not inv:
        raise HTTPException(status_code=404)

    def parse_d(s: str) -> dt_date:
        return dt_date.fromisoformat(s)

    inv.variable_symbol = variable_symbol.strip()
    inv.invoice_number = (invoice_number or "").strip() or None
    inv.amount = amount
    inv.currency = currency.strip().upper()
    inv.issued_date = parse_d(issued_date)
    inv.submitted_date = parse_d(submitted_date)
    inv.due_date = parse_d(due_date)
    inv.note = (note or "").strip() or None
    invoice_service.apply_fee_and_advance(db, inv)
    settings_service.log_audit(db, action="invoice_update", entity_type="invoice", entity_id=invoice_id)
    db.commit()
    add_flash(request, "Faktura uložena.")
    return RedirectResponse(url=f"/invoices/{invoice_id}", status_code=303)


@router.post("/invoices/{invoice_id}/delete")
def invoice_delete(invoice_id: int, request: Request, db: Session = Depends(get_db)):
    inv = db.get(Invoice, invoice_id)
    if not inv:
        raise HTTPException(status_code=404)
    cid = inv.client_id
    db.delete(inv)
    settings_service.log_audit(db, action="invoice_delete", entity_type="invoice", entity_id=invoice_id)
    db.commit()
    add_flash(request, "Faktura smazána.")
    return RedirectResponse(url=f"/clients/{cid}/invoices", status_code=303)


@router.post("/invoices/{invoice_id}/purchase")
def invoice_purchase(invoice_id: int, request: Request, db: Session = Depends(get_db)):
    inv = db.get(Invoice, invoice_id)
    if not inv:
        raise HTTPException(status_code=404)
    try:
        invoice_service.purchase_invoice(db, inv)
        db.commit()
        add_flash(request, "Faktura odkoupena.")
    except ValueError as e:
        db.rollback()
        add_flash(request, str(e))
    return RedirectResponse(url=f"/invoices/{invoice_id}", status_code=303)


@router.post("/invoices/{invoice_id}/finalize")
def invoice_finalize(invoice_id: int, request: Request, db: Session = Depends(get_db)):
    inv = db.get(Invoice, invoice_id)
    if not inv:
        raise HTTPException(status_code=404)
    try:
        invoice_service.finalize_if_collected(db, inv)
        db.commit()
        add_flash(request, "Faktura finalizována.")
    except ValueError as e:
        db.rollback()
        add_flash(request, str(e))
    return RedirectResponse(url=f"/invoices/{invoice_id}", status_code=303)


@router.post("/invoices/{invoice_id}/assign")
def invoice_assign(
    invoice_id: int,
    request: Request,
    db: Session = Depends(get_db),
    assign_note: str = Form(""),
):
    inv = db.get(Invoice, invoice_id)
    if not inv:
        raise HTTPException(status_code=404)
    invoice_service.record_assignment(db, inv, assign_note)
    db.commit()
    add_flash(request, "Postoupení zaznamenáno v audit logu.")
    return RedirectResponse(url=f"/invoices/{invoice_id}", status_code=303)


@router.post("/invoices/{invoice_id}/advance")
def invoice_advance_step(invoice_id: int, request: Request, db: Session = Depends(get_db)):
    inv = db.get(Invoice, invoice_id)
    if not inv:
        raise HTTPException(status_code=404)
    try:
        invoice_service.transition_invoice(db, inv, InvoiceStatus.ADVANCE_FINANCED.value)
        db.commit()
        add_flash(request, "Stav: záloha profinancována.")
    except ValueError as e:
        db.rollback()
        add_flash(request, str(e))
    return RedirectResponse(url=f"/invoices/{invoice_id}", status_code=303)


@router.post("/invoices/{invoice_id}/await-collection")
def invoice_await_collection(invoice_id: int, request: Request, db: Session = Depends(get_db)):
    inv = db.get(Invoice, invoice_id)
    if not inv:
        raise HTTPException(status_code=404)
    try:
        invoice_service.transition_invoice(db, inv, InvoiceStatus.AWAITING_COLLECTION.value)
        db.commit()
        add_flash(request, "Čeká na inkaso.")
    except ValueError as e:
        db.rollback()
        add_flash(request, str(e))
    return RedirectResponse(url=f"/invoices/{invoice_id}", status_code=303)


@router.post("/invoices/{invoice_id}/workflow")
def invoice_workflow(
    invoice_id: int,
    request: Request,
    db: Session = Depends(get_db),
    step: str = Form(...),
):
    inv = db.get(Invoice, invoice_id)
    if not inv:
        raise HTTPException(status_code=404)
    targets = {
        "to_check": InvoiceStatus.PENDING_CHECK.value,
        "to_debtor_pending": InvoiceStatus.PENDING_DEBTOR_CONFIRM.value,
        "debtor_confirmed": InvoiceStatus.DEBTOR_CONFIRMED.value,
        "problem": InvoiceStatus.PROBLEM.value,
        "recover_collection": InvoiceStatus.AWAITING_COLLECTION.value,
        "recover_review": InvoiceStatus.PENDING_CHECK.value,
    }
    target = targets.get(step)
    if not target:
        add_flash(request, "Neznámá akce.")
        return RedirectResponse(url=f"/invoices/{invoice_id}", status_code=303)
    try:
        invoice_service.transition_invoice(db, inv, target)
        db.commit()
        add_flash(request, "Workflow aktualizován.")
    except ValueError as e:
        db.rollback()
        add_flash(request, str(e))
    return RedirectResponse(url=f"/invoices/{invoice_id}", status_code=303)


@router.post("/invoices/{invoice_id}/reminder")
def invoice_reminder(invoice_id: int, request: Request, db: Session = Depends(get_db)):
    inv = db.get(Invoice, invoice_id)
    if not inv:
        raise HTTPException(status_code=404)
    invoice_service.simulate_reminder_sent(db, inv)
    db.commit()
    add_flash(request, "Upomínka simulována (odeslána).")
    return RedirectResponse(url=f"/invoices/{invoice_id}", status_code=303)


@router.post("/invoices/{invoice_id}/upload")
async def invoice_upload(
    invoice_id: int,
    request: Request,
    db: Session = Depends(get_db),
    file_type: str = Form("other"),
    file: UploadFile = File(...),
):
    inv = db.get(Invoice, invoice_id)
    if not inv:
        raise HTTPException(status_code=404)
    safe_name = Path(file.filename or "upload.bin").name
    target_dir = uploads_dir() / str(invoice_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    dest = target_dir / safe_name
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    rel = f"uploads/{invoice_id}/{safe_name}"
    db.add(
        InvoiceFile(
            invoice_id=invoice_id,
            file_type=file_type,
            original_filename=safe_name,
            stored_path=rel,
        )
    )
    settings_service.log_audit(db, action="invoice_file_upload", entity_type="invoice", entity_id=invoice_id)
    db.commit()
    add_flash(request, "Soubor uložen.")
    return RedirectResponse(url=f"/invoices/{invoice_id}/edit", status_code=303)


@router.post("/invoices/{invoice_id}/tax/add")
def invoice_tax_add(
    invoice_id: int,
    request: Request,
    db: Session = Depends(get_db),
    issued_date: str = Form(...),
    tax_supply_date: str = Form(...),
    base_amount: float = Form(...),
    total_amount: float = Form(...),
    currency: str = Form(...),
):
    from datetime import date as dt_date

    inv = db.get(Invoice, invoice_id)
    if not inv:
        raise HTTPException(status_code=404)

    def pd(s: str) -> dt_date:
        return dt_date.fromisoformat(s)

    db.add(
        TaxDocument(
            invoice_id=invoice_id,
            doc_type="normal",
            variable_symbol=inv.variable_symbol,
            issued_date=pd(issued_date),
            tax_supply_date=pd(tax_supply_date),
            base_amount=base_amount,
            total_amount=total_amount,
            currency=currency.strip().upper(),
        )
    )
    db.commit()
    add_flash(request, "Daňový doklad přidán.")
    return RedirectResponse(url=f"/invoices/{invoice_id}/edit", status_code=303)


@router.post("/invoices/{invoice_id}/email/simulate")
def invoice_email_simulate(
    invoice_id: int,
    request: Request,
    db: Session = Depends(get_db),
    recipients: str = Form(...),
    subject: str = Form(...),
):
    inv = db.get(Invoice, invoice_id)
    if not inv:
        raise HTTPException(status_code=404)
    db.add(
        EmailLog(
            invoice_id=invoice_id,
            sent_at=datetime.utcnow(),
            recipients=recipients,
            subject=subject,
            attachments_summary=None,
            error_message=None,
        )
    )
    db.commit()
    add_flash(request, "Email zalogován.")
    return RedirectResponse(url=f"/invoices/{invoice_id}/edit", status_code=303)
