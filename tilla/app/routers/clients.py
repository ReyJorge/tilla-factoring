from datetime import date
from io import StringIO

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.constants import INVOICE_STATUS_LABELS_CS
from app.models import Client, ClientSetting, Contact, Debtor, Invoice, InvoiceStatus, User
from app.services import finance_service, invoice_service, risk_service, settings_service
from app.template_helpers import add_flash, template_ctx, templates

router = APIRouter(tags=["clients"])


def client_summary(db: Session, client: Client) -> dict:
    invs = client.invoices
    sums: dict[str, float] = {}
    advances: dict[str, float] = {}
    active_adv = {
        InvoiceStatus.PURCHASED.value,
        InvoiceStatus.ADVANCE_FINANCED.value,
        InvoiceStatus.AWAITING_COLLECTION.value,
        InvoiceStatus.PARTIALLY_PAID.value,
        InvoiceStatus.OVERDUE.value,
    }
    for inv in invs:
        sums[inv.currency] = sums.get(inv.currency, 0.0) + float(inv.amount)
        if inv.status in active_adv:
            advances[inv.currency] = advances.get(inv.currency, 0.0) + float(inv.advance_amount or 0)
    offset_total = sum(float(o.amount_czk) for o in client.offsets)
    return {
        "invoice_count": len(invs),
        "sums": sums,
        "advances": advances,
        "offsets_czk": offset_total,
        "open_exposure": invoice_service.client_open_exposure(db, client.id),
    }


def paired_settings_table(db: Session, client: Client) -> list[dict]:
    gmap = settings_service.global_map(db)
    cmap = {r.key: r.value for r in client.settings_rows}
    rows_out = []
    for key, _kind, label in settings_service.SETTING_KEYS:
        rows_out.append(
            {
                "key": key,
                "label": label,
                "global_value": gmap.get(key, ""),
                "client_value": cmap.get(key),
                "field_name": "client_" + key.replace(".", "_"),
            }
        )
    return rows_out


@router.get("/clients")
def list_clients(request: Request, db: Session = Depends(get_db)):
    rows = db.query(Client).order_by(Client.name.asc()).all()
    enriched = [(c, client_summary(db, c)) for c in rows]
    return templates.TemplateResponse(
        "clients/list.html",
        template_ctx(request, nav_active="clients", clients=enriched),
    )


@router.get("/clients/{client_id}")
def client_detail(
    client_id: int,
    request: Request,
    db: Session = Depends(get_db),
    inv_filter: str | None = None,
):
    client = db.get(Client, client_id)
    if not client:
        raise HTTPException(status_code=404)
    today = date.today()
    for inv in client.invoices:
        invoice_service.refresh_auto_overdue(db, inv, today)
    db.commit()
    invoices_sorted = sorted(client.invoices, key=lambda x: x.due_date, reverse=True)
    invoices_filtered = _filter_invoices(invoices_sorted, inv_filter)
    debtor_ids = {inv.debtor_id for inv in client.invoices}
    debtor_risk: dict[int, str] = {}
    for did in debtor_ids:
        chk = risk_service.latest_check(db, did)
        debtor_risk[did] = chk.result if chk else "—"
    return templates.TemplateResponse(
        "clients/detail.html",
        template_ctx(
            request,
            nav_active="clients",
            client=client,
            summary=client_summary(db, client),
            settings_table=paired_settings_table(db, client),
            invoices=invoices_filtered,
            inv_filter=inv_filter or "",
            debtor_risk=debtor_risk,
            status_labels=INVOICE_STATUS_LABELS_CS,
            InvoiceStatus=InvoiceStatus,
            today=today,
        ),
    )


@router.get("/clients/{client_id}/edit")
def client_edit_form(client_id: int, request: Request, db: Session = Depends(get_db)):
    client = db.get(Client, client_id)
    if not client:
        raise HTTPException(status_code=404)
    users = db.query(User).order_by(User.full_name.asc()).all()
    return templates.TemplateResponse(
        "clients/edit.html",
        template_ctx(
            request,
            nav_active="clients",
            client=client,
            users=users,
            settings_table=paired_settings_table(db, client),
        ),
    )


