from datetime import datetime

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth import admin_required_page, hash_password
from app.deps import get_db
from app.models import AppUser

router = APIRouter(prefix="/admin/users", tags=["admin-users"])
templates = Jinja2Templates(directory="app/templates")


@router.get("", response_class=HTMLResponse)
@admin_required_page
def users_list(request: Request, db: Session = Depends(get_db)):
    users = db.query(AppUser).order_by(AppUser.id.asc()).all()
    return templates.TemplateResponse(
        "users.html",
        {
            "request": request,
            "users": users,
            "current_user": request.state.current_user,
        },
    )


@router.post("/create")
@admin_required_page
def users_create(
    request: Request,
    db: Session = Depends(get_db),
    username: str = Form(...),
    password: str = Form(...),
    is_admin: str | None = Form(None),
):
    exists = db.query(AppUser).filter(AppUser.username == username).first()
    if not exists:
        user = AppUser(
            username=username,
            password_hash=hash_password(password),
            is_active=True,
            is_admin=bool(is_admin),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(user)
        db.commit()

    return RedirectResponse("/admin/users", status_code=302)


@router.post("/{user_id}/toggle")
@admin_required_page
def users_toggle(request: Request, user_id: int, db: Session = Depends(get_db)):
    user = db.get(AppUser, user_id)
    current = request.state.current_user

    if user and user.id != current.id:
        user.is_active = not user.is_active
        user.updated_at = datetime.utcnow()
        db.commit()

    return RedirectResponse("/admin/users", status_code=302)


@router.post("/{user_id}/delete")
@admin_required_page
def users_delete(request: Request, user_id: int, db: Session = Depends(get_db)):
    user = db.get(AppUser, user_id)
    current = request.state.current_user

    if user and user.id != current.id:
        db.delete(user)
        db.commit()

    return RedirectResponse("/admin/users", status_code=302)
