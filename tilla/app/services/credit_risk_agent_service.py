"""Credit Risk Agent: deterministic Excel-model scoring + KB + optional LLM interpretation layer only."""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import date, timedelta
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.database import BASE_DIR
from app.services import credit_risk_excel_model as cra_xls

logger = logging.getLogger(__name__)

KB_ROOT = BASE_DIR / "knowledge_base" / "credit_risk"

SYSTEM_PROMPT_INTERPRETATION = """You are Tilla Credit Risk Agent — interpretation layer only.
You receive (1) deterministic model_result JSON from the anchored Excel scoring implementation and (2) approved markdown knowledge base excerpts.
Rules:
- Do NOT invent thresholds, gates, scores, advance %, fee %, risk bands, or rating gates.
- Copy risk_grade exactly from model_result.risk_band.
- recommendation must align with model_result.rating_gate and model_result.concentration_flag:
  - If rating_gate is STOP → recommendation MUST be \"Reject\" (or escalate rejection wording).
  - If rating_gate is MANUAL → recommendation MUST be \"Human review required\".
  - If concentration_flag is \"RED FLAG\" → recommendation MUST be \"Human review required\" unless already STOP.
  - If dispute is true or data_mismatch is true in model inputs context appears as penalties — never recommend unconditional approval.
- Explain reasoning in plain language referencing model_result fields by name, not invented numbers.
- Output a single JSON object matching the requested agent_interpretation schema only."""

OUTPUT_AGENT_HINT = """Respond with JSON only (no markdown), keys exactly:
{
  \"recommendation\": \"Approve | Conditional approve | Reject | Human review required\",
  \"risk_grade\": \"must equal model_result.risk_band verbatim\",
  \"key_risks\": [\"string\"],
  \"mitigants\": [\"string\"],
  \"missing_information\": [\"string\"],
  \"conditions_before_funding\": [\"string\"],
  \"credit_memo_summary\": \"string\",
  \"policy_references_used\": [\"string\"],
  \"confidence_level\": \"Low | Medium | High\"
}
Never contradict model_result.rating_gate or concentration RED FLAG semantics."""


class CreditRiskAnalyseIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    supplier_name: str = Field(..., max_length=255)
    supplier_ico: str = Field(..., max_length=32)
    anchor_name: str = Field(..., max_length=255)
    anchor_ico: str = Field(..., max_length=32)
    invoice_amount: float = Field(..., gt=0)
    requested_advance_pct: float | None = Field(None, ge=0, le=100)

    deal_id: str | None = Field(None, max_length=128)
    receivable_status: str | None = Field(None, max_length=255)
    due_date: str | None = Field(None, max_length=40)
    data_mismatch: bool = False
    dispute: bool = False
    anchor_rating: str | None = Field(None, max_length=16)
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
    notes: str | None = Field(None, max_length=8000)
    csrf_token: str = Field(..., min_length=8, max_length=128)

    @field_validator(
        "supplier_name",
        "anchor_name",
        "supplier_ico",
        "anchor_ico",
        "deal_id",
        "receivable_status",
        "anchor_rating",
        "due_date",
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
        if not self.due_date:
            self.due_date = (date.today() + timedelta(days=30)).isoformat()
        if self.total_portfolio_exposure is None:
            self.total_portfolio_exposure = 0.0
        return self


OVERDUE_MATERIAL_PATTERNS = re.compile(
    r"\b(legal|litigation|insolvency|bankruptcy|konkurs|likvidace|default|90\s*\+|120\s*\+|critical|execution|exekuce)\b",
    re.I,
)


def load_knowledge_base_text() -> str:
    if not KB_ROOT.is_dir():
        logger.warning("Knowledge base folder missing: %s", KB_ROOT)
        return "(Knowledge base folder missing — human review required.)"
    chunks: list[str] = []
    paths = sorted(KB_ROOT.rglob("*.md"))
    if not paths:
        paths = sorted(KB_ROOT.glob("*.md"))
    for path in paths:
        try:
            rel = path.relative_to(KB_ROOT)
            chunks.append(f"--- FILE: {rel.as_posix()} ---\n{path.read_text(encoding='utf-8')}")
        except OSError as e:
            logger.warning("KB read failed %s: %s", path, e)
    return "\n\n".join(chunks) if chunks else "(No markdown files — human review required.)"


def _parse_money(s: str | None) -> float | None:
    if not s:
        return None
    cleaned = re.sub(r"[^\d.,\-]", "", s.replace(" ", "")).replace(",", ".")
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def deal_from_payload(payload: CreditRiskAnalyseIn) -> cra_xls.DealInputs:
    due = cra_xls._parse_date(payload.due_date) or (date.today() + timedelta(days=30))
    hist = list(payload.historical_transactions or [])
    sup_exp = _parse_money(payload.existing_exposure_supplier) or 0.0
    anc_exp = _parse_money(payload.existing_exposure_anchor) or 0.0
    port = float(payload.total_portfolio_exposure or 0.0)
    rating = (payload.anchor_rating or "").strip().upper() or "NR"
    return cra_xls.DealInputs(
        anchor=payload.anchor_name.strip(),
        supplier=payload.supplier_name.strip(),
        receivable_status=(payload.receivable_status or "").strip() or "Standardní pohledávka",
        deal_id=(payload.deal_id or "").strip() or (payload.anchor_ico + "-" + payload.supplier_ico),
        invoice_amount=float(payload.invoice_amount),
        due_date=due,
        data_mismatch=bool(payload.data_mismatch),
        dispute=bool(payload.dispute),
        anchor_rating=rating,
        existing_supplier_exposure=float(sup_exp),
        existing_anchor_exposure=float(anc_exp),
        total_portfolio_exposure=float(port),
        historical_transactions=hist,
        reference_date=date.today(),
    )


def run_rule_prechecks(payload: CreditRiskAnalyseIn) -> dict[str, Any]:
    flags: list[str] = []
    missing_financial: list[str] = []
    scoring = (payload.scoring_result or "").strip().upper()

    if not payload.revenue_latest_year:
        missing_financial.append("revenue_latest_year")
    if not payload.ebitda_latest_year:
        missing_financial.append("ebitda_latest_year")
    if not payload.receivables:
        missing_financial.append("receivables")

    override_hint: str | None = None

    if scoring == "D":
        flags.append("legacy_external_scoring_D_requires_human_review")
        override_hint = "Human review required"

    req_adv = payload.requested_advance_pct
    if req_adv is not None and req_adv > 80:
        flags.append("requested_advance_above_80pct_exception")

    inv = payload.invoice_amount
    sup_cap = os.getenv("CREDIT_RISK_SUPPLIER_CAP_CZK", "").strip()
    anc_cap = os.getenv("CREDIT_RISK_ANCHOR_CAP_CZK", "").strip()
    if sup_cap:
        try:
            cap_v = float(sup_cap.replace(",", "."))
            if inv > cap_v:
                flags.append("invoice_exceeds_configured_supplier_cap")
        except ValueError:
            pass
    if anc_cap:
        try:
            cap_v = float(anc_cap.replace(",", "."))
            if inv > cap_v:
                flags.append("invoice_exceeds_configured_anchor_cap")
        except ValueError:
            pass

    ex_sup = _parse_money(payload.existing_exposure_supplier)
    if sup_cap and ex_sup is not None:
        try:
            cap_v = float(sup_cap.replace(",", "."))
            if ex_sup + inv > cap_v:
                flags.append("combined_exposure_exceeds_supplier_cap")
        except ValueError:
            pass

    ex_anc = _parse_money(payload.existing_exposure_anchor)
    if anc_cap and ex_anc is not None:
        try:
            cap_v = float(anc_cap.replace(",", "."))
            if ex_anc + inv > cap_v:
                flags.append("combined_exposure_exceeds_anchor_cap")
        except ValueError:
            pass

    overdue_txt = payload.overdue_information or ""
    if overdue_txt and OVERDUE_MATERIAL_PATTERNS.search(overdue_txt):
        flags.append("overdue_information_material_human_review")

    if missing_financial:
        flags.append("key_financial_fields_missing")

    return {
        "flags": flags,
        "missing_financial_fields": missing_financial,
        "override_hint": override_hint,
        "precheck_summary": "; ".join(flags) if flags else "no_blocking_rules_triggered",
    }


def apply_precheck_to_interpretation(precheck: dict[str, Any], interp: dict[str, Any]) -> dict[str, Any]:
    flags = precheck.get("flags") or []
    if "legacy_external_scoring_D_requires_human_review" in flags:
        interp.setdefault("key_risks", []).append("Legacy scoring grade D flagged — escalate.")
        if interp.get("recommendation") == "Approve":
            interp["recommendation"] = "Human review required"
    if "overdue_information_material_human_review" in flags:
        interp.setdefault("missing_information", []).append("Overdue / collections detail requires officer review.")
    if "requested_advance_above_80pct_exception" in flags:
        interp.setdefault("conditions_before_funding", []).append(
            "Requested advance above 80% — exceptional approval workflow applies."
        )
    if "invoice_exceeds_configured_supplier_cap" in flags or "invoice_exceeds_configured_anchor_cap" in flags:
        interp.setdefault("key_risks", []).append("Invoice size vs configured programme cap — verify limits.")
    if "combined_exposure_exceeds_supplier_cap" in flags or "combined_exposure_exceeds_anchor_cap" in flags:
        interp.setdefault("key_risks", []).append("Combined exposure exceeds configured cap — verify headroom.")
    if "key_financial_fields_missing" in flags:
        interp.setdefault("missing_information", []).append(
            "Key financial metrics incomplete — confirm latest revenue/EBITDA/receivables."
        )
    interp.setdefault("policy_references_used", []).append("draft_kb_bundle + legacy_precheck_rules")
    return interp


def enforce_llm_guardrails(model_result: dict[str, Any], interp: dict[str, Any]) -> dict[str, Any]:
    gate = str(model_result.get("rating_gate", "MANUAL")).strip().upper()
    flag = str(model_result.get("concentration_flag", "")).strip().upper()
    rec_l = str(interp.get("recommendation", "")).strip().lower()

    if gate == "STOP":
        interp["recommendation"] = "Reject"
        interp.setdefault("conditions_before_funding", []).append(
            "Model STOP gate — automated approval prohibited.",
        )
    elif gate == "MANUAL":
        interp["recommendation"] = "Human review required"

    if "RED FLAG" in flag or flag.endswith("RED FLAG"):
        interp["recommendation"] = "Human review required"
        interp.setdefault("conditions_before_funding", []).append(
            "Concentration RED FLAG — officer review required.",
        )

    if gate == "STOP" and rec_l.startswith("approve"):
        interp["recommendation"] = "Reject"

    interp["risk_grade"] = str(model_result.get("risk_band", interp.get("risk_grade", "")))
    return interp


def build_llm_messages(kb_text: str, model_result: dict[str, Any], precheck: dict[str, Any]) -> list[dict[str, str]]:
    mr = json.dumps(model_result, ensure_ascii=False)
    pc = json.dumps(precheck, ensure_ascii=False)
    return [
        {"role": "system", "content": SYSTEM_PROMPT_INTERPRETATION},
        {
            "role": "user",
            "content": (
                f"TILLA CREDIT RISK KNOWLEDGE BASE (approved excerpts):\n\n{kb_text}\n\n---\n"
                f"DETERMINISTIC MODEL RESULT (source of truth):\n{mr}\n---\n"
                f"LEGACY RULE PRECHECK (non-scoring):\n{pc}\n---\n{OUTPUT_AGENT_HINT}"
            ),
        },
    ]


def call_openai_json(messages: list[dict[str, str]]) -> dict[str, Any]:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured")

    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()
    client_cls = __import__("openai", fromlist=["OpenAI"]).OpenAI
    client = client_cls(api_key=api_key)
    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.2,
        response_format={"type": "json_object"},
    )
    raw = resp.choices[0].message.content or "{}"
    return json.loads(raw)


