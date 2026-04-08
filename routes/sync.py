from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db import get_db
from app.services.sync_service import sync_tickets, sync_time_accountings

router = APIRouter(prefix="/sync", tags=["sync"])

@router.post("/tickets")
def sync_tickets_endpoint(db: Session = Depends(get_db)):
    total = sync_tickets(db)
    return {"synced_tickets": total}

@router.post("/time-accountings")
def sync_time_endpoint(db: Session = Depends(get_db)):
    total = sync_time_accountings(db)
    return {"synced_time_accountings": total}
