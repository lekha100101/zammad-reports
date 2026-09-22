import threading
import json

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from app.auth import admin_required_page, login_required_page
from app.deps import get_db
from app.db import SessionLocal
from app.models import SyncLog, Ticket, TicketState, TicketHistory
from app.services.app_settings_service import get_app_settings, get_app_setting, update_app_settings
from app.services.metric_settings_service import get_metric_int, get_metric_settings, update_metric_settings
from app.services.report_service import ReportService
from app.services.sync_service import SyncService
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

router = APIRouter(tags=["ui"])
templates = Jinja2Templates(directory="app/templates")
SYNC_LOCK = threading.Lock()

def report_enabled(request: Request, key: str) -> bool:
    db = SessionLocal()
    try:
        raw = get_app_setting(db, "report_visibility")
        if not raw:
            return True
        return key in {item for item in raw.split(",") if item}
    finally:
        db.close()

templates.env.globals["report_enabled"] = report_enabled

def report_order() -> list[str]:
    db = SessionLocal()
    try:
        raw = get_app_setting(db, "report_order")
        saved = [item for item in raw.split(",") if item] if raw else []
        defaults = [key for key, _ in REPORT_VISIBILITY_OPTIONS]
        return saved + [key for key in defaults if key not in saved]
    finally:
        db.close()

templates.env.globals["report_order"] = report_order

def local_time(dt, tz_name: str = "UTC"):
    if not dt:
        return None

    try:
        target_tz = ZoneInfo(tz_name or "UTC")
    except ZoneInfoNotFoundError:
        target_tz = ZoneInfo("UTC")

    return (
        dt.replace(tzinfo=ZoneInfo("UTC"))
        .astimezone(target_tz)
        .strftime("%Y-%m-%d %H:%M:%S")
    )

@router.get("/", response_class=HTMLResponse)
@login_required_page
def index(request: Request, db: Session = Depends(get_db)):
    open_names = ["open", "new"]
    closed_names = ["closed"]
    suspended_names = ["suspended"]
    tz_name = get_app_setting(db, "tz")

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
        "last_sync": local_time(last_sync.started_at, tz_name) if last_sync else None,
        "last_sync_count": last_sync.items_count if last_sync else 0,
    }
    workload = ReportService(db).workload_report()
    trend_rows = workload.get("trend", [])
    trend_labels = [row["day"] for row in trend_rows]
    trend_created = [row["created"] for row in trend_rows]
    trend_closed = [row["closed"] for row in trend_rows]
    trend_backlog = [row["backlog_trend"] for row in trend_rows]

    chart_data = {
        "status_labels": ["Открытые", "Приостановленные"],
        "status_values": [
            summary["open_count"],
            summary["suspended_count"],
        ],
        "trend_labels": trend_labels,
        "trend_created": trend_created,
        "trend_closed": trend_closed,
        "trend_backlog": trend_backlog,
    }
    sync_status = request.query_params.get("sync_status")
    history_log = (
        db.query(SyncLog)
        .filter(SyncLog.sync_type == "ticket_history")
        .order_by(desc(SyncLog.started_at))
        .first()
    )
    history_summary = {
        "status": history_log.status if history_log else None,
        "started_at": local_time(history_log.started_at, tz_name) if history_log else None,
        "finished_at": local_time(history_log.finished_at, tz_name) if history_log and history_log.finished_at else None,
        "events": history_log.items_count if history_log else 0,
        "message": history_log.message if history_log else None,
        "stored_events": db.query(func.count(TicketHistory.id)).scalar() or 0,
    }

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "summary": summary,
            "chart_data_json": json.dumps(chart_data, ensure_ascii=False),
            "sync_status": sync_status,
            "history_summary": history_summary,
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


REPORT_VISIBILITY_OPTIONS = [
    ("statuses", "Статусы"), ("agents", "Исполнители"), ("engineers", "Отчет по инженерам"),
    ("sla_first_response", "История SLA: первый ответ"), ("sla_resolution", "История SLA: закрытие"),
    ("sla_current", "Текущие нарушения SLA"), ("groups", "Группы"), ("organizations", "Организации"),
    ("regional_summary", "Сводный отчет"), ("transfers", "Переводы"), ("reopened", "Повторные открытия"),
    ("returns", "Возвраты"), ("engineer_workload", "Нагрузка инженеров"), ("closure_time", "Время закрытия"),
    ("sla", "SLA отчет"), ("workload", "Workload"),
]

