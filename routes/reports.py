from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from app.db import get_db
from app.services.report_service import (
    tickets_by_status,
    tickets_by_agent,
    time_by_agent,
    export_to_excel,
)

router = APIRouter(prefix="/reports", tags=["reports"])

@router.get("/status")
def report_status(db: Session = Depends(get_db)):
    return tickets_by_status(db)

@router.get("/agents")
def report_agents(db: Session = Depends(get_db)):
    return tickets_by_agent(db)

@router.get("/time")
def report_time(db: Session = Depends(get_db)):
    return time_by_agent(db)

@router.get("/status/export")
def report_status_export(db: Session = Depends(get_db)):
    data = tickets_by_status(db)
    file_path = "/tmp/report_status.xlsx"
    export_to_excel(data, file_path)
    return FileResponse(
        file_path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="report_status.xlsx"
    )
