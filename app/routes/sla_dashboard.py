import json

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.auth import login_required_page
from app.deps import get_db
from app.routes.ui import templates
from app.services.report_service import ReportService
from app.services.sla_dashboard_service import SlaDashboardService

router = APIRouter(tags=["sla-dashboard"])


@router.get("/reports/sla-dashboard", response_class=HTMLResponse)
@login_required_page
def sla_dashboard(
    request: Request,
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    region: str | None = Query(None),
    group_id: str | None = Query(None),
    engineer_id: str | None = Query(None),
    organization_id: str | None = Query(None),
    db: Session = Depends(get_db),
):
    gid = int(group_id) if group_id and group_id.isdigit() else None
    eid = int(engineer_id) if engineer_id and engineer_id.isdigit() else None
    oid = int(organization_id) if organization_id and organization_id.isdigit() else None

    data = SlaDashboardService(db).report(date_from, date_to, region, gid, eid, oid)
    options = ReportService(db).engineer_report_filter_options()

    return templates.TemplateResponse("sla_dashboard.html", {
        "request": request,
        "data": data,
        "summary": data["summary"],
        "rows": data["engineers"],
        "chart_data_json": json.dumps(data["trend"], ensure_ascii=False),
        "options": options,
        "date_from": date_from,
        "date_to": date_to,
        "region": region,
        "group_id": gid,
        "engineer_id": eid,
        "organization_id": oid,
        "current_user": request.state.current_user,
    })
