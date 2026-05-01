from __future__ import annotations

import enum
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class UserRole(str, enum.Enum):
    SUPERADMIN = "superadmin"
    USER = "user"
    OWNER = "owner"


class InvoiceStatus(str, enum.Enum):
    NEW = "new"
    PENDING_CHECK = "pending_check"
    PENDING_DEBTOR_CONFIRM = "pending_debtor_confirm"
    DEBTOR_CONFIRMED = "debtor_confirmed"
    PURCHASED = "purchased"
    ADVANCE_FINANCED = "advance_financed"
    AWAITING_COLLECTION = "awaiting_collection"
    PARTIALLY_PAID = "partially_paid"
    FULLY_SETTLED = "fully_settled"
    OVERDUE = "overdue"
    PROBLEM = "problem"


class RiskResult(str, enum.Enum):
    OK = "OK"
    WARNING = "WARNING"
    BLOCK = "BLOCK"


class ProtocolFlag(str, enum.Enum):
    OK = "OK"
    ISSUE = "ISSUE"
    UNKNOWN = "UNKNOWN"


class InvoiceFileType(str, enum.Enum):
    CMR = "cmr"
    ORDER = "order"
    ISSUED_INVOICE = "issued_invoice"
    OTHER = "other"


class OffsetSignificance(str, enum.Enum):
    OK = "ok"
    ATTENTION = "attention"
    PROBLEM = "problem"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    role: Mapped[str] = mapped_column(String(40), default=UserRole.USER.value)
    signature_cz: Mapped[str | None] = mapped_column(Text, nullable=True)
    signature_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    managed_clients: Mapped[list["Client"]] = relationship(
        back_populates="responsible_user"
    )


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    contract_number: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    ic: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    short_name: Mapped[str] = mapped_column(String(80), nullable=False)
    dic: Mapped[str | None] = mapped_column(String(30), nullable=True)
    charge_vat: Mapped[bool] = mapped_column(Boolean, default=True)
    entity_type: Mapped[str] = mapped_column(String(40), default="legal")
    communication_language: Mapped[str] = mapped_column(String(8), default="cs")
    email: Mapped[str] = mapped_column(String(160), nullable=False)
    bank_account_number: Mapped[str | None] = mapped_column(String(34), nullable=True)
    bank_code: Mapped[str | None] = mapped_column(String(16), nullable=True)
    iban: Mapped[str | None] = mapped_column(String(34), nullable=True)
    swift: Mapped[str | None] = mapped_column(String(16), nullable=True)
    salutation: Mapped[str | None] = mapped_column(String(255), nullable=True)
    responsible_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    responsible_user: Mapped[User | None] = relationship(back_populates="managed_clients")
    contacts: Mapped[list["Contact"]] = relationship(
        back_populates="client", cascade="all, delete-orphan"
    )
    invoices: Mapped[list["Invoice"]] = relationship(back_populates="client")
    settings_rows: Mapped[list["ClientSetting"]] = relationship(
        back_populates="client", cascade="all, delete-orphan"
    )
    offsets: Mapped[list["OffsetEntry"]] = relationship(back_populates="client")


class Contact(Base):
    __tablename__ = "contacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    email: Mapped[str | None] = mapped_column(String(160), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    role_label: Mapped[str | None] = mapped_column(String(80), nullable=True)

    client: Mapped[Client] = relationship(back_populates="contacts")


class Debtor(Base):
    __tablename__ = "debtors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    ic: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    email: Mapped[str | None] = mapped_column(String(160), nullable=True)
    country_code: Mapped[str] = mapped_column(String(2), default="CZ")
    insurance_amount: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    insurance_from: Mapped[date | None] = mapped_column(Date, nullable=True)

    invoices: Mapped[list["Invoice"]] = relationship(back_populates="debtor")
    risk_checks: Mapped[list["RiskCheck"]] = relationship(back_populates="debtor")
    insurance_records: Mapped[list["InsuranceRecord"]] = relationship(back_populates="debtor")


