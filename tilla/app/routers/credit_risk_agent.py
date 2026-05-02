"""Tilla Credit Risk Agent — protected UI + POST API."""

from __future__ import annotations

import logging
import os
import secrets
import time

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import ValidationError
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


pages = APIRouter(tags=["credit-risk-agent"])
api = APIRouter(prefix="/api/credit-risk-agent", tags=["credit-risk-agent-api"])


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
        .filter(CreditRiskAgentRun.user_id == user.id)
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
    if not run or run.user_id != user.id:
        raise HTTPException(status_code=404, detail="Not found")
    return templates.TemplateResponse(
        "credit_risk_agent/detail.html",
        template_ctx(request, nav_active="credit-risk-agent", run=run),
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
        "credit_risk_analyse user_id=%s supplier=%s anchor=%s invoice=%s scoring=%s",
        user.id,
        payload.supplier_name[:120],
        payload.anchor_name[:120],
        payload.invoice_amount,
        payload.scoring_result,
    )
    if debug_financial:
        logger.debug("credit_risk_analyse full_body_keys=%s", list(body.keys()))

    inp_storage = payload.model_dump(exclude={"csrf_token"})

    try:
        try:
            out = cra_svc.analyse_credit_risk(payload)
        except Exception as exc:
            logger.warning("OpenAI analyse fallback: %s", exc)
            out = cra_svc.analyse_credit_risk_without_llm_placeholder(payload, str(exc))
    except Exception as exc:
        logger.exception("credit_risk fatal")
        return JSONResponse(status_code=500, content={"ok": False, "error": str(exc)})

    rec = str(out.get("recommendation", "Human review required"))[:80]
    conf = str(out.get("confidence_level", "Low"))[:40]

    run = CreditRiskAgentRun(
        user_id=user.id,
        supplier_name=payload.supplier_name,
        supplier_ico=payload.supplier_ico,
        anchor_name=payload.anchor_name,
        anchor_ico=payload.anchor_ico,
        invoice_amount=payload.invoice_amount,
        scoring_result=payload.scoring_result,
        recommendation=rec,
        confidence_level=conf,
        full_input_json=inp_storage,
        full_output_json=out,
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    _rotate_csrf(request)

    return JSONResponse(content={"ok": True, "run_id": run.id, "result": out})
