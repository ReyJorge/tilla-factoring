"""Tilla Credit Risk Officer — deterministic scoring + policy checks + optional AI credit memo."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from pydantic import Field

from app.database import BASE_DIR
from app.services.credit_risk_policy_engine import run_policy_checks
from app.services.credit_risk_scoring_engine import (
    MODEL_VERSION as SCORING_MODEL_VERSION,
    CreditRiskInput,
    calculate_credit_risk,
)

logger = logging.getLogger(__name__)

KB_ROOT = BASE_DIR / "knowledge_base" / "credit_risk"
KB_VERSION = "cro-kb-v1"

_KB_TEXT_CACHE: str | None = None

WORKFLOW_STATUSES = frozenset(
    {
        "Draft",
        "Recommended approve",
        "Conditional approve",
        "Human review required",
        "Approved by human",
        "Rejected by human",
        "Funded",
        "Settled",
    }
)


class CreditRiskAnalyseIn(CreditRiskInput):
    csrf_token: str = Field(..., min_length=8, max_length=128)


SYSTEM_PROMPT_INTERPRETATION = """You are Tilla Credit Risk Officer.
You support invoice financing and embedded factoring decisions.
You must use only:
1. deterministic model_result
2. policy_check_result
3. approved Tilla knowledge base excerpts
4. structured input_summary JSON

You must not invent thresholds, limits, pricing, ratings, score, advance %, fee %, legal conclusions or facts.

You must not override:
- hard_stops
- rating_gate STOP
- policy status STOP
- model risk_band
- deterministic recommended_advance_pct or recommended_fee_pct from model_result

If model_result.rating_gate is STOP or policy_check_result.final_policy_status is STOP, your recommendation field must be \"Reject\".

If manual review is required by policy_check_result.final_policy_status or non-empty manual_review_triggers, your output must state Human review required or Conditional approve consistent with policy_check_result.final_policy_status.

You are not a binding legal approver.
You create a structured credit memo and recommendation narrative for human approval only."""

OUTPUT_AGENT_HINT = """Respond with JSON only (no markdown). Keys exactly:
{
  \"recommendation\": \"Approve | Conditional approve | Reject | Human review required\",
  \"executive_summary\": \"string\",
  \"supplier_assessment\": \"string\",
  \"anchor_assessment\": \"string\",
  \"invoice_assessment\": \"string\",
  \"scoring_assessment\": \"string\",
  \"concentration_assessment\": \"string\",
  \"key_risks\": [],
  \"mitigants\": [],
  \"missing_information\": [],
  \"conditions_before_funding\": [],
  \"approval_level_required\": \"string\",
  \"human_review_required\": true,
  \"reason_for_human_review\": \"string\",
  \"credit_memo_summary\": \"string\",
  \"policy_references_used\": [],
  \"confidence_level\": \"Low | Medium | High\"
}

