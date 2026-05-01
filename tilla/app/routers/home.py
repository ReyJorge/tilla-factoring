from fastapi import APIRouter, Request

from app.template_helpers import template_ctx, templates

router = APIRouter(tags=["home"])


@router.get("/home")
def landing(request: Request):
    return templates.TemplateResponse(
        "home.html",
        template_ctx(request, nav_active="home"),
    )
