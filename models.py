from sqlalchemy import Column, Integer, String, DateTime, Text, Float
from app.db import Base

class Ticket(Base):
    __tablename__ = "tickets"

    id = Column(Integer, primary_key=True, index=True)
    number = Column(String(50), index=True)
    title = Column(String(500))
    group_id = Column(Integer, nullable=True)
    owner_id = Column(Integer, nullable=True)
    customer_id = Column(Integer, nullable=True)
    organization_id = Column(Integer, nullable=True)
    state_id = Column(Integer, nullable=True)
    priority_id = Column(Integer, nullable=True)

    created_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=True)
    close_at = Column(DateTime, nullable=True)
    escalation_at = Column(DateTime, nullable=True)
    first_response_at = Column(DateTime, nullable=True)

class TimeAccounting(Base):
    __tablename__ = "time_accountings"

    id = Column(Integer, primary_key=True, index=True)
    ticket_id = Column(Integer, index=True)
    ticket_article_id = Column(Integer, nullable=True)
    time_unit = Column(Float, nullable=True)
    type_id = Column(Integer, nullable=True)
    created_by_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=True)
