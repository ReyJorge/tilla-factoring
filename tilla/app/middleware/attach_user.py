"""Attach authenticated User to request.state for templates and guards (inside SessionMiddleware)."""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.database import SessionLocal
from app.models import User


class AttachUserMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request.state.user = None
        try:
            uid = request.session.get("user_id")
        except Exception:
            uid = None
        if uid:
            db = SessionLocal()
            try:
                u = db.get(User, int(uid))
                if u and u.is_active:
                    request.state.user = u
            finally:
                db.close()
        return await call_next(request)
