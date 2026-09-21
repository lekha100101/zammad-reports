import os

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import desc, func
from sqlalchemy.orm import Session
from zoneinfo import ZoneInfo

from app.auth import login_required_page
from app.deps import get_db
from app.models import SyncLog, Ticket, TicketState
from app.services.report_service import ReportService
from app.services.sync_service import SyncService

router = APIRouter(tags=["ui"])
templates = Jinja2Templates(directory="app/templates")


def local_time(dt):
    if not dt: return None
    return dt.replace(tzinfo=ZoneInfo("UTC")).astimezone(ZoneInfo("Asia/Almaty")).strftime("%Y-%m-%d %H:%M:%S")


@router.get("/", response_class=HTMLResponse)
@login_required_page
def index(request: Request, db: Session = Depends(get_db)):
    def count_states(names):
        return db.query(func.count(Ticket.id)).outerjoin(TicketState, Ticket.state_id == TicketState.id).filter(func.lower(TicketState.name).in_(names)).scalar() or 0
    last_sync = db.query(SyncLog).filter(SyncLog.sync_type == "tickets").order_by(desc(SyncLog.started_at)).first()
    summary = {"open_count": count_states(["open","new"]), "closed_count": count_states(["closed"]), "suspended_count": count_states(["suspended"]), "last_sync": local_time(last_sync.started_at) if last_sync else None, "last_sync_count": last_sync.items_count if last_sync else 0}
    return templates.TemplateResponse("index.html", {"request": request, "summary": summary, "current_user": request.state.current_user})


def simple_report(request, template, method, date_from, date_to, db):
    rows = getattr(ReportService(db), method)(date_from, date_to)
    return templates.TemplateResponse(template, {"request":request,"rows":rows,"date_from":date_from,"date_to":date_to,"current_user":request.state.current_user})


@router.get("/reports/statuses", response_class=HTMLResponse)
@login_required_page
def statuses(request: Request, date_from: str|None=Query(None), date_to: str|None=Query(None), db: Session=Depends(get_db)):
    return simple_report(request,"statuses.html","tickets_by_status",date_from,date_to,db)

@router.get("/reports/agents", response_class=HTMLResponse)
@login_required_page
def agents(request: Request, date_from: str|None=Query(None), date_to: str|None=Query(None), db: Session=Depends(get_db)):
    return simple_report(request,"agents.html","tickets_by_agent",date_from,date_to,db)

@router.get("/reports/groups", response_class=HTMLResponse)
@login_required_page
def groups(request: Request, date_from: str|None=Query(None), date_to: str|None=Query(None), db: Session=Depends(get_db)):
    return simple_report(request,"groups.html","tickets_by_group",date_from,date_to,db)

@router.get("/reports/organizations", response_class=HTMLResponse)
@login_required_page
def organizations(request: Request, date_from: str|None=Query(None), date_to: str|None=Query(None), db: Session=Depends(get_db)):
    return simple_report(request,"organizations.html","tickets_by_organization",date_from,date_to,db)

@router.get("/reports/regional-summary", response_class=HTMLResponse)
@login_required_page
def regional_summary(request: Request, date_from: str|None=Query(None), date_to: str|None=Query(None), db: Session=Depends(get_db)):
    rows = ReportService(db).regional_period_report(date_from,date_to) if date_from and date_to else []
    return templates.TemplateResponse("regional_summary.html", {"request":request,"rows":rows,"date_from":date_from,"date_to":date_to,"current_user":request.state.current_user})

@router.get("/reports/transfers", response_class=HTMLResponse)
@login_required_page
def transfers(
    request: Request, date_from: str|None=Query(None), date_to: str|None=Query(None),
    region: str|None=Query(None), engineer_id: int|None=Query(None),
    organization_id: int|None=Query(None), ticket_number: str|None=Query(None),
    sort_by: str=Query("transferred_at"), sort_order: str=Query("desc"),
    db: Session=Depends(get_db),
):
    service = ReportService(db)
    rows = service.ticket_transfers(date_from,date_to,region,engineer_id,organization_id,ticket_number,sort_by,sort_order)
    options = service.transfer_filter_options()
    return templates.TemplateResponse("transfers.html", {
        "request":request,"rows":rows,"options":options,"date_from":date_from,"date_to":date_to,
        "region":region,"engineer_id":engineer_id,"organization_id":organization_id,
        "ticket_number":ticket_number,"sort_by":sort_by,"sort_order":sort_order,
        "current_user":request.state.current_user,
    })

@router.post("/sync/run")
@login_required_page
def run_sync(request: Request, db: Session=Depends(get_db)):
    SyncService(db,os.getenv("ZAMMAD_URL"),os.getenv("ZAMMAD_TOKEN")).sync_all()
    return RedirectResponse("/",status_code=302)