@router.get("/admin/report-visibility", response_class=HTMLResponse)
@admin_required_page
def report_visibility_settings(request: Request, db: Session = Depends(get_db)):
    raw = get_app_setting(db, "report_visibility")
    enabled = set(raw.split(",")) if raw else {key for key, _ in REPORT_VISIBILITY_OPTIONS}
    raw_order = get_app_setting(db, "report_order")
    order = [key for key in raw_order.split(",") if key] if raw_order else []
    by_key = dict(REPORT_VISIBILITY_OPTIONS)
    ordered_keys = order + [key for key, _ in REPORT_VISIBILITY_OPTIONS if key not in order]
    reports = [(key, by_key[key]) for key in ordered_keys if key in by_key]
    return templates.TemplateResponse("report_visibility_settings.html", {
        "request": request, "reports": reports, "enabled": enabled,
        "current_user": request.state.current_user,
    })

@router.post("/admin/report-visibility")
@admin_required_page
def report_visibility_settings_save(
    request: Request,
    enabled_reports: list[str] = Form(default=[]),
    report_order: str = Form(""),
    db: Session = Depends(get_db),
):
    allowed = {key for key, _ in REPORT_VISIBILITY_OPTIONS}
    enabled = [key for key in enabled_reports if key in allowed]
    requested_order = [key for key in report_order.split(",") if key in allowed]
    order = requested_order + [key for key, _ in REPORT_VISIBILITY_OPTIONS if key not in requested_order]
    update_app_settings(db, {
        "report_visibility": ",".join(enabled),
        "report_order": ",".join(order),
    })
    return RedirectResponse("/admin/report-visibility", status_code=302)


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
        {
            "request": request,
            "app_settings": app_settings,
            "current_user": request.state.current_user,
        },
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
    if SYNC_LOCK.locked():
        return RedirectResponse("/?sync_status=already_running", status_code=302)

    def _sync_job():
        if not SYNC_LOCK.acquire(blocking=False):
            return
        bg_db = SessionLocal()
        try:
            zammad_url = get_app_setting(bg_db, "zammad_url")
            zammad_token = get_app_setting(bg_db, "zammad_token")
            if not zammad_url or not zammad_token:
                return
            SyncService(bg_db, zammad_url, zammad_token).sync_all()
        finally:
            bg_db.close()
            SYNC_LOCK.release()

    threading.Thread(target=_sync_job, daemon=True).start()
    return RedirectResponse("/?sync_status=started", status_code=302)


@router.get("/reports/transfers", response_class=HTMLResponse)
@login_required_page
def transfers(
    request: Request, date_from: str|None=Query(None), date_to: str|None=Query(None),
    region: str|None=Query(None), engineer_id: str|None=Query(None),
    organization_id: str|None=Query(None), ticket_number: str|None=Query(None),
    sort_by: str=Query("transferred_at"), sort_order: str=Query("desc"),
    db: Session=Depends(get_db),
):
    engineer_id_value = int(engineer_id) if engineer_id and engineer_id.isdigit() else None
    organization_id_value = int(organization_id) if organization_id and organization_id.isdigit() else None
    service = ReportService(db)
    rows = service.ticket_transfers(date_from,date_to,region,engineer_id_value,organization_id_value,ticket_number,sort_by,sort_order)
    options = service.transfer_filter_options()
    return templates.TemplateResponse("transfers.html", {
        "request":request,"rows":rows,"options":options,"date_from":date_from,"date_to":date_to,
        "region":region,"engineer_id":engineer_id_value,"organization_id":organization_id_value,
        "ticket_number":ticket_number,"sort_by":sort_by,"sort_order":sort_order,
        "current_user":request.state.current_user,
    })