@router.post("/clients/{client_id}/edit")
def client_edit_save(
    client_id: int,
    request: Request,
    db: Session = Depends(get_db),
    contract_number: str = Form(...),
    ic: str = Form(...),
    name: str = Form(...),
    short_name: str = Form(...),
    dic: str | None = Form(None),
    communication_language: str = Form("cs"),
    email: str = Form(...),
    bank_account_number: str | None = Form(None),
    bank_code: str | None = Form(None),
    iban: str | None = Form(None),
    swift: str | None = Form(None),
    salutation: str | None = Form(None),
    responsible_user_id: int | None = Form(None),
    headquarters: str | None = Form(None),
):
    client = db.get(Client, client_id)
    if not client:
        raise HTTPException(status_code=404)
    client.contract_number = contract_number.strip()
    client.ic = ic.strip()
    client.name = name.strip()
    client.short_name = short_name.strip()
    client.dic = (dic or "").strip() or None
    client.communication_language = communication_language
    client.email = email.strip()
    client.headquarters = (headquarters or "").strip() or None
    client.bank_account_number = (bank_account_number or "").strip() or None
    client.bank_code = (bank_code or "").strip() or None
    client.iban = (iban or "").strip() or None
    client.swift = (swift or "").strip() or None
    client.salutation = (salutation or "").strip() or None
    client.responsible_user_id = responsible_user_id or None
    settings_service.log_audit(db, action="client_update", entity_type="client", entity_id=client_id)
    db.commit()
    add_flash(request, "Klient uložen.")
    return RedirectResponse(url=f"/clients/{client_id}", status_code=303)


@router.post("/clients/{client_id}/contacts/add")
def client_add_contact(
    client_id: int,
    request: Request,
    db: Session = Depends(get_db),
    name: str = Form(...),
    contact_email: str | None = Form(None),
    phone: str | None = Form(None),
    role_label: str | None = Form(None),
):
    client = db.get(Client, client_id)
    if not client:
        raise HTTPException(status_code=404)
    db.add(
        Contact(
            client_id=client_id,
            name=name.strip(),
            email=(contact_email or "").strip() or None,
            phone=(phone or "").strip() or None,
            role_label=(role_label or "").strip() or None,
        )
    )
    db.commit()
    add_flash(request, "Kontakt přidán.")
    return RedirectResponse(url=f"/clients/{client_id}/edit", status_code=303)


@router.post("/clients/{client_id}/settings/save")
async def client_settings_save(client_id: int, request: Request, db: Session = Depends(get_db)):
    client = db.get(Client, client_id)
    if not client:
        raise HTTPException(status_code=404)
    form = await request.form()
    existing = {r.key: r for r in client.settings_rows}
    for key, _kind, _label in settings_service.SETTING_KEYS:
        fname = "client_" + key.replace(".", "_")
        if fname not in form:
            continue
        raw = str(form[fname]).strip()
        if raw == "" or raw.lower() == "inherit":
            if key in existing:
                db.delete(existing[key])
            continue
        if key in existing:
            existing[key].value = raw
        else:
            db.add(ClientSetting(client_id=client_id, key=key, value=raw))
    db.commit()
    add_flash(request, "Nastavení klienta uloženo.")
    return RedirectResponse(url=f"/clients/{client_id}/edit", status_code=303)


def _filter_invoices(invoices: list[Invoice], mode: str | None) -> list[Invoice]:
    today = date.today()
    if mode == "overdue":
        return [i for i in invoices if i.due_date < today and i.status != InvoiceStatus.FULLY_SETTLED.value]
    if mode == "before_due":
        return [i for i in invoices if i.due_date >= today]
    if mode == "pending_confirm":
        return [i for i in invoices if i.status == InvoiceStatus.PENDING_DEBTOR_CONFIRM.value]
    if mode == "problem":
        return [i for i in invoices if i.status == InvoiceStatus.PROBLEM.value]
    if mode == "archive":
        return [i for i in invoices if i.status == InvoiceStatus.FULLY_SETTLED.value]
    if mode == "new_purchased":
        return [
            i
            for i in invoices
            if i.status
            in {
                InvoiceStatus.NEW.value,
                InvoiceStatus.PURCHASED.value,
                InvoiceStatus.ADVANCE_FINANCED.value,
                InvoiceStatus.AWAITING_COLLECTION.value,
            }
        ]
    if mode == "purchased":
        return [
            i
            for i in invoices
            if i.status
            in {
                InvoiceStatus.PURCHASED.value,
                InvoiceStatus.ADVANCE_FINANCED.value,
                InvoiceStatus.AWAITING_COLLECTION.value,
            }
        ]
    return invoices


