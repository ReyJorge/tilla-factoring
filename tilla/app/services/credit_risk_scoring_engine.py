"""Deterministic credit risk scoring — Excel-backed params; Python-only runtime."""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.services import credit_risk_excel_model as cra_xls

MODEL_VERSION = "cro-scoring-v1.0"


class CreditRiskInput(BaseModel):
    """Deal intake for scoring & policy (API payload excluding CSRF)."""

    model_config = ConfigDict(extra="ignore")

    supplier_name: str = Field(..., max_length=255)
    supplier_ico: str = Field(..., max_length=32)
    anchor_name: str = Field(..., max_length=255)
    anchor_ico: str = Field(..., max_length=32)
    invoice_amount: float = Field(..., gt=0)
    requested_advance_pct: float | None = Field(None, ge=0, le=100)

    deal_id: str | None = Field(None, max_length=128)
    invoice_number: str | None = Field(None, max_length=64)
    invoice_issue_date: str | None = Field(None, max_length=40)
    due_date: str | None = Field(None, max_length=40)
    receivable_status: str | None = Field(None, max_length=255)

    data_mismatch: bool = False
    dispute: bool = False
    anchor_rating: str | None = Field(None, max_length=16)

    confirmation_status: str = Field(default="confirmed", max_length=32)
    legal_status: str = Field(default="ok", max_length=32)
    bank_account_verified: bool = Field(default=True)

    fraud_suspicion: bool = False
    duplicate_invoice: bool = False
    invoice_financed_elsewhere: bool = False
    supplier_terms_accepted: bool = Field(default=True)

    total_portfolio_exposure: float | None = Field(None, ge=0)
    historical_transactions: list[dict[str, Any]] | None = None

    revenue_latest_year: str | None = Field(None, max_length=80)
    ebitda_latest_year: str | None = Field(None, max_length=80)
    profit_loss_latest_year: str | None = Field(None, max_length=80)
    receivables: str | None = Field(None, max_length=80)
    payables: str | None = Field(None, max_length=80)
    overdue_information: str | None = Field(None, max_length=4000)
    existing_exposure_supplier: str | None = Field(None, max_length=80)
    existing_exposure_anchor: str | None = Field(None, max_length=80)
    scoring_result: str | None = Field(None, max_length=8)
    supplier_financials: str | None = Field(None, max_length=16000)
    notes: str | None = Field(None, max_length=8000)

    @field_validator(
        "supplier_name",
        "anchor_name",
        "supplier_ico",
        "anchor_ico",
        "deal_id",
        "receivable_status",
        "anchor_rating",
        "due_date",
        "invoice_number",
        "invoice_issue_date",
        "confirmation_status",
        "legal_status",
        "revenue_latest_year",
        "ebitda_latest_year",
        "profit_loss_latest_year",
        "receivables",
        "payables",
        "existing_exposure_supplier",
        "existing_exposure_anchor",
        "notes",
        mode="before",
    )
    @classmethod
    def strip_ws(cls, v):
        if v is None:
            return None
        return str(v).strip()

    @field_validator("historical_transactions", mode="before")
    @classmethod
    def parse_hist(cls, v):
        if v is None or v == "":
            return None
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError as e:
                raise ValueError("historical_transactions must be a valid JSON array") from e
        return v

    @model_validator(mode="after")
    def defaults_after(self):
        if self.total_portfolio_exposure is None:
            self.total_portfolio_exposure = 0.0
        if not self.due_date:
            self.due_date = (date.today() + timedelta(days=30)).isoformat()
        return self


def _money_str(s: str | None) -> float:
    return float(cra_xls._to_float(s, 0.0) or 0.0)


def _approval_level_required(
    risk_band: str,
    rating_gate: str,
    concentration_flag: str,
    advance_pct: float | None,
) -> str:
    gate = rating_gate.upper()
    band = risk_band.upper()
    conc = concentration_flag.upper()
    adv_exc = advance_pct is not None and advance_pct > 80
    if gate == "STOP" or band == "D":
        return "Credit Committee"
    if gate == "MANUAL" or "RED" in conc or adv_exc:
        return "CRO"
    if band == "C":
        return "CRO"
    if band == "B":
        return "Credit Manager"
    return "Credit Manager"


