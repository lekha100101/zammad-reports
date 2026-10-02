from datetime import datetime

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.auth import admin_required_page
from app.deps import get_db
from app.models import CategoryLabel, Ticket
from app.routes.ui import templates

router = APIRouter(tags=["category-settings"])


def _discover(db: Session):
    for field_name, column in (("category", Ticket.category), ("sub_accesses", Ticket.sub_accesses)):
        values = db.query(column).filter(column.isnot(None), column != "").distinct().all()
        existing = {x.technical_value for x in db.query(CategoryLabel).filter(CategoryLabel.field_name == field_name).all()}
        for (value,) in values:
            value = (value or "").strip()
            if value and value not in existing:
                db.add(CategoryLabel(field_name=field_name, technical_value=value, display_name=value, updated_at=datetime.utcnow()))
    db.commit()


@router.get("/admin/categories", response_class=HTMLResponse)
@admin_required_page
def categories_page(request: Request, db: Session = Depends(get_db)):
    _discover(db)
    rows = db.query(CategoryLabel).order_by(CategoryLabel.field_name, CategoryLabel.technical_value).all()
    return templates.TemplateResponse("category_settings.html", {"request": request, "rows": rows, "current_user": request.state.current_user})


@router.post("/admin/categories")
@admin_required_page
def categories_save(request: Request, label_id: list[str] = Form(default=[]), display_name: list[str] = Form(default=[]), db: Session = Depends(get_db)):
    for raw_id, name in zip(label_id, display_name):
        if not raw_id.isdigit():
            continue
        row = db.get(CategoryLabel, int(raw_id))
        if row:
            row.display_name = name.strip() or row.technical_value
            row.updated_at = datetime.utcnow()
    db.commit()
    return RedirectResponse("/admin/categories?saved=1", status_code=302)
