from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth import admin_required_page
from app.deps import get_db
from app.models import Group
from app.services.app_settings_service import get_app_setting, update_app_settings

router = APIRouter(tags=["excluded-groups"])
templates = Jinja2Templates(directory="app/templates")


def _parse_group_ids(raw: str) -> set[int]:
    result = set()
    for value in (raw or "").split(","):
        value = value.strip()
        if value.isdigit():
            result.add(int(value))
    return result


@router.get("/admin/excluded-groups", response_class=HTMLResponse)
@admin_required_page
def excluded_groups_page(request: Request, db: Session = Depends(get_db)):
    groups = db.query(Group).order_by(Group.name.asc()).all()
    excluded_group_ids = _parse_group_ids(get_app_setting(db, "excluded_report_group_ids"))
    return templates.TemplateResponse(
        "excluded_groups_settings.html",
        {
            "request": request,
            "groups": groups,
            "excluded_group_ids": excluded_group_ids,
            "current_user": request.state.current_user,
        },
    )


@router.post("/admin/excluded-groups")
@admin_required_page
def excluded_groups_save(
    request: Request,
    excluded_group_ids: list[str] = Form(default=[]),
    db: Session = Depends(get_db),
):
    valid_group_ids = {row.id for row in db.query(Group.id).all()}
    selected = sorted(
        {
            int(value)
            for value in excluded_group_ids
            if value.isdigit() and int(value) in valid_group_ids
        }
    )
    update_app_settings(db, {"excluded_report_group_ids": ",".join(map(str, selected))})
    return RedirectResponse("/admin/excluded-groups", status_code=302)