@router.post("/sync/history/run")
@login_required_page
def run_history_sync(request: Request, db: Session = Depends(get_db)):
    if SYNC_LOCK.locked():
        return RedirectResponse("/?sync_status=already_running", status_code=302)

    def _history_job():
        if not SYNC_LOCK.acquire(blocking=False):
            return
        bg_db = SessionLocal()
        try:
            zammad_url = get_app_setting(bg_db, "zammad_url")
            zammad_token = get_app_setting(bg_db, "zammad_token")
            if not zammad_url or not zammad_token:
                return
            SyncService(bg_db, zammad_url, zammad_token).sync_ticket_history()
        except Exception as exc:
            print(f"ticket_history background sync failed: {exc}")
        finally:
            bg_db.close()
            SYNC_LOCK.release()

    threading.Thread(target=_history_job, daemon=True).start()
    return RedirectResponse("/?sync_status=history_started", status_code=302)

@router.get("/reports/reopened", response_class=HTMLResponse)
@login_required_page
def reopened(
    request: Request,
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    region: str | None = Query(None),
    engineer_id: str | None = Query(None),
    organization_id: str | None = Query(None),
    ticket_number: str | None = Query(None),
    db: Session = Depends(get_db),
):
    engineer_id_value = int(engineer_id) if engineer_id and engineer_id.isdigit() else None
    organization_id_value = int(organization_id) if organization_id and organization_id.isdigit() else None
    service = ReportService(db)
    rows = service.reopened_tickets(
        date_from, date_to, region, engineer_id_value,
        organization_id_value, ticket_number,
    )
    return templates.TemplateResponse(
        "reopened.html",
        {
            "request": request,
            "rows": rows,
            "options": service.transfer_filter_options(),
            "date_from": date_from,
            "date_to": date_to,
            "region": region,
            "engineer_id": engineer_id_value,
            "organization_id": organization_id_value,
            "ticket_number": ticket_number,
            "current_user": request.state.current_user,
        },
    )

@router.get("/reports/returns", response_class=HTMLResponse)
@login_required_page
def returns_report(
    request: Request,
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    region: str | None = Query(None),
    engineer_id: str | None = Query(None),
    organization_id: str | None = Query(None),
    ticket_number: str | None = Query(None),
    db: Session = Depends(get_db),
):
    engineer_id_value = int(engineer_id) if engineer_id and engineer_id.isdigit() else None
    organization_id_value = int(organization_id) if organization_id and organization_id.isdigit() else None
    service = ReportService(db)
    rows = service.returned_tickets(
        date_from, date_to, region, engineer_id_value,
        organization_id_value, ticket_number,
    )
    return templates.TemplateResponse(
        "returns.html",
        {
            "request": request,
            "rows": rows,
            "options": service.transfer_filter_options(),
            "date_from": date_from,
            "date_to": date_to,
            "region": region,
            "engineer_id": engineer_id_value,
            "organization_id": organization_id_value,
            "ticket_number": ticket_number,
            "current_user": request.state.current_user,
        },
    )

@router.get("/reports/engineer-workload", response_class=HTMLResponse)
@login_required_page
def engineer_workload(
    request: Request,
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    region: str | None = Query(None),
    engineer_id: str | None = Query(None),
    organization_id: str | None = Query(None),
    db: Session = Depends(get_db),
):
    engineer_id_value = int(engineer_id) if engineer_id and engineer_id.isdigit() else None
    organization_id_value = int(organization_id) if organization_id and organization_id.isdigit() else None
    service = ReportService(db)
    rows = service.engineer_activity_report(
        date_from, date_to, region, engineer_id_value, organization_id_value,
    )
    return templates.TemplateResponse("engineer_workload.html", {
        "request": request, "rows": rows, "options": service.transfer_filter_options(),
        "date_from": date_from, "date_to": date_to, "region": region,
        "engineer_id": engineer_id_value, "organization_id": organization_id_value,
        "current_user": request.state.current_user,
    })

@router.get("/reports/closure-time", response_class=HTMLResponse)
@login_required_page
def closure_time(
    request: Request,
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    region: str | None = Query(None),
    engineer_id: str | None = Query(None),
    organization_id: str | None = Query(None),
    db: Session = Depends(get_db),
):
    engineer_id_value = int(engineer_id) if engineer_id and engineer_id.isdigit() else None
    organization_id_value = int(organization_id) if organization_id and organization_id.isdigit() else None
    service = ReportService(db)
    rows = service.closure_time_report(
        date_from, date_to, region, engineer_id_value, organization_id_value,
    )
    return templates.TemplateResponse("closure_time.html", {
        "request": request, "rows": rows, "options": service.transfer_filter_options(),
        "date_from": date_from, "date_to": date_to, "region": region,
        "engineer_id": engineer_id_value, "organization_id": organization_id_value,
        "current_user": request.state.current_user,
    })

