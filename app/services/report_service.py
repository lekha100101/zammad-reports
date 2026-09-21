from datetime import datetime, timedelta
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, aliased

from app.models import (
    Group, Organization, ReportRegion, Ticket, TicketHistory, TicketState, User
)


class ReportService:
    def __init__(self, db: Session):
        self.db = db

    def _parse_date_start(self, v):
        if not v:
            return None
        if isinstance(v, datetime):
            return v
        return datetime.strptime(v, "%Y-%m-%d")

    def _parse_date_end(self, v):
        if not v:
            return None
        if isinstance(v, datetime):
            return v + timedelta(days=1)
        return datetime.strptime(v, "%Y-%m-%d") + timedelta(days=1)

    @staticmethod
    def _user_name(firstname, lastname, login):
        return " ".join(x for x in [firstname, lastname] if x).strip() or login or "Unknown"

    def transfer_filter_options(self):
        regions = (
            self.db.query(ReportRegion.name)
            .filter(ReportRegion.name.is_not(None))
            .distinct().order_by(ReportRegion.name).all()
        )
        users = (
            self.db.query(User.id, User.firstname, User.lastname, User.login)
            .filter(User.active.is_(True))
            .order_by(User.firstname, User.lastname, User.login).all()
        )
        organizations = (
            self.db.query(Organization.id, Organization.name)
            .order_by(Organization.name).all()
        )
        return {
            "regions": [r[0] for r in regions if r[0]],
            "engineers": [
                {"id": u[0], "name": self._user_name(u[1], u[2], u[3])}
                for u in users
            ],
            "organizations": [
                {"id": o[0], "name": o[1] or str(o[0])} for o in organizations
            ],
        }

    def ticket_transfers(
        self, date_from=None, date_to=None, region=None, engineer_id=None,
        organization_id=None, ticket_number=None, sort_by="transferred_at",
        sort_order="desc",
    ):
        previous_user = aliased(User)
        new_user = aliased(User)
        initiator = aliased(User)

        query = (
            self.db.query(
                Ticket.number, Ticket.title, ReportRegion.name, Group.name,
                TicketHistory.id_from, TicketHistory.value_from,
                TicketHistory.id_to, TicketHistory.value_to,
                TicketHistory.created_at,
                initiator.firstname, initiator.lastname, initiator.login,
                Organization.name,
            )
            .join(Ticket, Ticket.id == TicketHistory.ticket_id)
            .outerjoin(Group, Group.id == Ticket.group_id)
            .outerjoin(ReportRegion, ReportRegion.group_id == Ticket.group_id)
            .outerjoin(Organization, Organization.id == Ticket.organization_id)
            .outerjoin(initiator, initiator.id == TicketHistory.created_by_id)
            .filter(TicketHistory.object == "Ticket")
            .filter(TicketHistory.attribute == "owner")
            # Zammad owner id=1/value "-" represents the initial unassigned owner.
            # A transfer must have a real previous and a real new engineer.
            .filter(TicketHistory.id_from.is_not(None))
            .filter(TicketHistory.id_to.is_not(None))
            .filter(TicketHistory.id_from != 1)
            .filter(TicketHistory.id_from != TicketHistory.id_to)
        )

        dt_from = self._parse_date_start(date_from)
        dt_to = self._parse_date_end(date_to)
        if dt_from:
            query = query.filter(TicketHistory.created_at >= dt_from)
        if dt_to:
            query = query.filter(TicketHistory.created_at < dt_to)
        if region:
            query = query.filter(ReportRegion.name == region)
        if engineer_id:
            query = query.filter(or_(
                TicketHistory.id_from == int(engineer_id),
                TicketHistory.id_to == int(engineer_id),
            ))
        if organization_id:
            query = query.filter(Ticket.organization_id == int(organization_id))
        if ticket_number:
            query = query.filter(Ticket.number.ilike(f"%{ticket_number.strip()}%"))

        rows = query.all()
        result = []
        for r in rows:
            result.append({
                "ticket_number": r[0] or "",
                "title": r[1] or "",
                "region": r[2] or r[3] or "",
                "previous_engineer": r[5] or str(r[4] or ""),
                "new_engineer": r[7] or str(r[6] or ""),
                "transferred_at": r[8],
                "initiator": self._user_name(r[9], r[10], r[11]),
                "organization": r[12] or "",
            })

        sort_map = {
            "ticket_number": lambda x: x["ticket_number"],
            "title": lambda x: x["title"].lower(),
            "region": lambda x: x["region"].lower(),
            "previous_engineer": lambda x: x["previous_engineer"].lower(),
            "new_engineer": lambda x: x["new_engineer"].lower(),
            "transferred_at": lambda x: x["transferred_at"] or datetime.min,
            "initiator": lambda x: x["initiator"].lower(),
            "organization": lambda x: x["organization"].lower(),
        }
        key = sort_map.get(sort_by, sort_map["transferred_at"])
        result.sort(key=key, reverse=(sort_order or "").lower() == "desc")
        return result

    def tickets_by_status(self, date_from=None, date_to=None):
        query = self.db.query(TicketState.name, func.count(Ticket.id)).outerjoin(
            TicketState, Ticket.state_id == TicketState.id
        )
        dt_from, dt_to = self._parse_date_start(date_from), self._parse_date_end(date_to)
        if dt_from: query = query.filter(Ticket.created_at >= dt_from)
        if dt_to: query = query.filter(Ticket.created_at < dt_to)
        return [{"status": r[0] or "unknown", "count": r[1]} for r in query.group_by(TicketState.name).all()]

    def tickets_by_agent(self, date_from=None, date_to=None):
        query = self.db.query(User.firstname, User.lastname, User.login, func.count(Ticket.id)).join(Ticket, Ticket.owner_id == User.id)
        dt_from, dt_to = self._parse_date_start(date_from), self._parse_date_end(date_to)
        if dt_from: query = query.filter(Ticket.created_at >= dt_from)
        if dt_to: query = query.filter(Ticket.created_at < dt_to)
        rows = query.group_by(User.firstname, User.lastname, User.login).all()
        return [{"agent": self._user_name(r[0], r[1], r[2]), "login": r[2], "count": r[3]} for r in rows]

    def tickets_by_group(self, date_from=None, date_to=None):
        query = self.db.query(Group.name, func.count(Ticket.id)).join(Ticket, Ticket.group_id == Group.id)
        dt_from, dt_to = self._parse_date_start(date_from), self._parse_date_end(date_to)
        if dt_from: query = query.filter(Ticket.created_at >= dt_from)
        if dt_to: query = query.filter(Ticket.created_at < dt_to)
        return [{"group": r[0], "count": r[1]} for r in query.group_by(Group.name).all()]

    def tickets_by_organization(self, date_from=None, date_to=None):
        query = self.db.query(Organization.name, func.count(Ticket.id)).join(Ticket, Ticket.organization_id == Organization.id)
        dt_from, dt_to = self._parse_date_start(date_from), self._parse_date_end(date_to)
        if dt_from: query = query.filter(Ticket.created_at >= dt_from)
        if dt_to: query = query.filter(Ticket.created_at < dt_to)
        return [{"organization": r[0], "count": r[1]} for r in query.group_by(Organization.name).all()]

    def format_duration(self, avg_seconds):
        if avg_seconds is None: return ""
        total_minutes = int(avg_seconds // 60)
        days, hours, minutes = total_minutes // 1440, (total_minutes % 1440) // 60, total_minutes % 60
        parts = []
        if days: parts.append(f"{days} д")
        if hours: parts.append(f"{hours} ч")
        if minutes or not parts: parts.append(f"{minutes} мин")
        return " ".join(parts)

    def regional_period_report(self, date_from=None, date_to=None):
        if date_from == "None": date_from = None
        if date_to == "None": date_to = None
        dt_from, dt_to = self._parse_date_start(date_from), self._parse_date_end(date_to)
        if not dt_from or not dt_to: return []
        result, closed_statuses = [], ["closed", "merged"]
        for group_id, group_name in self.db.query(Group.id, Group.name).order_by(Group.name.asc()).all():
            region = self.db.query(ReportRegion).filter(ReportRegion.group_id == group_id).first()
            if region: group_name = region.name
            incoming_count = self.db.query(func.count(Ticket.id)).filter(Ticket.group_id == group_id, Ticket.created_at >= dt_from, Ticket.created_at < dt_to).scalar() or 0
            closed_count = self.db.query(func.count(Ticket.id)).outerjoin(TicketState, Ticket.state_id == TicketState.id).filter(Ticket.group_id == group_id, Ticket.close_at.is_not(None), Ticket.close_at >= dt_from, Ticket.close_at < dt_to, func.lower(TicketState.name).in_(closed_statuses)).scalar() or 0
            carried_count = self.db.query(func.count(Ticket.id)).outerjoin(TicketState, Ticket.state_id == TicketState.id).filter(Ticket.group_id == group_id, Ticket.created_at < dt_to, ((Ticket.close_at.is_(None)) | (Ticket.close_at >= dt_to)), ~func.lower(TicketState.name).in_(closed_statuses)).scalar() or 0
            specialist_rows = self.db.query(User.firstname, User.lastname, User.login, func.count(Ticket.id).label("cnt")).join(Ticket, Ticket.owner_id == User.id).outerjoin(TicketState, Ticket.state_id == TicketState.id).filter(Ticket.group_id == group_id, Ticket.close_at.is_not(None), Ticket.close_at >= dt_from, Ticket.close_at < dt_to, func.lower(TicketState.name).in_(closed_statuses)).group_by(User.firstname, User.lastname, User.login).order_by(func.count(Ticket.id).desc()).all()
            specialist_items = [{"name": self._user_name(r[0], r[1], r[2]), "count": r[3]} for r in specialist_rows]
            avg_close_seconds = self.db.query(func.avg(func.extract("epoch", Ticket.close_at) - func.extract("epoch", Ticket.created_at))).outerjoin(TicketState, Ticket.state_id == TicketState.id).filter(Ticket.group_id == group_id, Ticket.close_at.is_not(None), Ticket.created_at.is_not(None), Ticket.close_at >= dt_from, Ticket.close_at < dt_to, func.lower(TicketState.name).in_(closed_statuses)).scalar()
            avg_response_seconds = self.db.query(func.avg(func.extract("epoch", Ticket.first_response_at) - func.extract("epoch", Ticket.created_at))).filter(Ticket.group_id == group_id, Ticket.first_response_at.is_not(None), Ticket.created_at.is_not(None), Ticket.created_at >= dt_from, Ticket.created_at < dt_to).scalar()
            if incoming_count == 0 and closed_count == 0 and carried_count == 0 and not specialist_items: continue
            result.append({"region": group_name, "incoming_count": incoming_count, "closed_count": closed_count, "carried_count": carried_count, "specialist_items": specialist_items, "avg_close_time": self.format_duration(avg_close_seconds), "avg_response_time": self.format_duration(avg_response_seconds)})
        return result