Copy risk_band wording only by quoting model_result.risk_band — never invent a letter grade different from model_result.risk_band.
Reference numeric totals using model_result.total_score, model_result.recommended_advance_pct and model_result.recommended_fee_pct verbatim when mentioning them."""


def load_knowledge_base_text() -> str:
    """Read numbered KB files once per worker — keeps analyse latency low on Render."""
    global _KB_TEXT_CACHE
    if _KB_TEXT_CACHE is not None:
        return _KB_TEXT_CACHE
    if not KB_ROOT.is_dir():
        logger.warning("Knowledge base folder missing: %s", KB_ROOT)
        _KB_TEXT_CACHE = "(Knowledge base folder missing — human review required.)"
        return _KB_TEXT_CACHE
    paths = sorted(KB_ROOT.glob("[0-9][0-9]_*.md"))
    if not paths:
        paths = sorted(KB_ROOT.glob("*.md"))
        paths = [p for p in paths if p.is_file() and "scoring_model" not in str(p.parent)]
    chunks: list[str] = []
    for path in paths:
        try:
            rel = path.relative_to(KB_ROOT)
            chunks.append(f"--- FILE: {rel.as_posix()} ---\n{path.read_text(encoding='utf-8')}")
        except OSError as e:
            logger.warning("KB read failed %s: %s", path, e)
    _KB_TEXT_CACHE = "\n\n".join(chunks) if chunks else "(No numbered KB markdown files — human review required.)"
    return _KB_TEXT_CACHE


def build_input_summary(inp: CreditRiskInput) -> dict[str, Any]:
    """Structured intake safe for memo context (mirrors CreditRiskInput)."""
    return inp.model_dump()


def build_final_decision(
    inp: CreditRiskInput,
    model_result: dict[str, Any],
    policy_result: dict[str, Any],
    _agent_interp: dict[str, Any],
) -> dict[str, Any]:
    gate = str(model_result.get("rating_gate", "")).upper()
    band = str(model_result.get("risk_band", "")).upper()
    conc = str(model_result.get("concentration_flag", ""))
    ps = str(policy_result.get("final_policy_status", "PASS"))

    mh = set(model_result.get("manual_review_triggers") or [])
    ph = set(policy_result.get("manual_review_triggers") or [])
    combined_manual = mh | ph

    hs_m = set(model_result.get("hard_stops") or [])
    hs_p = set(policy_result.get("hard_stops") or [])
    stopping = ps == "STOP" or bool(hs_p) or bool(hs_m) or gate == "STOP"

    conditions = sorted(
        set(model_result.get("conditions_before_funding") or [])
        | set(policy_result.get("conditions_before_funding") or [])
    )

    apprlvl = str(model_result.get("approval_level_required") or "Credit Manager")
    reason_human = "; ".join(sorted(combined_manual))[:4000]

    if stopping:
        return {
            "recommendation": "Reject",
            "human_review_required": False,
            "approval_level_required": "Credit Committee",
            "can_fund_now": False,
            "conditions_before_funding": conditions,
            "reason_for_human_review": "",
        }

    if band == "D":
        return {
            "recommendation": "Reject",
            "human_review_required": False,
            "approval_level_required": "Credit Committee",
            "can_fund_now": False,
            "conditions_before_funding": conditions,
            "reason_for_human_review": "",
        }

    if band == "C" or combined_manual or ps in ("MANUAL", "CONDITIONAL") or gate == "MANUAL":
        rec = "Human review required"
        if ps == "CONDITIONAL" and gate == "OK" and inp.dispute is False:
            rec = "Conditional approve"
        return {
            "recommendation": rec,
            "human_review_required": True,
            "approval_level_required": apprlvl,
            "can_fund_now": False,
            "conditions_before_funding": conditions,
            "reason_for_human_review": reason_human or ps,
        }

    if ps == "PASS" and gate == "OK" and band in ("A", "B") and conc == "GREEN" and not combined_manual:
        return {
            "recommendation": "Approve",
            "human_review_required": False,
            "approval_level_required": apprlvl,
            "can_fund_now": True,
            "conditions_before_funding": conditions,
            "reason_for_human_review": "",
        }

    return {
        "recommendation": "Human review required",
        "human_review_required": True,
        "approval_level_required": apprlvl,
        "can_fund_now": False,
        "conditions_before_funding": conditions,
        "reason_for_human_review": reason_human or "Residual eligibility gates",
    }


def enforce_llm_guardrails(
    model_result: dict[str, Any],
    policy_result: dict[str, Any],
    interp: dict[str, Any],
) -> dict[str, Any]:
    gate = str(model_result.get("rating_gate", "MANUAL")).strip().upper()
    flag = str(model_result.get("concentration_flag", "")).strip().upper()
    ps = str(policy_result.get("final_policy_status", "")).strip().upper()
    rec_l = str(interp.get("recommendation", "")).strip().lower()

    if ps == "STOP" or gate == "STOP":
        interp["recommendation"] = "Reject"
        interp.setdefault("conditions_before_funding", []).append(
            "Policy/model STOP — automated approval prohibited.",
        )
    elif gate == "MANUAL":
        interp["recommendation"] = "Human review required"

    if "RED FLAG" in flag or flag.endswith("RED FLAG"):
        interp["recommendation"] = "Human review required"

    if ps == "STOP" and rec_l.startswith("approve"):
        interp["recommendation"] = "Reject"

    interp.setdefault("key_risks", [])
    interp.setdefault("mitigants", [])
    interp.setdefault("missing_information", [])
    interp.setdefault("conditions_before_funding", [])
    interp.setdefault("policy_references_used", [])
    return interp


def default_agent_interpretation(
    model_result: dict[str, Any],
    policy_result: dict[str, Any],
    note: str,
) -> dict[str, Any]:
    gate = str(model_result.get("rating_gate", "MANUAL")).upper()
    band = str(model_result.get("risk_band", ""))
    ps = str(policy_result.get("final_policy_status", ""))
    missing_model = model_result.get("missing_information") or []
    missing_pol = []
    if policy_result.get("manual_review_triggers"):
        missing_pol.append("See policy manual_review_triggers in policy_check_result.")

    rec = "Human review required"
    if ps == "STOP" or gate == "STOP":
        rec = "Reject"
    elif ps == "CONDITIONAL":
        rec = "Conditional approve"

    return {
        "recommendation": rec,
        "executive_summary": note[:500],
        "supplier_assessment": "Deterministic memo fallback — verify supplier financials in source systems.",
        "anchor_assessment": f"Anchor gate={gate}; concentration_flag={model_result.get('concentration_flag')}.",
        "invoice_assessment": "Cross-check invoice existence, delivery / three-way match and confirmation outside this tool.",
        "scoring_assessment": (
            f"model_result.total_score={model_result.get('total_score')} "
            f"risk_band={band} rating_gate={gate}."
        ),
        "concentration_assessment": str(model_result.get("concentration_flag", "")),
        "key_risks": [note] if note else [],
        "mitigants": ["Use deterministic recommended_advance_pct and recommended_fee_pct only after human approval."],
        "missing_information": list(missing_model) + missing_pol,
        "conditions_before_funding": list(model_result.get("conditions_before_funding") or []),
        "approval_level_required": str(model_result.get("approval_level_required", "")),
        "human_review_required": ps in ("STOP", "MANUAL", "CONDITIONAL") or gate != "OK",
        "reason_for_human_review": "; ".join(policy_result.get("manual_review_triggers") or [])[:2000],
        "credit_memo_summary": str(model_result.get("management_summary") or ""),
        "policy_references_used": list(policy_result.get("policy_references") or []),
        "confidence_level": "Low",
    }


def build_llm_messages(
    kb_text: str,
    input_summary: dict[str, Any],
    model_result: dict[str, Any],
    policy_result: dict[str, Any],
) -> list[dict[str, str]]:
    payload = json.dumps(
        {
            "input_summary": input_summary,
            "model_result": model_result,
            "policy_check_result": policy_result,
        },
        ensure_ascii=False,
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT_INTERPRETATION},
        {
            "role": "user",
            "content": (
                f"TILLA CREDIT RISK KNOWLEDGE BASE (approved excerpts):\n\n{kb_text}\n\n---\n"
                f"STRUCTURED INPUT + MODEL + POLICY (authoritative JSON):\n{payload}\n---\n{OUTPUT_AGENT_HINT}"
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


def workflow_status_from_final_decision(fd: dict[str, Any]) -> str:
    rec = str(fd.get("recommendation", ""))
    if rec == "Approve":
        return "Recommended approve"
    if rec == "Conditional approve":
        return "Conditional approve"
    if rec == "Human review required":
        return "Human review required"
    if rec == "Reject":
        return "Rejected by human"
    return "Draft"


def final_recommendation_display(full_out: dict[str, Any]) -> str:
    fd = full_out.get("final_decision")
    if isinstance(fd, dict) and fd.get("recommendation"):
        return str(fd["recommendation"])[:160]
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


def _sync_interp_with_final(interp: dict[str, Any], final_decision: dict[str, Any]) -> dict[str, Any]:
    interp["recommendation"] = final_decision["recommendation"]
    interp["human_review_required"] = bool(final_decision["human_review_required"])
    interp["approval_level_required"] = final_decision["approval_level_required"]
    interp["reason_for_human_review"] = final_decision.get("reason_for_human_review") or ""
    merged_cond = sorted(
        set(interp.get("conditions_before_funding") or []) | set(final_decision.get("conditions_before_funding") or [])
    )
    interp["conditions_before_funding"] = merged_cond
    return interp


def analyse_credit_risk(payload: CreditRiskAnalyseIn) -> dict[str, Any]:
    inp = CreditRiskInput.model_validate(payload.model_dump(exclude={"csrf_token"}))
    model_result = calculate_credit_risk(inp)
    policy_result = run_policy_checks(inp, model_result)

    input_summary = build_input_summary(inp)
    kb_text = load_knowledge_base_text()
    messages = build_llm_messages(kb_text, input_summary, model_result, policy_result)

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        interp_raw = default_agent_interpretation(
            model_result,
            policy_result,
            "OPENAI_API_KEY is not configured — deterministic memo fallback.",
        )
    else:
        try:
            interp_raw = call_openai_json(messages)
        except Exception as exc:
            logger.warning("OpenAI interpretation fallback: %s", exc)
            interp_raw = default_agent_interpretation(model_result, policy_result, str(exc))

    interp = enforce_llm_guardrails(model_result, policy_result, interp_raw)
    final_decision = build_final_decision(inp, model_result, policy_result, interp)
    interp = _sync_interp_with_final(interp, final_decision)

    out = {
        "input_summary": input_summary,
        "model_result": model_result,
        "policy_check_result": policy_result,
        "agent_interpretation": interp,
        "final_decision": final_decision,
        "kb_version": KB_VERSION,
        "model_version": SCORING_MODEL_VERSION,
    }
    return out


def analyse_credit_risk_fatal_fallback(payload: CreditRiskAnalyseIn, error: str) -> dict[str, Any]:
    """Used when scoring bundle fails — still returns structured shells for audit."""
    inp = CreditRiskInput.model_validate(payload.model_dump(exclude={"csrf_token"}))
    model_result = {
        "model_version": SCORING_MODEL_VERSION,
        "total_score": 0,
        "risk_band": "D",
        "rating_gate": "STOP",
        "recommendation": "Reject",
        "recommended_advance_pct": 0.0,
        "recommended_fee_pct": 0.0,
        "hard_stops": ["SCORING_ENGINE_FAILURE"],
        "manual_review_triggers": [],
        "missing_information": [],
        "conditions_before_funding": [],
        "pricing_reason": "",
        "approval_level_required": "Credit Committee",
        "concentration_flag": "RED FLAG",
        "model_params_source": "scoring_engine_error",
        "error": error[:2000],
    }
    policy_result = run_policy_checks(inp, model_result)
    interp = default_agent_interpretation(model_result, policy_result, error)
    interp = enforce_llm_guardrails(model_result, policy_result, interp)
    final_decision = build_final_decision(inp, model_result, policy_result, interp)
    interp = _sync_interp_with_final(interp, final_decision)
    return {
        "input_summary": build_input_summary(inp),
        "model_result": model_result,
        "policy_check_result": policy_result,
        "agent_interpretation": interp,
        "final_decision": final_decision,
        "kb_version": KB_VERSION,
        "model_version": SCORING_MODEL_VERSION,
        "_fatal_error": error[:4000],
    }