@router.get("/reports/engineers", response_class=HTMLResponse)
@login_required_page
def engineers_report(
    request: Request,
    date_from: str | None = Query(None), date_to: str | None = Query(None),
    region: str | None = Query(None), group_id: str | None = Query(None),
    engineer_id: str | None = Query(None), organization_id: str | None = Query(None),
    db: Session = Depends(get_db),
):
    gid = int(group_id) if group_id and group_id.isdigit() else None
    eid = int(engineer_id) if engineer_id and engineer_id.isdigit() else None
    oid = int(organization_id) if organization_id and organization_id.isdigit() else None
    service = ReportService(db)
    rows = service.engineer_report(date_from, date_to, region, gid, eid, oid)
    return templates.TemplateResponse("engineers_report.html", {
        "request": request, "rows": rows, "options": service.engineer_report_filter_options(),
        "date_from": date_from, "date_to": date_to, "region": region,
        "group_id": gid, "engineer_id": eid, "organization_id": oid,
        "current_user": request.state.current_user,
    })

@router.get("/reports/engineers/overdue", response_class=HTMLResponse)
@login_required_page
def engineer_overdue_tickets(
    request: Request,
    date_from: str | None = Query(None), date_to: str | None = Query(None),
    region: str | None = Query(None), group_id: str | None = Query(None),
    engineer_id: str | None = Query(None), organization_id: str | None = Query(None),
    db: Session = Depends(get_db),
):
    gid = int(group_id) if group_id and group_id.isdigit() else None
    eid = int(engineer_id) if engineer_id and engineer_id.isdigit() else None
    oid = int(organization_id) if organization_id and organization_id.isdigit() else None
    service = ReportService(db)
    rows = service.overdue_tickets(region, gid, eid, oid)
    return templates.TemplateResponse("overdue_tickets.html", {
        "request": request, "rows": rows, "current_user": request.state.current_user,
    })

@router.get("/reports/engineers/sla-violations", response_class=HTMLResponse)
@login_required_page
def engineer_sla_violations(
    request: Request,
    violation_type: str = Query(...),
    date_from: str | None = Query(None), date_to: str | None = Query(None),
    region: str | None = Query(None), group_id: str | None = Query(None),
    engineer_id: str | None = Query(None), organization_id: str | None = Query(None),
    db: Session = Depends(get_db),
):
    gid = int(group_id) if group_id and group_id.isdigit() else None
    eid = int(engineer_id) if engineer_id and engineer_id.isdigit() else None
    oid = int(organization_id) if organization_id and organization_id.isdigit() else None
    service = ReportService(db)
    rows = service.sla_violation_tickets(
        violation_type, date_from, date_to, region, gid, eid, oid,
    )
    title = "Нарушения First Response SLA" if violation_type == "first_response" else "Нарушения Resolution SLA"
    return templates.TemplateResponse("sla_violation_tickets.html", {
        "request": request, "rows": rows, "title": title,
        "violation_type": violation_type, "current_user": request.state.current_user,
    })

@router.get("/reports/engineers/tickets", response_class=HTMLResponse)
@login_required_page
def engineer_ticket_details(
    request: Request, metric: str = Query(...),
    date_from: str | None = Query(None), date_to: str | None = Query(None),
    region: str | None = Query(None), group_id: str | None = Query(None),
    engineer_id: str | None = Query(None), organization_id: str | None = Query(None),
    db: Session = Depends(get_db),
):
    gid = int(group_id) if group_id and group_id.isdigit() else None
    eid = int(engineer_id) if engineer_id and engineer_id.isdigit() else None
    oid = int(organization_id) if organization_id and organization_id.isdigit() else None
    service = ReportService(db)
    rows = service.engineer_ticket_details(metric, date_from, date_to, region, gid, eid, oid)
    titles = {
        "assigned": "Назначенные заявки", "closed": "Закрытые заявки",
        "open": "Открытые заявки", "new": "Новые заявки",
    }
    return templates.TemplateResponse("engineer_ticket_details.html", {
        "request": request, "rows": rows, "title": titles.get(metric, "Заявки"),
        "metric": metric, "current_user": request.state.current_user,
    })

