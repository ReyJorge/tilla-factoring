"""Credit Risk Agent access control. Integrate with corporate IdP here if replacing session login."""

from __future__ import annotations

import os
from urllib.parse import quote

from fastapi import HTTPException, Request, status

from app.models import User


def owner_email_env() -> str | None:
    v = os.getenv("OWNER_EMAIL", "").strip()
    return v.lower() if v else None


def user_can_credit_risk_agent(user: User | None) -> bool:
    if not user or not user.is_active:
        return False
    owner_em = owner_email_env()
    if owner_em and user.email.strip().lower() == owner_em:
        return True
    role = (user.role or "").strip().lower()
    # Spec: role admin; superadmin = platform admin equivalent for MVP
    return role in ("admin", "superadmin")


def require_credit_risk_agent(user: User | None) -> User:
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    if not user_can_credit_risk_agent(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    return user


def redirect_login(request: Request) -> str:
    nxt = quote(request.url.path, safe="/")
    return f"/login?next={nxt}"
