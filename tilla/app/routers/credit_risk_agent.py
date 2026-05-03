"""Tilla Credit Risk Officer — protected UI + POST API."""

from __future__ import annotations

import logging
import os
import secrets
import time
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session

from app.authz import redirect_login, user_can_credit_risk_agent
from app.database import get_db
from app.models import CreditRiskAgentRun, User
from app.services import credit_risk_agent_service as cra_svc
from app.template_helpers import template_ctx, templates

logger = logging.getLogger(__name__)

_RATE: dict[int, list[float]] = {}
_RL_WINDOW_SEC = 3600
_RL_MAX = 30


def _rotate_csrf(request: Request) -> str:
    tok = secrets.token_urlsafe(32)
    request.session["csrf_token"] = tok
    return tok


def _rate_ok(user_id: int) -> bool:
    now = time.time()
    bucket = _RATE.setdefault(user_id, [])
    bucket[:] = [t for t in bucket if now - t < _RL_WINDOW_SEC]
    if len(bucket) >= _RL_MAX:
        return False
    bucket.append(now)
    return True


def _session_user(request: Request) -> User | None:
    return getattr(request.state, "user", None)


def build_portfolio_snapshot(db: Session, limit_runs: int = 800) -> dict:
    runs = (
        db.query(CreditRiskAgentRun)
        .order_by(CreditRiskAgentRun.created_at.desc())
        .limit(limit_runs)
        .all()
    )
    by_anchor: dict[str, float] = defaultdict(float)
    by_supplier: dict[str, float] = defaultdict(float)
    concentrations: list[tuple[str, float]] = []
    band_counts: dict[str, int] = defaultdict(int)
    advances: list[float] = []
    manual_queue: list[CreditRiskAgentRun] = []
    rejected: list[CreditRiskAgentRun] = []

    total_notional = 0.0

    for r in runs:
        out = r.full_output_json if isinstance(r.full_output_json, dict) else {}
        inp = r.full_input_json if isinstance(r.full_input_json, dict) else {}
        mr = out.get("model_result") if isinstance(out.get("model_result"), dict) else {}
        fd = out.get("final_decision") if isinstance(out.get("final_decision"), dict) else {}

        amt = float(inp.get("invoice_amount") or r.invoice_amount or 0)
        total_notional += amt

        anc_key = str(inp.get("anchor_name") or r.anchor_name or "—")
        sup_key = str(inp.get("supplier_name") or r.supplier_name or "—")
        by_anchor[anc_key] += amt
        by_supplier[sup_key] += amt

        band = str(mr.get("risk_band") or r.risk_band or r.scoring_result or "?")[:8]
        band_counts[band] += 1

        adv = mr.get("recommended_advance_pct")
        if adv is not None:
            try:
                advances.append(float(adv))
            except (TypeError, ValueError):
                pass

        if fd.get("human_review_required") or (
            r.workflow_status and r.workflow_status == "Human review required"
        ):
            manual_queue.append(r)
        rec = str(fd.get("recommendation") or r.recommendation or "")
        if "reject" in rec.lower() or r.workflow_status == "Rejected by human":
            rejected.append(r)

    for label, mp in (("anchor", by_anchor), ("supplier", by_supplier)):
        for name, val in mp.items():
            concentrations.append((f"{label}:{name}", float(val)))

    concentrations.sort(key=lambda x: x[1], reverse=True)
    top10 = concentrations[:10]

    avg_adv = sum(advances) / len(advances) if advances else None

    latest_decisions = runs[:10]

    return {
        "run_count": len(runs),
        "total_invoice_notional": total_notional,
        "by_anchor": dict(sorted(by_anchor.items(), key=lambda kv: kv[1], reverse=True)),
        "by_supplier": dict(sorted(by_supplier.items(), key=lambda kv: kv[1], reverse=True)),
        "top_concentrations": top10,
        "risk_band_distribution": dict(band_counts),
        "average_advance_pct": avg_adv,
        "manual_review_queue": manual_queue[:50],
        "rejected_cases": rejected[:50],
        "latest_decisions": latest_decisions,
    }


pages = APIRouter(tags=["credit-risk-agent"])
api = APIRouter(prefix="/api/credit-risk-agent", tags=["credit-risk-agent-api"])


class WorkflowUpdateBody(BaseModel):
    workflow_status: str = Field(..., max_length=40)
    workflow_note: str | None = Field(None, max_length=8000)


