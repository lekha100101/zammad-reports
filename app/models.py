from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text
from app.db import Base


class AppUser(Base):
    __tablename__ = "app_users"

    id = Column(Integer, primary_key=True)
    username = Column(String(150), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    is_admin = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=True)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    login = Column(String(255), index=True)
    firstname = Column(String(255), nullable=True)
    lastname = Column(String(255), nullable=True)
    email = Column(String(255), index=True, nullable=True)
    organization_id = Column(Integer, nullable=True)
    active = Column(Boolean, default=True)
    updated_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=True)


class Group(Base):
    __tablename__ = "groups"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), index=True)
    note = Column(Text, nullable=True)
    active = Column(Boolean, default=True)
    updated_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=True)


class Organization(Base):
    __tablename__ = "organizations"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), index=True)
    note = Column(Text, nullable=True)
    active = Column(Boolean, default=True)
    updated_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=True)


class TicketState(Base):
    __tablename__ = "ticket_states"

    id = Column(Integer, primary_key=True)
    name = Column(String(255))


class Ticket(Base):
    __tablename__ = "tickets"

    id = Column(Integer, primary_key=True)
    number = Column(String(50), index=True, nullable=True)
    title = Column(String(500), nullable=True)
    group_id = Column(Integer, ForeignKey("groups.id"), nullable=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    customer_id = Column(Integer, nullable=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True)
    state_id = Column(Integer, nullable=True)
    priority_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, nullable=True, index=True)
    updated_at = Column(DateTime, nullable=True)
    close_at = Column(DateTime, nullable=True)
    escalation_at = Column(DateTime, nullable=True)
    first_response_at = Column(DateTime, nullable=True)
    pending_time = Column(DateTime, nullable=True)


class TimeAccounting(Base):
    __tablename__ = "time_accountings"

    id = Column(Integer, primary_key=True)
    ticket_id = Column(Integer, ForeignKey("tickets.id"), index=True)
    ticket_article_id = Column(Integer, nullable=True)
    time_unit = Column(Float, nullable=True)
    type_id = Column(Integer, nullable=True)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, nullable=True, index=True)
    updated_at = Column(DateTime, nullable=True)


class SyncLog(Base):
    __tablename__ = "sync_logs"

    id = Column(Integer, primary_key=True)
    sync_type = Column(String(50), index=True)
    status = Column(String(50), default="started")
    message = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=False)
    finished_at = Column(DateTime, nullable=True)
    items_count = Column(Integer, default=0)


class ReportRegion(Base):
    __tablename__ = "report_regions"

    id = Column(Integer, primary_key=True)
    group_id = Column(Integer, unique=True, index=True)
    name = Column(String, nullable=False)
