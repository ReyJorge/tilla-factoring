"""Minimal session login — integrate SSO/OIDC here for production."""

from __future__ import annotations

import logging
import secrets
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.services.password_hashing import verify_password
from app.template_helpers import template_ctx, templates

logger = logging.getLogger(__name__)

router = APIRouter(tags=["auth"])


def _rotate_csrf(request: Request) -> str:
    tok = secrets.token_urlsafe(32)
    request.session["csrf_token"] = tok
    return tok


@router.get("/login")
def login_get(request: Request, next: str = "/dashboard"):
    if not next.startswith("/") or next.startswith("//"):
        next = "/dashboard"
    tok = _rotate_csrf(request)
    return templates.TemplateResponse(
        "auth/login.html",
        template_ctx(request, nav_active="", csrf_token=tok, next_path=next),
    )


@router.post("/login")
def login_post(
    request: Request,
    db: Session = Depends(get_db),
    username: str = Form(...),
    password: str = Form(...),
    csrf_token: str = Form(...),
    next: str = Form("/dashboard"),
):
    if csrf_token != request.session.get("csrf_token"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid CSRF token")
    if not next.startswith("/") or next.startswith("//"):
        next = "/dashboard"

    user = db.query(User).filter(User.username == username.strip()).first()
    ok = user and verify_password(password, user.password_hash)
    if not ok:
        logger.info("login failed username=%s", username[:80])
        tok = _rotate_csrf(request)
        return templates.TemplateResponse(
            "auth/login.html",
            template_ctx(
                request,
                nav_active="",
                csrf_token=tok,
                next_path=next,
                login_error="Neplatné přihlašovací údaje.",
            ),
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    request.session.clear()
    request.session["user_id"] = user.id
    _rotate_csrf(request)
    logger.info("login ok user_id=%s username=%s", user.id, user.username)
    return RedirectResponse(url=next, status_code=status.HTTP_303_SEE_OTHER)


@router.post("/logout")
def logout_post(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/logout")
def logout_get(request: Request):
    """GET logout for convenience (demo); prefer POST in hardened deployments."""
    request.session.clear()
    return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
