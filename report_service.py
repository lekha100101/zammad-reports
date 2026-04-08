import pandas as pd
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models import Ticket, TimeAccounting

def tickets_by_status(db: Session):
    rows = (
        db.query(Ticket.state_id, func.count(Ticket.id))
        .group_by(Ticket.state_id)
        .all()
    )
    return [{"state_id": state_id, "count": count} for state_id, count in rows]

def tickets_by_agent(db: Session):
    rows = (
        db.query(Ticket.owner_id, func.count(Ticket.id))
        .group_by(Ticket.owner_id)
        .all()
    )
    return [{"owner_id": owner_id, "count": count} for owner_id, count in rows]

def time_by_agent(db: Session):
    rows = (
        db.query(TimeAccounting.created_by_id, func.sum(TimeAccounting.time_unit))
        .group_by(TimeAccounting.created_by_id)
        .all()
    )
    return [{"agent_id": agent_id, "minutes": float(minutes or 0)} for agent_id, minutes in rows]

def export_to_excel(data: list[dict], path: str):
    df = pd.DataFrame(data)
    df.to_excel(path, index=False)
    return path
