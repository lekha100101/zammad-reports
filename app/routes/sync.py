import os

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.auth import require_user
from app.deps import get_db
from app.services.sync_service import SyncService

router = APIRouter(prefix="/sync", tags=["sync"])


def get_sync(db: Session):
    base_url = os.getenv("ZAMMAD_URL")
    token = os.getenv("ZAMMAD_TOKEN")

    if not base_url or not token:
        raise HTTPException(status_code=500, detail="ZAMMAD_URL or ZAMMAD_TOKEN not set")

    return SyncService(db, base_url, token)


def ensure_sync_access(
    request: Request,
    db: Session,
    x_sync_token: str | None = None,
):
    expected = os.getenv("SYNC_TOKEN", "").strip()

    if expected and x_sync_token == expected:
        return

    require_user(request, db)


@router.post("/all")
def sync_all(
    request: Request,
    db: Session = Depends(get_db),
    x_sync_token: str | None = Header(default=None),
):
    ensure_sync_access(request, db, x_sync_token)
    return get_sync(db).sync_all()


@router.post("/users")
def sync_users(
    request: Request,
    db: Session = Depends(get_db),
    x_sync_token: str | None = Header(default=None),
):
    ensure_sync_access(request, db, x_sync_token)
    return get_sync(db).sync_users()


@router.post("/groups")
def sync_groups(
    request: Request,
    db: Session = Depends(get_db),
    x_sync_token: str | None = Header(default=None),
):
    ensure_sync_access(request, db, x_sync_token)
    return get_sync(db).sync_groups()


@router.post("/organizations")
def sync_organizations(
    request: Request,
    db: Session = Depends(get_db),
    x_sync_token: str | None = Header(default=None),
):
    ensure_sync_access(request, db, x_sync_token)
    return get_sync(db).sync_organizations()


@router.post("/ticket-states")
def sync_states(
    request: Request,
    db: Session = Depends(get_db),
    x_sync_token: str | None = Header(default=None),
):
    ensure_sync_access(request, db, x_sync_token)
    return get_sync(db).sync_ticket_states()


@router.post("/tickets")
def sync_tickets(
    request: Request,
    db: Session = Depends(get_db),
    x_sync_token: str | None = Header(default=None),
):
    ensure_sync_access(request, db, x_sync_token)
    return get_sync(db).sync_tickets()