@router.get("/clients/{client_id}/invoices")
def client_invoices(
    client_id: int,
    request: Request,
    db: Session = Depends(get_db),
    quick: str | None = None,
):
    client = db.get(Client, client_id)
    if not client:
        raise HTTPException(status_code=404)
    today = date.today()
    for inv in client.invoices:
        invoice_service.refresh_auto_overdue(db, inv, today)
    db.commit()
    invoices_sorted = sorted(client.invoices, key=lambda x: x.due_date, reverse=True)
    invoices_filtered = _filter_invoices(invoices_sorted, quick)
    debtors = db.query(Debtor).order_by(Debtor.name.asc()).limit(500).all()
    debtor_ids = {inv.debtor_id for inv in client.invoices}
    debtor_risk: dict[int, str] = {}
    for did in debtor_ids:
        chk = risk_service.latest_check(db, did)
        debtor_risk[did] = chk.result if chk else "—"
    return templates.TemplateResponse(
        "clients/invoices.html",
        template_ctx(
            request,
            nav_active="clients",
            client=client,
            invoices=invoices_filtered,
            quick=quick or "",
            summary=client_summary(db, client),
            status_labels=INVOICE_STATUS_LABELS_CS,
            InvoiceStatus=InvoiceStatus,
            today=today,
            debtors=debtors,
            debtor_risk=debtor_risk,
        ),
    )


@router.post("/clients/{client_id}/invoices/create")
def invoice_create(
    client_id: int,
    request: Request,
    db: Session = Depends(get_db),
    debtor_id: int = Form(...),
    variable_symbol: str = Form(...),
    invoice_number: str | None = Form(None),
    amount: float = Form(...),
    currency: str = Form(...),
    issued_date: date = Form(...),
    submitted_date: date = Form(...),
    due_date: date = Form(...),
    note: str | None = Form(None),
):
    client = db.get(Client, client_id)
    debtor = db.get(Debtor, debtor_id)
    if not client or not debtor:
        raise HTTPException(status_code=404)
    inv = Invoice(
        client_id=client_id,
        debtor_id=debtor_id,
        variable_symbol=variable_symbol.strip(),
        invoice_number=(invoice_number or "").strip() or None,
        amount=amount,
        currency=currency.strip().upper(),
        issued_date=issued_date,
        submitted_date=submitted_date,
        due_date=due_date,
        note=(note or "").strip() or None,
        status=InvoiceStatus.NEW.value,
    )
    invoice_service.apply_fee_and_advance(db, inv)
    db.add(inv)
    db.flush()
    settings_service.log_audit(db, action="invoice_create", entity_type="invoice", entity_id=inv.id)
    db.commit()
    add_flash(request, "Nová faktura založena.")
    return RedirectResponse(url=f"/clients/{client_id}/invoices", status_code=303)


@router.get("/clients/{client_id}/invoices/export")
def export_client_invoices(client_id: int, db: Session = Depends(get_db)):
    client = db.get(Client, client_id)
    if not client:
        raise HTTPException(status_code=404)
    buf = StringIO()
    buf.write(
        "id;vs;debtor;status;issued;due;days_to_due;amount;currency;fee;advance\n"
    )
    today = date.today()
    for inv in sorted(client.invoices, key=lambda x: x.id):
        dd = invoice_service.days_relative_to_due(inv, today)
        buf.write(
            f"{inv.id};{inv.variable_symbol};{inv.debtor.name};{inv.status};"
            f"{inv.issued_date};{inv.due_date};{dd};{inv.amount};{inv.currency};"
            f"{inv.fee_percent};{inv.advance_amount}\n"
        )
    data = buf.getvalue().encode("utf-8")
    headers = {"Content-Disposition": f'attachment; filename="tilla_client_{client_id}_invoices.csv"'}
    return StreamingResponse(iter([data]), media_type="text/csv", headers=headers)


@router.get("/clients/{client_id}/setoffs")
def client_setoffs(client_id: int, request: Request, db: Session = Depends(get_db)):
    client = db.get(Client, client_id)
    if not client:
        raise HTTPException(status_code=404)
    agg = finance_service.offset_client_totals(db, client_id)
    return templates.TemplateResponse(
        "clients/setoffs.html",
        template_ctx(request, nav_active="finance", client=client, agg=agg),
    )


@router.post("/clients/{client_id}/setoffs/manual")
def client_setoffs_manual(
    client_id: int,
    request: Request,
    db: Session = Depends(get_db),
    movement_date: date = Form(...),
    description: str = Form(...),
    original_amount: float = Form(...),
    original_currency: str = Form(...),
    fx_rate_to_czk: float = Form(...),
    interest_bearing: str = Form("yes"),
    invoice_id: int | None = Form(None),
):
    client = db.get(Client, client_id)
    if not client:
        raise HTTPException(status_code=404)
    finance_service.add_manual_offset(
        db,
        client_id=client_id,
        movement_date=movement_date,
        description=description,
        original_amount=original_amount,
        original_currency=original_currency.strip().upper(),
        fx_rate_to_czk=fx_rate_to_czk,
        interest_bearing=interest_bearing == "yes",
        invoice_id=invoice_id,
    )
    db.commit()
    add_flash(request, "Pohyb přidán.")
    return RedirectResponse(url=f"/clients/{client_id}/setoffs", status_code=303)