def default_agent_interpretation(model_result: dict[str, Any], note: str) -> dict[str, Any]:
    gate = model_result.get("rating_gate", "MANUAL")
    band = model_result.get("risk_band", "")
    rec = "Human review required"
    if gate == "STOP":
        rec = "Reject"
    elif gate == "OK" and model_result.get("concentration_flag") == "GREEN":
        rec = "Conditional approve"
    interp = {
        "recommendation": rec,
        "risk_grade": str(band),
        "key_risks": [note],
        "mitigants": ["Verify documentation vs deterministic model assumptions."],
        "missing_information": [],
        "conditions_before_funding": [
            f"Model advance {model_result.get('recommended_advance_pct')} % / fee bundle — execute only after committee alignment.",
        ],
        "credit_memo_summary": model_result.get("management_summary") or "",
        "policy_references_used": ["scoring_model_summary.md + deterministic engine"],
        "confidence_level": "Low",
    }
    return interp


def analyse_credit_risk(payload: CreditRiskAnalyseIn) -> dict[str, Any]:
    params, catalog = cra_xls.load_model_bundle()
    deal = deal_from_payload(payload)
    model_result = cra_xls.compute_deal_scoring(deal, params, catalog)
    precheck = run_rule_prechecks(payload)
    kb_text = load_knowledge_base_text()
    messages = build_llm_messages(kb_text, model_result, precheck)

    try:
        interp_raw = call_openai_json(messages)
    except Exception as exc:
        logger.warning("OpenAI interpretation fallback: %s", exc)
        interp_raw = default_agent_interpretation(model_result, str(exc))

    interp = enforce_llm_guardrails(model_result, interp_raw)
    interp = apply_precheck_to_interpretation(precheck, interp)

    return {
        "model_result": model_result,
        "agent_interpretation": interp,
        "_precheck_legacy": precheck,
    }


def analyse_credit_risk_without_llm_placeholder(payload: CreditRiskAnalyseIn, error: str) -> dict[str, Any]:
    params, catalog = cra_xls.load_model_bundle()
    deal = deal_from_payload(payload)
    model_result = cra_xls.compute_deal_scoring(deal, params, catalog)
    precheck = run_rule_prechecks(payload)
    interp = default_agent_interpretation(model_result, error)
    interp = enforce_llm_guardrails(model_result, interp)
    interp = apply_precheck_to_interpretation(precheck, interp)
    return {
        "model_result": model_result,
        "agent_interpretation": interp,
        "_precheck_legacy": precheck,
        "_error": error,
    }


def final_recommendation_display(full_out: dict[str, Any]) -> str:
    """Prefer deterministic approval headline for audit UI."""
    mr = full_out.get("model_result") or {}
    ai = full_out.get("agent_interpretation") or {}
    gate = str(mr.get("rating_gate", "")).strip().upper()
    conc = str(mr.get("concentration_flag", "")).strip().upper()
    base = str(mr.get("approval_conclusion", mr.get("recommendation", "")))[:160]
    if gate == "STOP":
        return base or "Reject"
    if gate == "MANUAL" or "RED FLAG" in conc:
        return base or str(ai.get("recommendation", "Human review required"))
    return str(ai.get("recommendation", base))[:160]