class Invoice(Base):
    __tablename__ = "invoices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), nullable=False)
    debtor_id: Mapped[int] = mapped_column(ForeignKey("debtors.id"), nullable=False)
    variable_symbol: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    invoice_number: Mapped[str | None] = mapped_column(String(60), nullable=True)
    amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    fee_percent: Mapped[float] = mapped_column(Numeric(6, 3), default=0)
    advance_amount: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    issued_date: Mapped[date] = mapped_column(Date, nullable=False)
    submitted_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    purchased_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    collected_amount: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    status: Mapped[str] = mapped_column(String(40), default=InvoiceStatus.NEW.value, index=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reminder_level: Mapped[int] = mapped_column(Integer, default=0)

    client: Mapped[Client] = relationship(back_populates="invoices")
    debtor: Mapped[Debtor] = relationship(back_populates="invoices")
    files: Mapped[list["InvoiceFile"]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan"
    )
    payments: Mapped[list["Payment"]] = relationship(back_populates="invoice")
    reminders: Mapped[list["Reminder"]] = relationship(back_populates="invoice")
    tax_documents: Mapped[list["TaxDocument"]] = relationship(back_populates="invoice")
    emails: Mapped[list["EmailLog"]] = relationship(back_populates="invoice")


class InvoiceFile(Base):
    __tablename__ = "invoice_files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"), nullable=False)
    file_type: Mapped[str] = mapped_column(String(32), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_path: Mapped[str] = mapped_column(String(512), nullable=False)

    invoice: Mapped[Invoice] = relationship(back_populates="files")


class PaymentBatch(Base):
    __tablename__ = "payment_batches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    reference: Mapped[str] = mapped_column(String(80), nullable=False)
    batch_date: Mapped[date] = mapped_column(Date, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    payments: Mapped[list["Payment"]] = relationship(back_populates="batch")


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_id: Mapped[int | None] = mapped_column(ForeignKey("payment_batches.id"), nullable=True)
    amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    payer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    payment_date: Mapped[date] = mapped_column(Date, nullable=False)
    matched_invoice_id: Mapped[int | None] = mapped_column(ForeignKey("invoices.id"), nullable=True)
    variable_symbol_hint: Mapped[str | None] = mapped_column(String(40), nullable=True)

    batch: Mapped[PaymentBatch | None] = relationship(back_populates="payments")
    invoice: Mapped[Invoice | None] = relationship(back_populates="payments")


class RiskCheck(Base):
    __tablename__ = "risk_checks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    debtor_id: Mapped[int] = mapped_column(ForeignKey("debtors.id"), nullable=False)
    checked_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    result: Mapped[str] = mapped_column(String(16), nullable=False)
    protocol_insolvency: Mapped[str] = mapped_column(String(16), default=ProtocolFlag.OK.value)
    protocol_taxpayer: Mapped[str] = mapped_column(String(16), default=ProtocolFlag.OK.value)
    protocol_execution: Mapped[str] = mapped_column(String(16), default=ProtocolFlag.OK.value)
    protocol_cese: Mapped[str] = mapped_column(String(16), default=ProtocolFlag.OK.value)
    protocol_rating: Mapped[str] = mapped_column(String(16), default=ProtocolFlag.OK.value)

    debtor: Mapped[Debtor] = relationship(back_populates="risk_checks")


class GlobalSetting(Base):
    __tablename__ = "global_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    value: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)


class ClientSetting(Base):
    __tablename__ = "client_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), nullable=False)
    key: Mapped[str] = mapped_column(String(80), nullable=False)
    value: Mapped[str | None] = mapped_column(String(255), nullable=True)

    client: Mapped[Client] = relationship(back_populates="settings_rows")


class OffsetEntry(Base):
    __tablename__ = "offset_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), nullable=False)
    invoice_id: Mapped[int | None] = mapped_column(ForeignKey("invoices.id"), nullable=True)
    movement_date: Mapped[date] = mapped_column(Date, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    original_amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    original_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    fx_rate_to_czk: Mapped[float] = mapped_column(Numeric(12, 6), nullable=False)
    amount_czk: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    interest_bearing: Mapped[bool] = mapped_column(Boolean, default=True)

    client: Mapped[Client] = relationship(back_populates="offsets")


class Reminder(Base):
    __tablename__ = "reminders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"), nullable=False)
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    scheduled_for: Mapped[date] = mapped_column(Date, nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    invoice: Mapped[Invoice] = relationship(back_populates="reminders")


class InsuranceRecord(Base):
    __tablename__ = "insurance_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    debtor_id: Mapped[int] = mapped_column(ForeignKey("debtors.id"), nullable=False)
    insured_limit: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    insurer_name: Mapped[str | None] = mapped_column(String(160), nullable=True)

    debtor: Mapped[Debtor] = relationship(back_populates="insurance_records")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(60), nullable=False)
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)


class TaxDocument(Base):
    __tablename__ = "tax_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"), nullable=False)
    doc_type: Mapped[str] = mapped_column(String(40), default="normal")
    variable_symbol: Mapped[str] = mapped_column(String(40), nullable=False)
    issued_date: Mapped[date] = mapped_column(Date, nullable=False)
    tax_supply_date: Mapped[date] = mapped_column(Date, nullable=False)
    base_amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    total_amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)

    invoice: Mapped[Invoice] = relationship(back_populates="tax_documents")


class EmailLog(Base):
    __tablename__ = "email_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    invoice_id: Mapped[int | None] = mapped_column(ForeignKey("invoices.id"), nullable=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    recipients: Mapped[str] = mapped_column(String(512), nullable=False)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    attachments_summary: Mapped[str | None] = mapped_column(String(512), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    invoice: Mapped[Invoice | None] = relationship(back_populates="emails")


class BankStatement(Base):
    __tablename__ = "bank_statements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    imported_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    account_iban: Mapped[str] = mapped_column(String(34), nullable=False)
    period_from: Mapped[date] = mapped_column(Date, nullable=False)
    period_to: Mapped[date] = mapped_column(Date, nullable=False)
    opening_balance: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    closing_balance: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)


class AdvanceInterestLine(Base):
    __tablename__ = "advance_interest_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"), nullable=False)
    period_month: Mapped[str] = mapped_column(String(7), nullable=False)
    interest_amount_czk: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
