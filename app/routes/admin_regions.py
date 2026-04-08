from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy.orm import Session

from app.auth import login_required_page
from app.deps import get_db
from app.models import Group, ReportRegion
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="app/templates")

router = APIRouter(prefix="/admin/regions")


@router.get("/", response_class=HTMLResponse)
@login_required_page
def regions(request: Request, db: Session = Depends(get_db)):
    groups = db.query(Group).order_by(Group.id).all()

    mapping = {
        r.group_id: r
        for r in db.query(ReportRegion).all()
    }

    return templates.TemplateResponse(
        "admin_regions.html",
        {
            "request": request,
            "groups": groups,
            "mapping": mapping,
            "current_user": request.state.current_user,
        },
    )


@router.post("/save")
@login_required_page
def save_region(
    request: Request,
    group_id: int = Form(...),
    name: str = Form(...),
    db: Session = Depends(get_db),
):
    obj = db.query(ReportRegion).filter_by(group_id=group_id).first()

    if not obj:
        obj = ReportRegion(group_id=group_id)
        db.add(obj)

    obj.name = name

    db.commit()

    return RedirectResponse("/admin/regions", status_code=302)