@pages.get("/credit-risk-agent", response_class=HTMLResponse)
def credit_risk_agent_page(request: Request, db: Session = Depends(get_db)):
    user = _session_user(request)
    if not user:
        return RedirectResponse(url=redirect_login(request), status_code=303)
    if not user_can_credit_risk_agent(user):
        return templates.TemplateResponse(
            "errors/forbidden_credit.html",
            template_ctx(request, nav_active="credit-risk-agent"),
            status_code=403,
        )

    tok = request.session.get("csrf_token") or _rotate_csrf(request)
    history = (
        db.query(CreditRiskAgentRun)
        .order_by(CreditRiskAgentRun.created_at.desc())
        .limit(10)
        .all()
    )
    return templates.TemplateResponse(
        "credit_risk_agent/index.html",
        template_ctx(
            request,
            nav_active="credit-risk-agent",
            csrf_token=tok,
            history=history,
        ),
    )


@pages.get("/credit-risk-agent/portfolio", response_class=HTMLResponse)
def credit_risk_portfolio_page(request: Request, db: Session = Depends(get_db)):
    user = _session_user(request)
    if not user:
        return RedirectResponse(url=redirect_login(request), status_code=303)
    if not user_can_credit_risk_agent(user):
        return templates.TemplateResponse(
            "errors/forbidden_credit.html",
            template_ctx(request, nav_active="credit-risk-portfolio"),
            status_code=403,
        )
    snapshot = build_portfolio_snapshot(db)
    return templates.TemplateResponse(
        "credit_risk_agent/portfolio.html",
        template_ctx(request, nav_active="credit-risk-portfolio", snapshot=snapshot),
    )


