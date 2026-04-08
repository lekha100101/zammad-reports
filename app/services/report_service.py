from datetime import datetime, timedelta
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Ticket, User, Group, Organization, TicketState, ReportRegion


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

    def tickets_by_status(self, date_from=None, date_to=None):
        query = (
            self.db.query(
                TicketState.name,
                func.count(Ticket.id)
            )
            .outerjoin(TicketState, Ticket.state_id == TicketState.id)
        )

        dt_from = self._parse_date_start(date_from)
        dt_to = self._parse_date_end(date_to)

        if dt_from:
            query = query.filter(Ticket.created_at >= dt_from)
        if dt_to:
            query = query.filter(Ticket.created_at < dt_to)

        rows = query.group_by(TicketState.name).all()

        return [
            {"status": r[0] or "unknown", "count": r[1]}
            for r in rows
        ]

    def tickets_by_agent(self, date_from=None, date_to=None):
        query = (
            self.db.query(
                User.firstname,
                User.lastname,
                User.login,
                func.count(Ticket.id)
            )
            .join(Ticket, Ticket.owner_id == User.id)
        )

        dt_from = self._parse_date_start(date_from)
        dt_to = self._parse_date_end(date_to)

        if dt_from:
            query = query.filter(Ticket.created_at >= dt_from)
        if dt_to:
            query = query.filter(Ticket.created_at < dt_to)

        rows = query.group_by(
            User.firstname,
            User.lastname,
            User.login
        ).all()

        return [
            {
                "agent": " ".join(
                    [x for x in [r[0], r[1]] if x]
                ).strip() or (r[2] or "Unknown"),
                "login": r[2],
                "count": r[3]
            }
            for r in rows
        ]

    def tickets_by_group(self, date_from=None, date_to=None):
        query = (
            self.db.query(
                Group.name,
                func.count(Ticket.id)
            )
            .join(Ticket, Ticket.group_id == Group.id)
        )

        dt_from = self._parse_date_start(date_from)
        dt_to = self._parse_date_end(date_to)

        if dt_from:
            query = query.filter(Ticket.created_at >= dt_from)
        if dt_to:
            query = query.filter(Ticket.created_at < dt_to)

        rows = query.group_by(Group.name).all()

        return [
            {"group": r[0], "count": r[1]}
            for r in rows
        ]

    def tickets_by_organization(self, date_from=None, date_to=None):
        query = (
            self.db.query(
                Organization.name,
                func.count(Ticket.id)
            )
            .join(Ticket, Ticket.organization_id == Organization.id)
        )

        dt_from = self._parse_date_start(date_from)
        dt_to = self._parse_date_end(date_to)

        if dt_from:
            query = query.filter(Ticket.created_at >= dt_from)
        if dt_to:
            query = query.filter(Ticket.created_at < dt_to)

        rows = query.group_by(Organization.name).all()

        return [
            {"organization": r[0], "count": r[1]}
            for r in rows
        ]

    def format_duration(self, avg_seconds):
        if avg_seconds is None:
            return ""

        total_minutes = int(avg_seconds // 60)
        days = total_minutes // (60 * 24)
        hours = (total_minutes % (60 * 24)) // 60
        minutes = total_minutes % 60

        parts = []
        if days:
            parts.append(f"{days} д")
        if hours:
            parts.append(f"{hours} ч")
        if minutes or not parts:
            parts.append(f"{minutes} мин")

        return " ".join(parts)

    def regional_period_report(self, date_from=None, date_to=None):
        # нормализуем None
        if date_from == "None":
            date_from = None

        if date_to == "None":
            date_to = None

        dt_from = self._parse_date_start(date_from)
        dt_to = self._parse_date_end(date_to)

        if not dt_from or not dt_to:
            return []

        period_end_inclusive = dt_to

        groups = (
            self.db.query(Group.id, Group.name)
            .order_by(Group.name.asc())
            .all()
        )

        result = []

        closed_statuses = ["closed", "merged"]

        for group_id, group_name in groups:
            region = (
                self.db.query(ReportRegion)
                .filter(ReportRegion.group_id == group_id)
                .first()
            )

            if region:
                group_name = region.name

            incoming_count = (
                self.db.query(func.count(Ticket.id))
                .filter(Ticket.group_id == group_id)
                .filter(Ticket.created_at >= dt_from)
                .filter(Ticket.created_at < dt_to)
                .scalar()
                or 0
            )

            closed_count = (
                self.db.query(func.count(Ticket.id))
                .outerjoin(TicketState, Ticket.state_id == TicketState.id)
                .filter(Ticket.group_id == group_id)
                .filter(Ticket.close_at.is_not(None))
                .filter(Ticket.close_at >= dt_from)
                .filter(Ticket.close_at < dt_to)
                .filter(func.lower(TicketState.name).in_(closed_statuses))
                .scalar()
                or 0
            )

            carried_count = (
                self.db.query(func.count(Ticket.id))
                .outerjoin(TicketState, Ticket.state_id == TicketState.id)
                .filter(Ticket.group_id == group_id)
                .filter(Ticket.created_at < period_end_inclusive)
                .filter(
                    (Ticket.close_at.is_(None)) |
                    (Ticket.close_at >= period_end_inclusive)
                )
                .filter(~func.lower(TicketState.name).in_(closed_statuses))
                .scalar()
                or 0
            )

            specialist_rows = (
                self.db.query(
                    User.firstname,
                    User.lastname,
                    User.login,
                    func.count(Ticket.id).label("cnt")
                )
                .join(Ticket, Ticket.owner_id == User.id)
                .outerjoin(TicketState, Ticket.state_id == TicketState.id)
                .filter(Ticket.group_id == group_id)
                .filter(Ticket.close_at.is_not(None))
                .filter(Ticket.close_at >= dt_from)
                .filter(Ticket.close_at < dt_to)
                .filter(func.lower(TicketState.name).in_(closed_statuses))
                .group_by(User.firstname, User.lastname, User.login)
                .order_by(func.count(Ticket.id).desc())
                .all()
            )

            specialist_items = []

            for row in specialist_rows:
                fullname = " ".join([x for x in [row[0], row[1]] if x]).strip()
                specialist_items.append({
                    "name": fullname or row[2] or "Unknown",
                    "count": row[3]
                })


            avg_close_seconds = (
                self.db.query(
                    func.avg(
                        func.extract("epoch", Ticket.close_at) - func.extract("epoch", Ticket.created_at)
                    )
                )
                .outerjoin(TicketState, Ticket.state_id == TicketState.id)
                .filter(Ticket.group_id == group_id)
                .filter(Ticket.close_at.is_not(None))
                .filter(Ticket.created_at.is_not(None))
                .filter(Ticket.close_at >= dt_from)
                .filter(Ticket.close_at < dt_to)
                .filter(func.lower(TicketState.name).in_(closed_statuses))
                .scalar()
            )

            avg_response_seconds = (
                self.db.query(
                    func.avg(
                        func.extract("epoch", Ticket.first_response_at) - func.extract("epoch", Ticket.created_at)
                    )
                )
                .filter(Ticket.group_id == group_id)
                .filter(Ticket.first_response_at.is_not(None))
                .filter(Ticket.created_at.is_not(None))
                .filter(Ticket.created_at >= dt_from)
                .filter(Ticket.created_at < dt_to)
                .scalar()
            )

            if (
                incoming_count == 0 and
                closed_count == 0 and
                carried_count == 0 and
                not specialist_items
            ):
                continue

            result.append({
                "region": group_name,
                "incoming_count": incoming_count,
                "closed_count": closed_count,
                "carried_count": carried_count,
                "specialist_items": specialist_items,
                "avg_close_time": self.format_duration(avg_close_seconds),
                "avg_response_time": self.format_duration(avg_response_seconds),
            })

        return result
