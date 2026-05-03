"""Policy checks layered on deterministic scoring — PASS | CONDITIONAL | MANUAL | STOP."""

from __future__ import annotations

import os
import re
from datetime import date
from typing import Any

from app.services import credit_risk_excel_model as cra_xls
from app.services.credit_risk_scoring_engine import CreditRiskInput

OVERDUE_PATTERN = re.compile(r"\b(po\s+splatnosti|overdue|after\s+due)\b", re.I)
OVERDUE_MATERIAL_PATTERNS = re.compile(
    r"\b(legal|litigation|insolvency|bankruptcy|konkurs|likvidace|default|90\s*\+|120\s*\+|critical|execution|exekuce)\b",
    re.I,
)


def run_policy_checks(inp: CreditRiskInput, model_result: dict[str, Any]) -> dict[str, Any]:
    hard_stops: list[str] = []
    manual_review_triggers: list[str] = []
    conditions_before_funding: list[str] = []
    policy_refs: list[str] = []

    gate = str(model_result.get("rating_gate", "")).upper()
    band = str(model_result.get("risk_band", "")).upper()
    conc = str(model_result.get("concentration_flag", ""))

    if band == "C":
        manual_review_triggers.append("POLICY_RISK_BAND_C_REQUIRES_OFFICER")

    policy_refs.extend(
        [
            "07_invoice_eligibility_rules.md",
            "08_fraud_operational_checklist.md",
            "10_concentration_limits.md",
            "11_pricing_advance_rules.md",
        ]
    )

    if inp.dispute:
        hard_stops.append("POLICY_DISPUTE_YES_NO_AUTOFUND")

    if inp.fraud_suspicion:
        hard_stops.append("POLICY_FRAUD_SUSPICION_STOP")

    if inp.duplicate_invoice:
        hard_stops.append("POLICY_DUPLICATE_INVOICE_STOP")

    if inp.invoice_financed_elsewhere:
        hard_stops.append("POLICY_INVOICE_ALREADY_FINANCED_ELSEWHERE_STOP")

    if not inp.supplier_terms_accepted:
        hard_stops.append("POLICY_SUPPLIER_TERMS_NOT_ACCEPTED")

    cs = inp.confirmation_status.strip().lower()
    if cs in ("refused", "anchor_refused", "no"):
        hard_stops.append("POLICY_ANCHOR_CONFIRMATION_REFUSED")
    elif cs not in ("confirmed", "yes", "verified"):
        manual_review_triggers.append("POLICY_ANCHOR_CONFIRMATION_PENDING")

    ls = inp.legal_status.strip().lower()
    if ls in ("blocked", "impossible", "fail"):
        hard_stops.append("POLICY_LEGAL_ASSIGNMENT_BLOCKED")
    elif ls not in ("ok", "satisfied", "cleared"):
        manual_review_triggers.append("POLICY_LEGAL_PRECONDITION_PENDING")

    if not inp.bank_account_verified:
        manual_review_triggers.append("POLICY_BANK_ACCOUNT_NOT_VERIFIED")

    if not (inp.invoice_number or "").strip():
        manual_review_triggers.append("POLICY_INVOICE_NUMBER_MISSING")

    due_d = cra_xls._parse_date(inp.due_date)
    if due_d and due_d < date.today():
        manual_review_triggers.append("POLICY_INVOICE_OVERDUE_REQUIRES_EXCEPTION")

    rs = (inp.receivable_status or "").strip().lower()
    if OVERDUE_PATTERN.search(inp.receivable_status or "") or "po splatnosti" in rs:
        manual_review_triggers.append("POLICY_RECEIVABLE_STATUS_OVERDUE_TEXT")

    if inp.data_mismatch:
        manual_review_triggers.append("POLICY_DATA_MISMATCH_HUMAN_REVIEW")

    overdue_txt = inp.overdue_information or ""
    if OVERDUE_MATERIAL_PATTERNS.search(overdue_txt):
        manual_review_triggers.append("POLICY_OVERDUE_INFORMATION_MATERIAL")

    inv = float(inp.invoice_amount)
    sup_exp = cra_xls._to_float(inp.existing_exposure_supplier, None)
    anc_exp = cra_xls._to_float(inp.existing_exposure_anchor, None)

    sup_cap = os.getenv("CREDIT_RISK_SUPPLIER_CAP_CZK", "").strip()
    if sup_cap:
        try:
            cap_v = float(sup_cap.replace(",", "."))
            if inv > cap_v:
                manual_review_triggers.append("POLICY_INVOICE_EXCEEDS_CONFIGURED_SUPPLIER_CAP")
        except ValueError:
            pass

    anc_cap = os.getenv("CREDIT_RISK_ANCHOR_CAP_CZK", "").strip()
    if anc_cap:
        try:
            cap_v = float(anc_cap.replace(",", "."))
            if inv > cap_v:
                manual_review_triggers.append("POLICY_INVOICE_EXCEEDS_CONFIGURED_ANCHOR_CAP")
        except ValueError:
            pass

    if sup_cap and sup_exp is not None:
        try:
            cap_v = float(sup_cap.replace(",", "."))
            if sup_exp + inv > cap_v:
                manual_review_triggers.append("POLICY_COMBINED_EXPOSURE_EXCEEDS_SUPPLIER_CAP")
        except ValueError:
            pass

    if anc_cap and anc_exp is not None:
        try:
            cap_v = float(anc_cap.replace(",", "."))
            if anc_exp + inv > cap_v:
                manual_review_triggers.append("POLICY_COMBINED_EXPOSURE_EXCEEDS_ANCHOR_CAP")
        except ValueError:
            pass

    if gate == "STOP":
        hard_stops.append("POLICY_MODEL_RATING_GATE_STOP")

    if gate == "MANUAL":
        manual_review_triggers.append("POLICY_MODEL_RATING_GATE_MANUAL")

    if "RED FLAG" in conc:
        manual_review_triggers.append("POLICY_CONCENTRATION_RED_FLAG")

    req_adv = inp.requested_advance_pct
    if req_adv is not None and req_adv > 80:
        manual_review_triggers.append("POLICY_ADVANCE_ABOVE_80_PCT_REQUIRES_CRO")
        conditions_before_funding.append(f"CRO sign-off required for requested advance {req_adv} % (>80 %).")

    paid_ct = int(model_result.get("paid_invoice_count") or 0)
    if paid_ct < 5:
        manual_review_triggers.append("POLICY_NEW_SUPPLIER_OR_THIN_PAYMENT_HISTORY")

    if not inp.revenue_latest_year or not inp.ebitda_latest_year:
        manual_review_triggers.append("POLICY_MISSING_SUPPLIER_FINANCIAL_FIELDS")

    legacy = (inp.scoring_result or "").strip().upper()
    if legacy == "D":
        hard_stops.append("POLICY_LEGACY_EXTERNAL_SCORE_D")

    for hs in model_result.get("hard_stops") or []:
        hard_stops.append(f"SYNC_MODEL::{hs}")

    for mt in model_result.get("manual_review_triggers") or []:
        manual_review_triggers.append(f"SYNC_MODEL::{mt}")

    hard_stops = sorted(set(hard_stops))
    manual_review_triggers = sorted(set(manual_review_triggers))

    final_status = "PASS"
    if hard_stops:
        final_status = "STOP"
    elif manual_review_triggers:
        if band in ("A", "B") and gate == "OK" and conc == "GREEN":
            final_status = "CONDITIONAL"
        else:
            final_status = "MANUAL"
    elif conc == "AMBER":
        final_status = "CONDITIONAL"

    return {
        "hard_stops": hard_stops,
        "manual_review_triggers": manual_review_triggers,
        "conditions_before_funding": sorted(set(conditions_before_funding)),
        "policy_references": sorted(set(policy_refs)),
        "final_policy_status": final_status,
    }