@pages.get("/credit-risk-agent/run/{run_id}", response_class=HTMLResponse)
def credit_risk_run_detail(request: Request, run_id: int, db: Session = Depends(get_db)):
    user = _session_user(request)
    if not user:
        return RedirectResponse(url=redirect_login(request), status_code=303)
    if not user_can_credit_risk_agent(user):
        return templates.TemplateResponse(
            "errors/forbidden_credit.html",
            template_ctx(request, nav_active="credit-risk-agent"),
            status_code=403,
        )
    run = db.get(CreditRiskAgentRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Not found")
    tok = request.session.get("csrf_token") or _rotate_csrf(request)
    return templates.TemplateResponse(
        "credit_risk_agent/detail.html",
        template_ctx(request, nav_active="credit-risk-agent", run=run, csrf_token=tok),
    )


@api.post("/analyse")
async def credit_risk_analyse(request: Request, db: Session = Depends(get_db)):
    user = _session_user(request)
    if not user:
        return JSONResponse(status_code=401, content={"ok": False, "error": "Authentication required"})
    if not user_can_credit_risk_agent(user):
        return JSONResponse(status_code=403, content={"ok": False, "error": "Access denied"})
    if not _rate_ok(user.id):
        return JSONResponse(status_code=429, content={"ok": False, "error": "Rate limit exceeded"})

    try:
        body = await request.json()
    except Exception:
        body = {}

    try:
        payload = cra_svc.CreditRiskAnalyseIn.model_validate(body)
    except ValidationError as ve:
        return JSONResponse(status_code=422, content={"ok": False, "error": ve.errors()})

    if payload.csrf_token != request.session.get("csrf_token"):
        return JSONResponse(status_code=400, content={"ok": False, "error": "Invalid CSRF token"})

    debug_financial = os.getenv("DEBUG", "").lower() in ("1", "true", "yes")
    logger.info(
        "credit_risk_analyse user_id=%s supplier=%s anchor=%s invoice=%s anchor_rating=%s",
        user.id,
        payload.supplier_name[:120],
        payload.anchor_name[:120],
        payload.invoice_amount,
        (payload.anchor_rating or "")[:12],
    )
    if debug_financial:
        logger.debug("credit_risk_analyse full_body_keys=%s", list(body.keys()))

    inp_storage = payload.model_dump(exclude={"csrf_token"})

    try:
        out = cra_svc.analyse_credit_risk(payload)
    except Exception as exc:
        logger.warning("credit_risk analyse fatal fallback: %s", exc)
        out = cra_svc.analyse_credit_risk_fatal_fallback(payload, str(exc))

    mr = out.get("model_result") or {}
    pol = out.get("policy_check_result") or {}
    ai = out.get("agent_interpretation") or {}
    fd = out.get("final_decision") or {}

    model_score_val = None
    if mr.get("total_score") is not None:
        try:
            model_score_val = float(mr["total_score"])
        except (TypeError, ValueError):
            model_score_val = None

    rec = cra_svc.final_recommendation_display(out)[:80]
    conf = str(ai.get("confidence_level", "Low"))[:40]
    risk_band = str(mr.get("risk_band") or payload.scoring_result or "-")[:8]

    run = CreditRiskAgentRun(
        user_id=user.id,
        supplier_name=payload.supplier_name,
        supplier_ico=payload.supplier_ico,
        anchor_name=payload.anchor_name,
        anchor_ico=payload.anchor_ico,
        invoice_amount=payload.invoice_amount,
        scoring_result=risk_band,
        recommendation=rec,
        confidence_level=conf,
        full_input_json=inp_storage,
        full_output_json=out,
        workflow_status=cra_svc.workflow_status_from_final_decision(fd),
        workflow_note=None,
        model_score=model_score_val,
        risk_band=str(mr.get("risk_band"))[:8] if mr.get("risk_band") else None,
        rating_gate=str(mr.get("rating_gate"))[:16] if mr.get("rating_gate") else None,
        recommended_advance_pct=float(mr["recommended_advance_pct"])
        if mr.get("recommended_advance_pct") is not None
        else None,
        recommended_fee_pct=float(mr["recommended_fee_pct"]) if mr.get("recommended_fee_pct") is not None else None,
        policy_status=str(pol.get("final_policy_status"))[:16] if pol.get("final_policy_status") else None,
        approval_level_required=str(fd.get("approval_level_required"))[:64]
        if fd.get("approval_level_required")
        else None,
        can_fund_now=bool(fd["can_fund_now"]) if fd.get("can_fund_now") is not None else None,
        model_version=str(out.get("model_version"))[:48] if out.get("model_version") else None,
        kb_version=str(out.get("kb_version"))[:48] if out.get("kb_version") else None,
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    _rotate_csrf(request)

    return JSONResponse(
        content={
            "ok": True,
            "run_id": run.id,
            "input_summary": out.get("input_summary"),
            "model_result": out.get("model_result"),
            "policy_check_result": out.get("policy_check_result"),
            "agent_interpretation": out.get("agent_interpretation"),
            "final_decision": out.get("final_decision"),
            "kb_version": out.get("kb_version"),
            "model_version": out.get("model_version"),
        }
    )


@api.patch("/run/{run_id}/workflow")
async def credit_risk_workflow_update(
    run_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    user = _session_user(request)
    if not user:
        return JSONResponse(status_code=401, content={"ok": False, "error": "Authentication required"})
    if not user_can_credit_risk_agent(user):
        return JSONResponse(status_code=403, content={"ok": False, "error": "Access denied"})
    try:
        body = await request.json()
    except Exception:
        body = {}
    try:
        patch = WorkflowUpdateBody.model_validate(body)
    except ValidationError as ve:
        return JSONResponse(status_code=422, content={"ok": False, "error": ve.errors()})

    if patch.workflow_status not in cra_svc.WORKFLOW_STATUSES:
        return JSONResponse(
            status_code=400,
            content={"ok": False, "error": f"Invalid workflow_status; allowed={sorted(cra_svc.WORKFLOW_STATUSES)}"},
        )

    run = db.get(CreditRiskAgentRun, run_id)
    if not run:
        return JSONResponse(status_code=404, content={"ok": False, "error": "Not found"})

    mr = {}
    pol = {}
    if isinstance(run.full_output_json, dict):
        mr = run.full_output_json.get("model_result") or {}
        pol = run.full_output_json.get("policy_check_result") or {}

    hs = set(mr.get("hard_stops") or []) | set(pol.get("hard_stops") or [])
    stop_pol = str(pol.get("final_policy_status", "")).upper() == "STOP"
    stop_gate = str(mr.get("rating_gate", "")).upper() == "STOP"

    if patch.workflow_status == "Approved by human" and (stop_pol or stop_gate or hs):
        return JSONResponse(
            status_code=409,
            content={
                "ok": False,
                "error": "Cannot mark Approved when policy STOP / rating_gate STOP / hard_stops present.",
            },
        )

    run.workflow_status = patch.workflow_status
    run.workflow_note = patch.workflow_note
    db.commit()

    return JSONResponse(content={"ok": True, "run_id": run.id, "workflow_status": run.workflow_status})
