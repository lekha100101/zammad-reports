import os
from datetime import datetime
from functools import wraps

from fastapi import HTTPException, Request
from fastapi.responses import RedirectResponse
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.models import AppUser

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def get_session_user(request: Request, db: Session) -> AppUser | None:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    user = db.get(AppUser, user_id)
    if not user or not user.is_active:
        request.session.clear()
        return None
    return user


def require_user(request: Request, db: Session) -> AppUser:
    user = get_session_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return user


def require_admin(request: Request, db: Session) -> AppUser:
    user = require_user(request, db)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Forbidden")
    return user


def login_required_page(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        request: Request = kwargs.get("request")
        db = kwargs.get("db")
        if request is None or db is None:
            raise RuntimeError("request/db not passed")
        user = get_session_user(request, db)
        if not user:
            return RedirectResponse("/login", status_code=302)
        request.state.current_user = user
        return func(*args, **kwargs)
    return wrapper


def admin_required_page(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        request: Request = kwargs.get("request")
        db = kwargs.get("db")
        if request is None or db is None:
            raise RuntimeError("request/db not passed")
        user = get_session_user(request, db)
        if not user:
            return RedirectResponse("/login", status_code=302)
        if not user.is_admin:
            return RedirectResponse("/", status_code=302)
        request.state.current_user = user
        return func(*args, **kwargs)
    return wrapper


def bootstrap_admin(db: Session):
    username = os.getenv("ADMIN_USERNAME", "admin")
    password = os.getenv("ADMIN_PASSWORD", "ChangeMe123!")

    exists = db.query(AppUser).first()
    if exists:
        return

    admin = AppUser(
        username=username,
        password_hash=hash_password(password),
        is_active=True,
        is_admin=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(admin)
    db.commit()