@router.get("/reports/sla-violations", response_class=HTMLResponse)
@login_required_page
def sla_violations_report(
    request: Request,
    date_from: str | None = Query(None), date_to: str | None = Query(None),
    region: str | None = Query(None), group_id: str | None = Query(None),
    engineer_id: str | None = Query(None), organization_id: str | None = Query(None),
    violation_type: str | None = Query(None),
    db: Session = Depends(get_db),
):
    gid = int(group_id) if group_id and group_id.isdigit() else None
    eid = int(engineer_id) if engineer_id and engineer_id.isdigit() else None
    oid = int(organization_id) if organization_id and organization_id.isdigit() else None
    service = ReportService(db)
    rows = service.sla_violations_report(
        date_from, date_to, region, gid, eid, oid, violation_type,
    )
    return templates.TemplateResponse("sla_violations_report.html", {
        "request": request, "rows": rows,
        "options": service.engineer_report_filter_options(),
        "date_from": date_from, "date_to": date_to, "region": region,
        "group_id": gid, "engineer_id": eid, "organization_id": oid,
        "violation_type": violation_type or "all",
        "current_user": request.state.current_user,
    })

@router.get("/reports/sla-current", response_class=HTMLResponse)
@login_required_page
def sla_current_report(
    request: Request,
    region: str | None = Query(None), group_id: str | None = Query(None),
    engineer_id: str | None = Query(None), organization_id: str | None = Query(None),
    db: Session = Depends(get_db),
):
    gid = int(group_id) if group_id and group_id.isdigit() else None
    eid = int(engineer_id) if engineer_id and engineer_id.isdigit() else None
    oid = int(organization_id) if organization_id and organization_id.isdigit() else None
    service = ReportService(db)
    rows = service.current_sla_violations(region, gid, eid, oid)
    return templates.TemplateResponse("sla_current_report.html", {
        "request": request, "rows": rows, "options": service.engineer_report_filter_options(),
        "region": region, "group_id": gid, "engineer_id": eid,
        "organization_id": oid, "current_user": request.state.current_user,
    })

@router.get("/reports/overdue", response_class=HTMLResponse)
@login_required_page
def overdue_report(
    request: Request,
    date_from: str | None = Query(None), date_to: str | None = Query(None),
    region: str | None = Query(None), group_id: str | None = Query(None),
    engineer_id: str | None = Query(None), organization_id: str | None = Query(None),
    db: Session = Depends(get_db),
):
    gid = int(group_id) if group_id and group_id.isdigit() else None
    eid = int(engineer_id) if engineer_id and engineer_id.isdigit() else None
    oid = int(organization_id) if organization_id and organization_id.isdigit() else None
    service = ReportService(db)
    rows = service.overdue_tickets(date_from, date_to, region, gid, eid, oid)
    return templates.TemplateResponse("overdue_report.html", {
        "request": request, "rows": rows,
        "date_from": date_from, "date_to": date_to,
        "options": service.engineer_report_filter_options(),
        "region": region, "group_id": gid, "engineer_id": eid,
        "organization_id": oid, "current_user": request.state.current_user,
    })

@router.get("/reports/engineer-workload/details", response_class=HTMLResponse)
@login_required_page
def engineer_workload_details(
    request: Request, metric: str = Query(...),
    date_from: str | None = Query(None), date_to: str | None = Query(None),
    region: str | None = Query(None), engineer_id: str | None = Query(None),
    organization_id: str | None = Query(None),
    db: Session = Depends(get_db),
):
    eid = int(engineer_id) if engineer_id and engineer_id.isdigit() else None
    oid = int(organization_id) if organization_id and organization_id.isdigit() else None
    service = ReportService(db)
    rows = service.engineer_workload_details(
        metric, date_from, date_to, region, eid, oid,
    )
    titles = {
        "assigned": "Назначенные заявки",
        "transferred_in": "Получено переводом",
        "transferred_out": "Передано другому инженеру",
        "closed": "Закрытые заявки",
        "open_now": "Открытые сейчас",
        "overdue_now": "Просроченные сейчас",
    }
    return templates.TemplateResponse("engineer_workload_details.html", {
        "request": request, "rows": rows, "metric": metric,
        "title": titles.get(metric, "Заявки"),
        "current_user": request.state.current_user,
    })

