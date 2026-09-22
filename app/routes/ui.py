from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from app.auth import admin_required_page, login_required_page
from app.deps import get_db
from app.models import SyncLog, Ticket, TicketState
from app.services.app_settings_service import get_app_settings, get_app_setting, update_app_settings
from app.services.metric_settings_service import get_metric_int, get_metric_settings, update_metric_settings
from app.services.report_service import ReportService
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
        {
            "request": request,
            "rows": rows,
            "date_from": date_from,
            "date_to": date_to,
            "current_user": request.state.current_user,
            "sla_response_minutes": get_metric_int(db, "sla_response_minutes"),
            "sla_resolution_hours": get_metric_int(db, "sla_resolution_hours"),
        },
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
            "workload_open_warning": get_metric_int(db, "workload_open_warning"),
            "workload_open_critical": get_metric_int(db, "workload_open_critical"),
            "backlog_delta_warning": get_metric_int(db, "backlog_delta_warning"),
        },
    )


@router.get("/admin/report-metrics", response_class=HTMLResponse)
@admin_required_page
def report_metrics_settings(request: Request, db: Session = Depends(get_db)):
    metrics = get_metric_settings(db)
    return templates.TemplateResponse(
        "metrics_settings.html",
        {"request": request, "metrics": metrics, "current_user": request.state.current_user},
    )


@router.post("/admin/report-metrics")
@admin_required_page
def report_metrics_settings_save(
    request: Request,
    db: Session = Depends(get_db),
    sla_response_minutes: str = Form(""),
    sla_resolution_hours: str = Form(""),
    workload_open_warning: str = Form(""),
    workload_open_critical: str = Form(""),
    backlog_delta_warning: str = Form(""),
):
    update_metric_settings(
        db,
        {
            "sla_response_minutes": sla_response_minutes,
            "sla_resolution_hours": sla_resolution_hours,
            "workload_open_warning": workload_open_warning,
            "workload_open_critical": workload_open_critical,
            "backlog_delta_warning": backlog_delta_warning,
        },
    )
    return RedirectResponse("/admin/report-metrics", status_code=302)


@router.get("/admin/settings", response_class=HTMLResponse)
@admin_required_page
def app_settings_page(request: Request, db: Session = Depends(get_db)):
    app_settings = get_app_settings(db)
    return templates.TemplateResponse(
        "app_settings.html",
        {"request": request, "app_settings": app_settings, "current_user": request.state.current_user},
    )


@router.post("/admin/settings")
@admin_required_page
def app_settings_save(
    request: Request,
    db: Session = Depends(get_db),
    app_name: str = Form(""),
    debug: str = Form("0"),
    zammad_url: str = Form(""),
    zammad_token: str = Form(""),
    zammad_verify_ssl: str = Form("1"),
    zammad_per_page: str = Form("100"),
    tz: str = Form(""),
    sync_token: str = Form(""),
):
    update_app_settings(
        db,
        {
            "app_name": app_name,
            "debug": debug,
            "zammad_url": zammad_url,
            "zammad_token": zammad_token,
            "zammad_verify_ssl": zammad_verify_ssl,
            "zammad_per_page": zammad_per_page,
            "tz": tz,
            "sync_token": sync_token,
        },
    )
    return RedirectResponse("/admin/settings", status_code=302)


@router.post("/sync/run")
@login_required_page
def run_sync(request: Request, db: Session = Depends(get_db)):
    zammad_url = get_app_setting(db, "zammad_url")
    zammad_token = get_app_setting(db, "zammad_token")
    sync_service = SyncService(
        db,
        zammad_url,
        zammad_token,
    )
    sync_service.sync_all()
    return RedirectResponse("/", status_code=302)
