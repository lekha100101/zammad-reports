import os
import requests

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.auth import require_user
from app.deps import get_db
from app.models import Ticket
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


@router.post("/time-accountings")
def sync_time_accountings(
    request: Request,
    db: Session = Depends(get_db),
    x_sync_token: str | None = Header(default=None),
):
    ensure_sync_access(request, db, x_sync_token)
    return get_sync(db).sync_time_accounting()


def _preview_payload(data, limit: int = 3):
    if isinstance(data, list):
        return {
            "payload_type": "list",
            "items_count": len(data),
            "sample": data[:limit],
        }
    if isinstance(data, dict):
        keys = list(data.keys())
        sample = {}
        for k in ["error", "message", "assets", "data", "time_accountings"]:
            if k in data:
                v = data[k]
                if isinstance(v, list):
                    sample[k] = v[:limit]
                else:
                    sample[k] = v
        return {
            "payload_type": "dict",
            "keys": keys,
            "sample": sample,
        }
    return {"payload_type": str(type(data)), "repr": str(data)[:1000]}


@router.get("/debug/time-accountings")
def debug_time_accountings(
    request: Request,
    limit: int = 3,
    scan_tickets: int = 200,
    db: Session = Depends(get_db),
    x_sync_token: str | None = Header(default=None),
):
    ensure_sync_access(request, db, x_sync_token)
    sync = get_sync(db)
    limit = max(1, min(limit, 10))
    scan_tickets = max(1, min(scan_tickets, 2000))

    result = {
        "global_endpoint": {},
        "ticket_endpoints_sample": [],
        "ticket_scan_summary": {
            "scanned": 0,
            "non_empty": 0,
            "empty": 0,
            "first_non_empty_samples": [],
        },
    }

    global_resp = requests.get(
        f"{sync.base_url}/api/v1/time_accountings?page=1&per_page={limit}",
        headers=sync.headers,
    )
    try:
        global_json = global_resp.json()
    except Exception:
        global_json = {"raw_text": global_resp.text[:2000]}

    result["global_endpoint"] = {
        "status_code": global_resp.status_code,
        "preview": _preview_payload(global_json, limit),
    }

    ticket_ids = [t[0] for t in db.query(Ticket.id).order_by(Ticket.id.desc()).limit(scan_tickets).all()]
    for ticket_id in ticket_ids:
        r = requests.get(
            f"{sync.base_url}/api/v1/tickets/{ticket_id}/time_accountings",
            headers=sync.headers,
        )
        try:
            ticket_json = r.json()
        except Exception:
            ticket_json = {"raw_text": r.text[:2000]}

        preview = _preview_payload(ticket_json, limit)
        items_count = preview.get("items_count", 0) if preview.get("payload_type") == "list" else 0

        result["ticket_scan_summary"]["scanned"] += 1
        if items_count > 0:
            result["ticket_scan_summary"]["non_empty"] += 1
            if len(result["ticket_scan_summary"]["first_non_empty_samples"]) < limit:
                result["ticket_scan_summary"]["first_non_empty_samples"].append(
                    {
                        "ticket_id": ticket_id,
                        "status_code": r.status_code,
                        "preview": preview,
                    }
                )
        else:
            result["ticket_scan_summary"]["empty"] += 1

        if len(result["ticket_endpoints_sample"]) < limit:
            result["ticket_endpoints_sample"].append(
                {
                    "ticket_id": ticket_id,
                    "status_code": r.status_code,
                    "preview": preview,
                }
            )

    return result
