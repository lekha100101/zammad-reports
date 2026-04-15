import os

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from app.auth import login_required_page
from app.deps import get_db
from app.models import SyncLog, Ticket, TicketState
from app.services.report_service import ReportService
from fastapi.responses import HTMLResponse, RedirectResponse
from app.services.sync_service import SyncService
from zoneinfo import ZoneInfo

router = APIRouter(tags=["ui"])
templates = Jinja2Templates(directory="app/templates")

def local_time(dt):
    if not dt:
        return None

    return (
        dt.replace(tzinfo=ZoneInfo("UTC"))
        .astimezone(ZoneInfo("Asia/Almaty"))
        .strftime("%Y-%m-%d %H:%M:%S")
    )

@router.get("/", response_class=HTMLResponse)
@login_required_page
def index(request: Request, db: Session = Depends(get_db)):
    open_names = ["open", "new"]
    closed_names = ["closed"]
    suspended_names = ["suspended"]

    open_count = (
        db.query(func.count(Ticket.id))
        .outerjoin(TicketState, Ticket.state_id == TicketState.id)
        .filter(func.lower(TicketState.name).in_(open_names))
        .scalar()
        or 0
    )

    closed_count = (
        db.query(func.count(Ticket.id))
        .outerjoin(TicketState, Ticket.state_id == TicketState.id)
        .filter(func.lower(TicketState.name).in_(closed_names))
        .scalar()
        or 0
    )

    suspended_count = (
        db.query(func.count(Ticket.id))
        .outerjoin(TicketState, Ticket.state_id == TicketState.id)
        .filter(func.lower(TicketState.name).in_(suspended_names))
        .scalar()
        or 0
    )

    last_sync = (
        db.query(SyncLog)
        .filter(SyncLog.sync_type == "tickets")
        .order_by(desc(SyncLog.started_at))
        .first()
    )

    summary = {
        "open_count": open_count,
        "closed_count": closed_count,
        "suspended_count": suspended_count,
        "last_sync": local_time(last_sync.started_at) if last_sync else None,
        "last_sync_count": last_sync.items_count if last_sync else 0,
    }

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "summary": summary,
            "current_user": request.state.current_user,
        },
    )


@router.get("/reports/statuses", response_class=HTMLResponse)
@login_required_page
def statuses(
    request: Request,
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    db: Session = Depends(get_db),
):
    rows = ReportService(db).tickets_by_status(date_from, date_to)
    return templates.TemplateResponse(
        "statuses.html",
        {"request": request, "rows": rows, "date_from": date_from, "date_to": date_to, "current_user": request.state.current_user},
    )


@router.get("/reports/agents", response_class=HTMLResponse)
@login_required_page
def agents(
    request: Request,
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    db: Session = Depends(get_db),
):
    rows = ReportService(db).tickets_by_agent(date_from, date_to)
    return templates.TemplateResponse(
        "agents.html",
        {"request": request, "rows": rows, "date_from": date_from, "date_to": date_to, "current_user": request.state.current_user},
    )


@router.get("/reports/groups", response_class=HTMLResponse)
@login_required_page
def groups(
    request: Request,
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    db: Session = Depends(get_db),
):
    rows = ReportService(db).tickets_by_group(date_from, date_to)
    return templates.TemplateResponse(
        "groups.html",
        {"request": request, "rows": rows, "date_from": date_from, "date_to": date_to, "current_user": request.state.current_user},
    )


@router.get("/reports/organizations", response_class=HTMLResponse)
@login_required_page
def organizations(
    request: Request,
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    db: Session = Depends(get_db),
):
    rows = ReportService(db).tickets_by_organization(date_from, date_to)
    return templates.TemplateResponse(
        "organizations.html",
        {"request": request, "rows": rows, "date_from": date_from, "date_to": date_to, "current_user": request.state.current_user},
    )


@router.get("/reports/regional-summary", response_class=HTMLResponse)
@login_required_page
def regional_summary(
    request: Request,
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    db: Session = Depends(get_db),
):
    rows = []
    if date_from and date_to:
        rows = ReportService(db).regional_period_report(date_from, date_to)

    return templates.TemplateResponse(
        "regional_summary.html",
        {
            "request": request,
            "rows": rows,
            "date_from": date_from,
            "date_to": date_to,
            "current_user": request.state.current_user,
        },
    )


@router.get("/reports/sla", response_class=HTMLResponse)
@login_required_page
def sla_report(
    request: Request,
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    db: Session = Depends(get_db),
):
    rows = ReportService(db).sla_report(date_from, date_to)
    return templates.TemplateResponse(
        "sla_report.html",
        {"request": request, "rows": rows, "date_from": date_from, "date_to": date_to, "current_user": request.state.current_user},
    )


@router.get("/reports/workload", response_class=HTMLResponse)
@login_required_page
def workload_report(
    request: Request,
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    db: Session = Depends(get_db),
):
    data = ReportService(db).workload_report(date_from, date_to)
    return templates.TemplateResponse(
        "workload_report.html",
        {
            "request": request,
            "agent_rows": data["agents"],
            "trend_rows": data["trend"],
            "date_from": date_from,
            "date_to": date_to,
            "current_user": request.state.current_user,
        },
    )


@router.post("/sync/run")
@login_required_page
def run_sync(request: Request, db: Session = Depends(get_db)):
    sync_service = SyncService(
        db,
        os.getenv("ZAMMAD_URL"),
        os.getenv("ZAMMAD_TOKEN"),
    )
    sync_service.sync_all()
    return RedirectResponse("/", status_code=302)
