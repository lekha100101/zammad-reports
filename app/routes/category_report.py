from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.auth import login_required_page
from app.deps import get_db
from app.routes.ui import templates
from app.services.category_report_service import CategoryReportService
from app.services.report_service import ReportService

router = APIRouter(tags=["category-report"])


@router.get("/reports/categories", response_class=HTMLResponse)
@login_required_page
def category_report(
    request: Request,
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    region: str | None = Query(None),
    group_id: str | None = Query(None),
    engineer_id: str | None = Query(None),
    organization_id: str | None = Query(None),
    category: str | None = Query(None),
    db: Session = Depends(get_db),
):
    gid = int(group_id) if group_id and group_id.isdigit() else None
    eid = int(engineer_id) if engineer_id and engineer_id.isdigit() else None
    oid = int(organization_id) if organization_id and organization_id.isdigit() else None
    data = CategoryReportService(db).report(date_from, date_to, region, gid, eid, oid, category)
    options = ReportService(db).engineer_report_filter_options()
    return templates.TemplateResponse("category_report.html", {
        "request": request, "data": data, "options": options,
        "date_from": date_from, "date_to": date_to, "region": region,
        "group_id": gid, "engineer_id": eid, "organization_id": oid,
        "category": category, "current_user": request.state.current_user,
    })
