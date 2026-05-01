from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import GlobalSetting
from app.services import settings_service
from app.template_helpers import add_flash, template_ctx, templates

router = APIRouter(tags=["settings"], prefix="/settings")


@router.get("/global")
def global_settings(request: Request, db: Session = Depends(get_db)):
    rows = db.query(GlobalSetting).order_by(GlobalSetting.key.asc()).all()
    return templates.TemplateResponse(
        "settings/global.html",
        template_ctx(request, nav_active="settings", rows=rows),
    )


@router.post("/global")
async def global_settings_save(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    rows = db.query(GlobalSetting).all()
    if not rows:
        raise HTTPException(status_code=400, detail="Missing seed.")
    for row in rows:
        fname = row.key.replace(".", "_")
        if fname not in form:
            continue
        row.value = str(form[fname]).strip()
    db.commit()
    add_flash(request, "Globální nastavení uloženo.")
    return RedirectResponse(url="/settings/global", status_code=303)