def _pricing_reason(adv: float, fee: float) -> str:
    return (
        f"Advance driven by anchor rating ceiling and behaviour score path ({adv} %). "
        f"Total fee bundle {fee} % (base + rating premium per model)."
    )


def calculate_credit_risk(inp: CreditRiskInput) -> dict[str, Any]:
    due = cra_xls._parse_date(inp.due_date) or (date.today() + timedelta(days=30))
    sup_exp = _money_str(inp.existing_exposure_supplier)
    anc_exp = _money_str(inp.existing_exposure_anchor)
    port = float(inp.total_portfolio_exposure or 0)
    rating = (inp.anchor_rating or "").strip().upper() or "NR"

    deal = cra_xls.DealInputs(
        anchor=inp.anchor_name.strip(),
        supplier=inp.supplier_name.strip(),
        receivable_status=(inp.receivable_status or "").strip() or "Neznámý",
        deal_id=(inp.deal_id or "").strip() or f"{inp.anchor_ico}-{inp.supplier_ico}",
        invoice_amount=float(inp.invoice_amount),
        due_date=due,
        data_mismatch=bool(inp.data_mismatch),
        dispute=bool(inp.dispute),
        anchor_rating=rating,
        existing_supplier_exposure=sup_exp,
        existing_anchor_exposure=anc_exp,
        total_portfolio_exposure=port,
        historical_transactions=list(inp.historical_transactions or []),
        reference_date=date.today(),
    )

    params, catalog = cra_xls.load_model_bundle()
    base = cra_xls.compute_deal_scoring(deal, params, catalog)

    hard_stops: list[str] = []
    manual_review_triggers: list[str] = []
    missing_information: list[str] = []
    conditions_before_funding: list[str] = []

    gate = str(base.get("rating_gate", "")).upper()
    band = str(base.get("risk_band", "")).upper()
    conc = str(base.get("concentration_flag", ""))

    if gate == "STOP":
        hard_stops.append("MODEL_RATING_GATE_STOP")
    elif gate == "MANUAL":
        manual_review_triggers.append("MODEL_RATING_GATE_MANUAL")

    if inp.dispute:
        hard_stops.append("MODEL_INPUT_DISPUTE_YES")

    if inp.data_mismatch:
        manual_review_triggers.append("MODEL_INPUT_DATA_MISMATCH")

    if "RED FLAG" in conc:
        manual_review_triggers.append("CONCENTRATION_RED_FLAG")

    if band == "D":
        hard_stops.append("RISK_BAND_D")

    paid_ct = int(base.get("paid_invoice_count") or 0)
    if paid_ct < int(params.min_paid_invoices):
        manual_review_triggers.append("NEW_OR_THIN_PAYMENT_HISTORY")

    if not inp.revenue_latest_year or not inp.ebitda_latest_year:
        missing_information.append("supplier_financial_summary_incomplete")

    approval_level = _approval_level_required(band, gate, conc, inp.requested_advance_pct)

    recommended_adv = float(base.get("recommended_advance_pct") or 0)
    recommended_fee = float(base.get("recommended_fee_pct") or 0)
    if band == "C":
        recommended_adv = min(recommended_adv, 60.0)
        conditions_before_funding.append("Risk band C — advance capped at 60 % unless CRO documents override.")
    if band == "D":
        recommended_adv = 0.0

    out = dict(base)
    out.update(
        {
            "model_version": MODEL_VERSION,
            "supplier_exposure_after_deal": base.get("supplier_exposure"),
            "anchor_exposure_after_deal": base.get("anchor_exposure"),
            "recommended_advance_pct": round(recommended_adv, 2),
            "recommended_fee_pct": round(recommended_fee, 3),
            "hard_stops": sorted(set(hard_stops)),
            "manual_review_triggers": sorted(set(manual_review_triggers)),
            "missing_information": sorted(set(missing_information)),
            "conditions_before_funding": sorted(set(conditions_before_funding)),
            "pricing_reason": _pricing_reason(round(recommended_adv, 2), round(recommended_fee, 3)),
            "approval_level_required": approval_level,
        }
    )
    return out
