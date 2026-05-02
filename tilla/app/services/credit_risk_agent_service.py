"""Credit Risk Agent: knowledge base loading, rule pre-checks, OpenAI structured recommendation."""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.database import BASE_DIR

logger = logging.getLogger(__name__)

# TODO: Replace full-folder concatenation with embedding retrieval + vector search (pgvector / hosted search).
KB_ROOT = BASE_DIR / "knowledge_base" / "credit_risk"

SYSTEM_PROMPT = """You are Tilla Credit Risk Agent.
You support invoice financing and embedded factoring decisions.
You may only use the approved Tilla Credit Risk Knowledge Base, explicitly coded risk rules, and structured user input.
You must not invent policy, limits, pricing, thresholds, credit appetite, legal conclusions, or financial facts.
If the information is missing, say that human review is required.
Every recommendation must include reasons, risks, mitigants, and missing information.
You are not allowed to make final binding credit decisions.
Your output is only a recommendation for a human credit approver."""

OUTPUT_SCHEMA_HINT = """Respond with a single JSON object only (no markdown), keys exactly:
{
  "recommendation": "Approve | Conditional approve | Reject | Human review required",
  "suggested_risk_grade": "string",
  "suggested_supplier_limit": "string",
  "suggested_anchor_exposure_limit": "string",
  "suggested_advance_rate": "string",
  "key_risks": ["string"],
  "mitigants": ["string"],
  "missing_information": ["string"],
  "conditions_before_funding": ["string"],
  "credit_memo_summary": "string",
  "policy_references_used": ["string"],
  "confidence_level": "Low | Medium | High",
  "rationale": "string"
}
Use conservative wording; cite only KB filenames or sections implied by the injected knowledge base text, not external sources."""


class CreditRiskAnalyseIn(BaseModel):
    supplier_name: str = Field(..., max_length=255)
    supplier_ico: str = Field(..., max_length=32)
    anchor_name: str = Field(..., max_length=255)
    anchor_ico: str = Field(..., max_length=32)
    invoice_amount: float = Field(..., gt=0)
    requested_advance_pct: float = Field(..., ge=0, le=100)
    revenue_latest_year: str | None = Field(None, max_length=80)
    ebitda_latest_year: str | None = Field(None, max_length=80)
    profit_loss_latest_year: str | None = Field(None, max_length=80)
    receivables: str | None = Field(None, max_length=80)
    payables: str | None = Field(None, max_length=80)
    overdue_information: str | None = Field(None, max_length=4000)
    existing_exposure_supplier: str | None = Field(None, max_length=80)
    existing_exposure_anchor: str | None = Field(None, max_length=80)
    scoring_result: str = Field(..., pattern=r"^[ABCD]$")
    notes: str | None = Field(None, max_length=8000)
    csrf_token: str = Field(..., min_length=8, max_length=128)

    @field_validator(
        "supplier_name",
        "anchor_name",
        "supplier_ico",
        "anchor_ico",
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


OVERDUE_MATERIAL_PATTERNS = re.compile(
    r"\b(legal|litigation|insolvency|bankruptcy|konkurs|likvidace|default|90\s*\+|120\s*\+|critical|execution|exekuce)\b",
    re.I,
)


def load_knowledge_base_text() -> str:
    if not KB_ROOT.is_dir():
        logger.warning("Knowledge base folder missing: %s", KB_ROOT)
        return "(Knowledge base folder missing — human review required.)"
    chunks: list[str] = []
    for path in sorted(KB_ROOT.glob("*.md")):
        try:
            chunks.append(f"--- FILE: {path.name} ---\n{path.read_text(encoding='utf-8')}")
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


def run_rule_prechecks(payload: CreditRiskAnalyseIn) -> dict[str, Any]:
    """Deterministic flags merged into LLM context; may constrain recommendation."""
    flags: list[str] = []
    missing_financial: list[str] = []

    if not payload.revenue_latest_year:
        missing_financial.append("revenue_latest_year")
    if not payload.ebitda_latest_year:
        missing_financial.append("ebitda_latest_year")
    if not payload.receivables:
        missing_financial.append("receivables")

    override_hint: str | None = None

    if payload.scoring_result == "D":
        flags.append("scoring_D_requires_reject_or_human_review")
        override_hint = "Human review required"

    if payload.requested_advance_pct > 80:
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


def build_llm_messages(kb_text: str, payload: CreditRiskAnalyseIn, precheck: dict[str, Any]) -> list[dict[str, str]]:
    user_blob = payload.model_dump(exclude={"csrf_token"})
    user_content = json.dumps(user_blob, ensure_ascii=False)
    meta = json.dumps(precheck, ensure_ascii=False)
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"TILLA CREDIT RISK KNOWLEDGE BASE (draft):\n\n{kb_text}\n\n---\nRULE PRECHECK RESULTS:\n{meta}\n---\nSTRUCTURED CASE INPUT JSON:\n{user_content}\n---\n{OUTPUT_SCHEMA_HINT}",
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


def merge_precheck_into_output(parsed: dict[str, Any], precheck: dict[str, Any]) -> dict[str, Any]:
    """Ensure human review when rules demand it."""
    flags = precheck.get("flags") or []
    rec = parsed.get("recommendation", "")
    if "scoring_D_requires_reject_or_human_review" in flags:
        if rec not in ("Reject", "Human review required"):
            parsed["recommendation"] = "Human review required"
            parsed.setdefault("key_risks", []).append("Scoring grade D — rule-based escalation.")
    if "overdue_information_material_human_review" in flags:
        if rec == "Approve":
            parsed["recommendation"] = "Human review required"
        parsed.setdefault("missing_information", []).append("Overdue / collections detail requires officer review.")
    if "requested_advance_above_80pct_exception" in flags:
        parsed.setdefault("conditions_before_funding", []).append(
            "Requested advance above 80% — exceptional approval workflow applies."
        )
    if "invoice_exceeds_configured_supplier_cap" in flags or "invoice_exceeds_configured_anchor_cap" in flags:
        parsed.setdefault("key_risks", []).append("Invoice size vs configured programme cap — verify limits.")
    if "combined_exposure_exceeds_supplier_cap" in flags or "combined_exposure_exceeds_anchor_cap" in flags:
        parsed.setdefault("key_risks", []).append("Combined exposure exceeds configured cap — verify headroom.")
    if "key_financial_fields_missing" in flags:
        parsed.setdefault("missing_information", []).append(
            "Key financial metrics incomplete — confirm latest revenue/EBITDA/receivables."
        )
    parsed.setdefault("policy_references_used", []).append("draft_kb_bundle + coded_precheck_rules")
    return parsed


def analyse_credit_risk(payload: CreditRiskAnalyseIn) -> dict[str, Any]:
    kb_text = load_knowledge_base_text()
    precheck = run_rule_prechecks(payload)
    messages = build_llm_messages(kb_text, payload, precheck)
    parsed = call_openai_json(messages)
    out = merge_precheck_into_output(parsed, precheck)
    out["_precheck"] = precheck
    return out


def analyse_credit_risk_without_llm_placeholder(payload: CreditRiskAnalyseIn, error: str) -> dict[str, Any]:
    """Fallback JSON when OpenAI unavailable — rule pre-checks still apply."""
    precheck = run_rule_prechecks(payload)
    rec = "Human review required"
    if "scoring_D_requires_reject_or_human_review" in (precheck.get("flags") or []):
        rec = "Reject"
    base: dict[str, Any] = {
        "recommendation": rec,
        "suggested_risk_grade": "Ungraded",
        "suggested_supplier_limit": "Not assessed (LLM offline)",
        "suggested_anchor_exposure_limit": "Not assessed (LLM offline)",
        "suggested_advance_rate": "Not assessed",
        "key_risks": [error],
        "mitigants": ["Provide complete financial package for manual underwriting."],
        "missing_information": list(precheck.get("missing_financial_fields") or []),
        "conditions_before_funding": ["Manual credit committee review"],
        "credit_memo_summary": "Automated narrative unavailable — use draft KB and manual review.",
        "policy_references_used": ["draft_kb_bundle + coded_precheck_rules"],
        "confidence_level": "Low",
        "rationale": "OpenAI call failed or disabled; rule pre-check only.",
    }
    if not base["missing_information"]:
        base["missing_information"] = ["LLM analysis unavailable"]
    merged = merge_precheck_into_output(base, precheck)
    merged["_precheck"] = precheck
    merged["_error"] = error
    return merged
