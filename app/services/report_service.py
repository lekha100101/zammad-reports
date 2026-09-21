from datetime import datetime, timedelta
from sqlalchemy import and_, case, cast, Date, func, or_
from sqlalchemy.orm import Session, aliased

from app.models import Ticket, User, Group, Organization, TicketState, ReportRegion, TicketHistory
from app.services.metric_settings_service import get_metric_int


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
                func.coalesce(ReportRegion.name, Group.name).label("group_name"),
                func.count(Ticket.id)
            )
            .select_from(Group)
            .join(Ticket, Ticket.group_id == Group.id)
            .outerjoin(ReportRegion, ReportRegion.group_id == Group.id)
        )

        dt_from = self._parse_date_start(date_from)
        dt_to = self._parse_date_end(date_to)

        if dt_from:
            query = query.filter(Ticket.created_at >= dt_from)
        if dt_to:
            query = query.filter(Ticket.created_at < dt_to)

        rows = query.group_by(func.coalesce(ReportRegion.name, Group.name)).all()

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
        if date_from == "None":
            date_from = None
        if date_to == "None":
            date_to = None

        dt_from = self._parse_date_start(date_from)
        dt_to = self._parse_date_end(date_to)

        if not dt_from or not dt_to:
            return []

        period_end_inclusive = dt_to
        closed_statuses = ["closed", "merged"]
        groups = self.db.query(Group.id, Group.name).order_by(Group.name.asc()).all()
        regions = {
            row.group_id: row.name
            for row in self.db.query(ReportRegion.group_id, ReportRegion.name).all()
        }

        incoming_map = {
            row.group_id: int(row.cnt or 0)
            for row in (
                self.db.query(Ticket.group_id.label("group_id"), func.count(Ticket.id).label("cnt"))
                .filter(Ticket.created_at >= dt_from, Ticket.created_at < dt_to)
                .group_by(Ticket.group_id)
                .all()
            )
        }

        closed_map = {
            row.group_id: int(row.cnt or 0)
            for row in (
                self.db.query(Ticket.group_id.label("group_id"), func.count(Ticket.id).label("cnt"))
                .outerjoin(TicketState, Ticket.state_id == TicketState.id)
                .filter(
                    Ticket.close_at.is_not(None),
                    Ticket.close_at >= dt_from,
                    Ticket.close_at < dt_to,
                    func.lower(TicketState.name).in_(closed_statuses),
                )
                .group_by(Ticket.group_id)
                .all()
            )
        }

        carried_map = {
            row.group_id: int(row.cnt or 0)
            for row in (
                self.db.query(Ticket.group_id.label("group_id"), func.count(Ticket.id).label("cnt"))
                .outerjoin(TicketState, Ticket.state_id == TicketState.id)
                .filter(Ticket.created_at < period_end_inclusive)
                .filter((Ticket.close_at.is_(None)) | (Ticket.close_at >= period_end_inclusive))
                .filter(or_(TicketState.name.is_(None), ~func.lower(TicketState.name).in_(closed_statuses)))
                .group_by(Ticket.group_id)
                .all()
            )
        }

        specialist_map = {}
        specialist_rows = (
            self.db.query(
                Ticket.group_id.label("group_id"),
                User.firstname,
                User.lastname,
                User.login,
                func.count(Ticket.id).label("cnt"),
            )
            .join(User, Ticket.owner_id == User.id)
            .outerjoin(TicketState, Ticket.state_id == TicketState.id)
            .filter(
                Ticket.close_at.is_not(None),
                Ticket.close_at >= dt_from,
                Ticket.close_at < dt_to,
                func.lower(TicketState.name).in_(closed_statuses),
            )
            .group_by(Ticket.group_id, User.firstname, User.lastname, User.login)
            .order_by(Ticket.group_id.asc(), func.count(Ticket.id).desc())
            .all()
        )
        for row in specialist_rows:
            fullname = " ".join([x for x in [row.firstname, row.lastname] if x]).strip()
            specialist_map.setdefault(row.group_id, []).append(
                {"name": fullname or row.login or "Unknown", "count": int(row.cnt or 0)}
            )

        avg_close_map = {
            row.group_id: row.avg_seconds
            for row in (
                self.db.query(
                    Ticket.group_id.label("group_id"),
                    func.avg(
                        func.extract("epoch", Ticket.close_at) - func.extract("epoch", Ticket.created_at)
                    ).label("avg_seconds"),
                )
                .outerjoin(TicketState, Ticket.state_id == TicketState.id)
                .filter(
                    Ticket.close_at.is_not(None),
                    Ticket.created_at.is_not(None),
                    Ticket.close_at >= dt_from,
                    Ticket.close_at < dt_to,
                    func.lower(TicketState.name).in_(closed_statuses),
                )
                .group_by(Ticket.group_id)
                .all()
            )
        }

        avg_response_map = {
            row.group_id: row.avg_seconds
            for row in (
                self.db.query(
                    Ticket.group_id.label("group_id"),
                    func.avg(
                        func.extract("epoch", Ticket.first_response_at) - func.extract("epoch", Ticket.created_at)
                    ).label("avg_seconds"),
                )
                .filter(
                    Ticket.first_response_at.is_not(None),
                    Ticket.created_at.is_not(None),
                    Ticket.created_at >= dt_from,
                    Ticket.created_at < dt_to,
                )
                .group_by(Ticket.group_id)
                .all()
            )
        }

        result = []
        for group_id, group_name in groups:
            display_name = regions.get(group_id, group_name)
            incoming_count = incoming_map.get(group_id, 0)
            closed_count = closed_map.get(group_id, 0)
            carried_count = carried_map.get(group_id, 0)
            specialist_items = specialist_map.get(group_id, [])
            avg_close_seconds = avg_close_map.get(group_id)
            avg_response_seconds = avg_response_map.get(group_id)

            if incoming_count == 0 and closed_count == 0 and carried_count == 0 and not specialist_items:
                continue

            result.append(
                {
                    "region": display_name,
                    "incoming_count": incoming_count,
                    "closed_count": closed_count,
                    "carried_count": carried_count,
                    "specialist_items": specialist_items,
                    "avg_close_time": self.format_duration(avg_close_seconds),
                    "avg_response_time": self.format_duration(avg_response_seconds),
                }
            )

        return result

    def sla_report(self, date_from=None, date_to=None):
        dt_from = self._parse_date_start(date_from)
        dt_to = self._parse_date_end(date_to)

        response_sla_seconds = get_metric_int(self.db, "sla_response_minutes") * 60
        resolution_sla_seconds = get_metric_int(self.db, "sla_resolution_hours") * 60 * 60

        query = (
            self.db.query(
                func.coalesce(ReportRegion.name, Group.name).label("group_name"),
                func.count(Ticket.id).label("total"),
                func.sum(
                    case(
                        (
                            and_(
                                Ticket.first_response_at.is_not(None),
                                (func.extract("epoch", Ticket.first_response_at) - func.extract("epoch", Ticket.created_at)) <= response_sla_seconds,
                            ),
                            1,
                        ),
                        else_=0,
                    )
                ).label("response_in_sla"),
                func.sum(
                    case(
                        (
                            and_(
                                Ticket.close_at.is_not(None),
                                (func.extract("epoch", Ticket.close_at) - func.extract("epoch", Ticket.created_at)) <= resolution_sla_seconds,
                            ),
                            1,
                        ),
                        else_=0,
                    )
                ).label("resolution_in_sla"),
            )
            .outerjoin(Group, Ticket.group_id == Group.id)
            .outerjoin(ReportRegion, ReportRegion.group_id == Group.id)
        )

        if dt_from:
            query = query.filter(Ticket.created_at >= dt_from)
        if dt_to:
            query = query.filter(Ticket.created_at < dt_to)

        rows = (
            query.group_by(func.coalesce(ReportRegion.name, Group.name))
            .order_by(func.coalesce(ReportRegion.name, Group.name).asc())
            .all()
        )

        result = []
        for row in rows:
            total = int(row.total or 0)
            response_ok = int(row.response_in_sla or 0)
            resolution_ok = int(row.resolution_in_sla or 0)

            result.append(
                {
                    "group": row.group_name or "Без группы",
                    "total": total,
                    "response_in_sla": response_ok,
                    "response_sla_pct": round((response_ok / total) * 100, 1) if total else 0,
                    "resolution_in_sla": resolution_ok,
                    "resolution_sla_pct": round((resolution_ok / total) * 100, 1) if total else 0,
                }
            )

        return result

    def workload_report(self, date_from=None, date_to=None):
        dt_from = self._parse_date_start(date_from)
        dt_to = self._parse_date_end(date_to)

        closed_statuses = ["closed", "merged"]

        open_agents = (
            self.db.query(
                User.firstname,
                User.lastname,
                User.login,
                func.count(Ticket.id).label("open_count"),
                func.avg(func.extract("epoch", func.now()) - func.extract("epoch", Ticket.created_at)).label("avg_age_sec"),
            )
            .join(Ticket, Ticket.owner_id == User.id)
            .outerjoin(TicketState, Ticket.state_id == TicketState.id)
            .filter(or_(TicketState.name.is_(None), ~func.lower(TicketState.name).in_(closed_statuses)))
        )

        if dt_from:
            open_agents = open_agents.filter(Ticket.created_at >= dt_from)
        if dt_to:
            open_agents = open_agents.filter(Ticket.created_at < dt_to)

        open_agents = (
            open_agents.group_by(User.firstname, User.lastname, User.login)
            .order_by(func.count(Ticket.id).desc())
            .all()
        )

        agent_rows = []
        for row in open_agents:
            fullname = " ".join([x for x in [row[0], row[1]] if x]).strip() or (row[2] or "Unknown")
            agent_rows.append(
                {
                    "agent": fullname,
                    "open_count": int(row[3] or 0),
                    "avg_age": self.format_duration(row[4]),
                }
            )

        trend_from = dt_from or (datetime.utcnow() - timedelta(days=13))
        trend_to = dt_to or (datetime.utcnow() + timedelta(days=1))

        created_daily = (
            self.db.query(
                cast(Ticket.created_at, Date).label("day"),
                func.count(Ticket.id).label("cnt"),
            )
            .filter(Ticket.created_at >= trend_from)
            .filter(Ticket.created_at < trend_to)
            .group_by(cast(Ticket.created_at, Date))
            .all()
        )
        closed_daily = (
            self.db.query(
                cast(Ticket.close_at, Date).label("day"),
                func.count(Ticket.id).label("cnt"),
            )
            .outerjoin(TicketState, Ticket.state_id == TicketState.id)
            .filter(Ticket.close_at.is_not(None))
            .filter(Ticket.close_at >= trend_from)
            .filter(Ticket.close_at < trend_to)
            .filter(func.lower(TicketState.name).in_(closed_statuses))
            .group_by(cast(Ticket.close_at, Date))
            .all()
        )

        created_map = {str(r.day): int(r.cnt or 0) for r in created_daily}
        closed_map = {str(r.day): int(r.cnt or 0) for r in closed_daily}

        trend_rows = []
        day = trend_from.date()
        end_day = (trend_to - timedelta(days=1)).date()
        backlog = 0
        while day <= end_day:
            key = str(day)
            created = created_map.get(key, 0)
            closed = closed_map.get(key, 0)
            backlog += created - closed
            trend_rows.append(
                {
                    "day": key,
                    "created": created,
                    "closed": closed,
                    "delta": created - closed,
                    "backlog_trend": backlog,
                }
            )
            day += timedelta(days=1)

        return {"agents": agent_rows, "trend": trend_rows}

    def time_accounting_report(self, date_from=None, date_to=None):
        dt_from = self._parse_date_start(date_from)
        dt_to = self._parse_date_end(date_to)

        from app.models import TimeAccounting

        period_col = func.coalesce(TimeAccounting.created_at, TimeAccounting.updated_at)
        query = (
            self.db.query(
                TimeAccounting.created_by_id.label("user_id"),
                Ticket.group_id.label("group_id"),
                func.sum(TimeAccounting.time_unit).label("time_units"),
            )
            .outerjoin(Ticket, TimeAccounting.ticket_id == Ticket.id)
        )

        if dt_from:
            query = query.filter(period_col >= dt_from)
        if dt_to:
            query = query.filter(period_col < dt_to)

        rows = (
            query.group_by(
                TimeAccounting.created_by_id,
                Ticket.group_id,
            )
            .order_by(func.sum(TimeAccounting.time_unit).desc())
            .all()
        )

        users = {
            u.id: (" ".join([x for x in [u.firstname, u.lastname] if x]).strip() or (u.login or "Unknown"))
            for u in self.db.query(User.id, User.firstname, User.lastname, User.login).all()
        }
        groups = {g.id: g.name for g in self.db.query(Group.id, Group.name).all()}
        regions = {r.group_id: r.name for r in self.db.query(ReportRegion.group_id, ReportRegion.name).all()}

        result = []
        for row in rows:
            fullname = users.get(row.user_id, "Unknown")
            display_group = regions.get(row.group_id) or groups.get(row.group_id) or "Без группы"
            units = float(row.time_units or 0)
            result.append(
                {
                    "agent": fullname,
                    "group": display_group,
                    "minutes": round(units, 2),
                    "hours": round(units / 60, 2),
                }
            )

        return result

    def transfer_filter_options(self):
        regions = (
            self.db.query(ReportRegion.name)
            .filter(ReportRegion.name.is_not(None))
            .distinct()
            .order_by(ReportRegion.name)
            .all()
        )
        users = (
            self.db.query(User.id, User.firstname, User.lastname, User.login)
            .filter(User.active.is_(True))
            .order_by(User.firstname, User.lastname, User.login)
            .all()
        )
        organizations = (
            self.db.query(Organization.id, Organization.name)
            .order_by(Organization.name)
            .all()
        )
        return {
            "regions": [row[0] for row in regions if row[0]],
            "engineers": [
                {
                    "id": row[0],
                    "name": self._user_name(row[1], row[2], row[3]),
                }
                for row in users
            ],
            "organizations": [
                {"id": row[0], "name": row[1] or str(row[0])}
                for row in organizations
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

    def reopened_tickets(
        self,
        date_from=None,
        date_to=None,
        region=None,
        engineer_id=None,
        organization_id=None,
        ticket_number=None,
    ):
        """Return transitions from a closed state back to open/new.

        Zammad history stores state names in value_from/value_to, which lets us
        reconstruct reopen events without relying on the ticket's current state.
        """
        dt_from = self._parse_date_start(date_from)
        dt_to = self._parse_date_end(date_to)
        closed_states = ["closed", "merged"]
        open_states = ["open", "new"]

        owner = aliased(User)
        query = (
            self.db.query(
                Ticket.number.label("ticket_number"),
                Ticket.title.label("title"),
                func.coalesce(ReportRegion.name, Group.name).label("region"),
                owner.firstname,
                owner.lastname,
                owner.login,
                Organization.name.label("organization"),
                TicketHistory.value_from.label("previous_state"),
                TicketHistory.value_to.label("new_state"),
                TicketHistory.created_at.label("reopened_at"),
            )
            .join(Ticket, Ticket.id == TicketHistory.ticket_id)
            .outerjoin(Group, Group.id == Ticket.group_id)
            .outerjoin(ReportRegion, ReportRegion.group_id == Ticket.group_id)
            .outerjoin(Organization, Organization.id == Ticket.organization_id)
            .outerjoin(owner, owner.id == Ticket.owner_id)
            .filter(TicketHistory.object == "Ticket")
            .filter(TicketHistory.attribute == "state")
            .filter(func.lower(TicketHistory.value_from).in_(closed_states))
            .filter(func.lower(TicketHistory.value_to).in_(open_states))
        )

        if dt_from:
            query = query.filter(TicketHistory.created_at >= dt_from)
        if dt_to:
            query = query.filter(TicketHistory.created_at < dt_to)
        if region:
            query = query.filter(func.coalesce(ReportRegion.name, Group.name) == region)
        if engineer_id:
            query = query.filter(Ticket.owner_id == engineer_id)
        if organization_id:
            query = query.filter(Ticket.organization_id == organization_id)
        if ticket_number:
            query = query.filter(Ticket.number.ilike(f"%{ticket_number.strip()}%"))

        rows = query.order_by(TicketHistory.created_at.desc()).all()
        return [
            {
                "ticket_number": row.ticket_number,
                "title": row.title or "",
                "region": row.region or "Без группы",
                "engineer": self._user_name(row.firstname, row.lastname, row.login),
                "organization": row.organization or "",
                "previous_state": row.previous_state or "",
                "new_state": row.new_state or "",
                "reopened_at": row.reopened_at,
            }
            for row in rows
        ]

    def returned_tickets(
        self,
        date_from=None,
        date_to=None,
        region=None,
        engineer_id=None,
        organization_id=None,
        ticket_number=None,
    ):
        """Return owner changes where a ticket is assigned back to a previous owner.

        Operational definition: A -> B -> A (or any later reassignment to an owner
        who already owned the ticket). Initial assignment from owner id 1 is ignored.
        """
        dt_from = self._parse_date_start(date_from)
        dt_to = self._parse_date_end(date_to)

        query = (
            self.db.query(TicketHistory)
            .filter(TicketHistory.object == "Ticket")
            .filter(TicketHistory.attribute == "owner")
            .filter(TicketHistory.id_from.is_not(None))
            .filter(TicketHistory.id_to.is_not(None))
            .filter(TicketHistory.id_from != TicketHistory.id_to)
            .order_by(TicketHistory.ticket_id.asc(), TicketHistory.created_at.asc(), TicketHistory.id.asc())
        )

        histories = query.all()
        ticket_ids = {h.ticket_id for h in histories}
        tickets = {
            t.id: t
            for t in self.db.query(Ticket).filter(Ticket.id.in_(ticket_ids)).all()
        } if ticket_ids else {}
        user_ids = {
            value
            for h in histories
            for value in (h.id_from, h.id_to, h.created_by_id)
            if value is not None
        }
        users = {
            u.id: self._user_name(u.firstname, u.lastname, u.login)
            for u in self.db.query(User).filter(User.id.in_(user_ids)).all()
        } if user_ids else {}
        groups = {g.id: g.name for g in self.db.query(Group.id, Group.name).all()}
        regions = {r.group_id: r.name for r in self.db.query(ReportRegion.group_id, ReportRegion.name).all()}
        organizations = {o.id: o.name for o in self.db.query(Organization.id, Organization.name).all()}

        seen_owners = {}
        result = []
        for h in histories:
            seen = seen_owners.setdefault(h.ticket_id, set())
            if h.id_from not in (None, 1):
                seen.add(h.id_from)

            is_return = h.id_to not in (None, 1) and h.id_to in seen
            seen.add(h.id_to)

            if not is_return:
                continue
            if dt_from and (not h.created_at or h.created_at < dt_from):
                continue
            if dt_to and (not h.created_at or h.created_at >= dt_to):
                continue

            ticket = tickets.get(h.ticket_id)
            if not ticket:
                continue
            display_region = regions.get(ticket.group_id) or groups.get(ticket.group_id) or "Без группы"
            if region and display_region != region:
                continue
            if engineer_id and h.id_to != engineer_id:
                continue
            if organization_id and ticket.organization_id != organization_id:
                continue
            if ticket_number and ticket_number.strip().lower() not in (ticket.number or "").lower():
                continue

            result.append({
                "ticket_number": ticket.number or str(ticket.id),
                "title": ticket.title or "",
                "region": display_region,
                "from_engineer": users.get(h.id_from, h.value_from or str(h.id_from)),
                "returned_to": users.get(h.id_to, h.value_to or str(h.id_to)),
                "returned_at": h.created_at,
                "initiator": users.get(h.created_by_id, str(h.created_by_id) if h.created_by_id else ""),
                "organization": organizations.get(ticket.organization_id, ""),
            })

        result.sort(key=lambda row: row["returned_at"] or datetime.min, reverse=True)
        return result

    def engineer_activity_report(
        self, date_from=None, date_to=None, region=None,
        engineer_id=None, organization_id=None,
    ):
        """Engineer workload for a period using owner history plus ticket outcomes."""
        dt_from = self._parse_date_start(date_from)
        dt_to = self._parse_date_end(date_to)
        closed_states = ["closed", "merged"]

        users = {
            u.id: self._user_name(u.firstname, u.lastname, u.login)
            for u in self.db.query(User).filter(User.active.is_(True)).all()
        }
        groups = {g.id: g.name for g in self.db.query(Group.id, Group.name).all()}
        regions = {r.group_id: r.name for r in self.db.query(ReportRegion.group_id, ReportRegion.name).all()}

        # Assignment events in the selected period. Initial assignment is included;
        # system/unassigned owner id 1 is excluded.
        aq = (
            self.db.query(TicketHistory, Ticket)
            .join(Ticket, Ticket.id == TicketHistory.ticket_id)
            .filter(TicketHistory.object == "Ticket")
            .filter(TicketHistory.attribute == "owner")
            .filter(TicketHistory.id_to.is_not(None))
            .filter(TicketHistory.id_to != 1)
        )
        if dt_from:
            aq = aq.filter(TicketHistory.created_at >= dt_from)
        if dt_to:
            aq = aq.filter(TicketHistory.created_at < dt_to)
        if organization_id:
            aq = aq.filter(Ticket.organization_id == organization_id)

        stats = {}
        for h, ticket in aq.all():
            if engineer_id and h.id_to != engineer_id:
                continue
            display_region = regions.get(ticket.group_id) or groups.get(ticket.group_id) or "Без группы"
            if region and display_region != region:
                continue
            key = (h.id_to, ticket.group_id)
            item = stats.setdefault(key, {
                "engineer_id": h.id_to,
                "engineer": users.get(h.id_to, h.value_to or str(h.id_to)),
                "region": display_region,
                "assigned": 0,
                "transferred_in": 0,
                "transferred_out": 0,
                "closed": 0,
                "open_now": 0,
            })
            item["assigned"] += 1
            if h.id_from not in (None, 1):
                item["transferred_in"] += 1

        # Transfers out during the period.
        oq = (
            self.db.query(TicketHistory, Ticket)
            .join(Ticket, Ticket.id == TicketHistory.ticket_id)
            .filter(TicketHistory.object == "Ticket")
            .filter(TicketHistory.attribute == "owner")
            .filter(TicketHistory.id_from.is_not(None))
            .filter(TicketHistory.id_from != 1)
            .filter(TicketHistory.id_from != TicketHistory.id_to)
        )
        if dt_from:
            oq = oq.filter(TicketHistory.created_at >= dt_from)
        if dt_to:
            oq = oq.filter(TicketHistory.created_at < dt_to)
        if organization_id:
            oq = oq.filter(Ticket.organization_id == organization_id)
        for h, ticket in oq.all():
            if engineer_id and h.id_from != engineer_id:
                continue
            display_region = regions.get(ticket.group_id) or groups.get(ticket.group_id) or "Без группы"
            if region and display_region != region:
                continue
            key = (h.id_from, ticket.group_id)
            item = stats.setdefault(key, {
                "engineer_id": h.id_from,
                "engineer": users.get(h.id_from, h.value_from or str(h.id_from)),
                "region": display_region,
                "assigned": 0, "transferred_in": 0, "transferred_out": 0,
                "closed": 0, "open_now": 0,
            })
            item["transferred_out"] += 1

        # Tickets closed in the period are attributed to their current/final owner.
        cq = (
            self.db.query(Ticket)
            .outerjoin(TicketState, Ticket.state_id == TicketState.id)
            .filter(Ticket.close_at.is_not(None))
            .filter(func.lower(TicketState.name).in_(closed_states))
        )
        if dt_from:
            cq = cq.filter(Ticket.close_at >= dt_from)
        if dt_to:
            cq = cq.filter(Ticket.close_at < dt_to)
        if organization_id:
            cq = cq.filter(Ticket.organization_id == organization_id)
        for ticket in cq.all():
            if not ticket.owner_id or ticket.owner_id == 1:
                continue
            if engineer_id and ticket.owner_id != engineer_id:
                continue
            display_region = regions.get(ticket.group_id) or groups.get(ticket.group_id) or "Без группы"
            if region and display_region != region:
                continue
            key = (ticket.owner_id, ticket.group_id)
            item = stats.setdefault(key, {
                "engineer_id": ticket.owner_id,
                "engineer": users.get(ticket.owner_id, str(ticket.owner_id)),
                "region": display_region,
                "assigned": 0, "transferred_in": 0, "transferred_out": 0,
                "closed": 0, "open_now": 0,
            })
            item["closed"] += 1

        # Current open backlog by engineer/region.
        openq = (
            self.db.query(Ticket)
            .outerjoin(TicketState, Ticket.state_id == TicketState.id)
            .filter(or_(TicketState.name.is_(None), ~func.lower(TicketState.name).in_(closed_states)))
        )
        if organization_id:
            openq = openq.filter(Ticket.organization_id == organization_id)
        for ticket in openq.all():
            if not ticket.owner_id or ticket.owner_id == 1:
                continue
            if engineer_id and ticket.owner_id != engineer_id:
                continue
            display_region = regions.get(ticket.group_id) or groups.get(ticket.group_id) or "Без группы"
            if region and display_region != region:
                continue
            key = (ticket.owner_id, ticket.group_id)
            item = stats.setdefault(key, {
                "engineer_id": ticket.owner_id,
                "engineer": users.get(ticket.owner_id, str(ticket.owner_id)),
                "region": display_region,
                "assigned": 0, "transferred_in": 0, "transferred_out": 0,
                "closed": 0, "open_now": 0,
            })
            item["open_now"] += 1

        rows = list(stats.values())
        for row in rows:
            row["net_flow"] = row["transferred_in"] - row["transferred_out"]
        rows.sort(key=lambda x: (-x["assigned"], -x["closed"], x["engineer"], x["region"]))
        return rows

    def closure_time_report(
        self, date_from=None, date_to=None, region=None,
        engineer_id=None, organization_id=None,
    ):
        """Closure-time statistics by final engineer and region."""
        dt_from = self._parse_date_start(date_from)
        dt_to = self._parse_date_end(date_to)
        closed_states = ["closed", "merged"]

        query = (
            self.db.query(
                Ticket.owner_id.label("engineer_id"),
                Ticket.group_id.label("group_id"),
                func.count(Ticket.id).label("closed_count"),
                func.avg(
                    func.extract("epoch", Ticket.close_at) -
                    func.extract("epoch", Ticket.created_at)
                ).label("avg_seconds"),
                func.percentile_cont(0.5).within_group(
                    func.extract("epoch", Ticket.close_at) -
                    func.extract("epoch", Ticket.created_at)
                ).label("median_seconds"),
                func.min(
                    func.extract("epoch", Ticket.close_at) -
                    func.extract("epoch", Ticket.created_at)
                ).label("min_seconds"),
                func.max(
                    func.extract("epoch", Ticket.close_at) -
                    func.extract("epoch", Ticket.created_at)
                ).label("max_seconds"),
            )
            .outerjoin(TicketState, Ticket.state_id == TicketState.id)
            .filter(Ticket.close_at.is_not(None))
            .filter(Ticket.created_at.is_not(None))
            .filter(Ticket.close_at >= Ticket.created_at)
            .filter(func.lower(TicketState.name).in_(closed_states))
            .filter(Ticket.owner_id.is_not(None))
            .filter(Ticket.owner_id != 1)
        )
        if dt_from:
            query = query.filter(Ticket.close_at >= dt_from)
        if dt_to:
            query = query.filter(Ticket.close_at < dt_to)
        if engineer_id:
            query = query.filter(Ticket.owner_id == engineer_id)
        if organization_id:
            query = query.filter(Ticket.organization_id == organization_id)

        rows = query.group_by(Ticket.owner_id, Ticket.group_id).all()
        users = {
            u.id: self._user_name(u.firstname, u.lastname, u.login)
            for u in self.db.query(User).all()
        }
        groups = {g.id: g.name for g in self.db.query(Group.id, Group.name).all()}
        regions = {r.group_id: r.name for r in self.db.query(ReportRegion.group_id, ReportRegion.name).all()}

        result = []
        for row in rows:
            display_region = regions.get(row.group_id) or groups.get(row.group_id) or "Без группы"
            if region and display_region != region:
                continue
            result.append({
                "engineer_id": row.engineer_id,
                "engineer": users.get(row.engineer_id, str(row.engineer_id)),
                "region": display_region,
                "closed_count": int(row.closed_count or 0),
                "avg_time": self.format_duration(row.avg_seconds),
                "median_time": self.format_duration(row.median_seconds),
                "min_time": self.format_duration(row.min_seconds),
                "max_time": self.format_duration(row.max_seconds),
                "avg_seconds": float(row.avg_seconds or 0),
            })
        # Find the slowest closed ticket for every engineer/region row.
        for item in result:
            slowq = (
                self.db.query(
                    Ticket.number,
                    (
                        func.extract("epoch", Ticket.close_at) -
                        func.extract("epoch", Ticket.created_at)
                    ).label("duration_seconds"),
                )
                .outerjoin(TicketState, Ticket.state_id == TicketState.id)
                .filter(Ticket.owner_id == item["engineer_id"])
                .filter(Ticket.close_at.is_not(None), Ticket.created_at.is_not(None))
                .filter(Ticket.close_at >= Ticket.created_at)
                .filter(func.lower(TicketState.name).in_(closed_states))
            )
            group_id = next(
                (
                    gid for gid, name in groups.items()
                    if (regions.get(gid) or name or "Без группы") == item["region"]
                ),
                None,
            )
            if group_id is not None:
                slowq = slowq.filter(Ticket.group_id == group_id)
            if dt_from:
                slowq = slowq.filter(Ticket.close_at >= dt_from)
            if dt_to:
                slowq = slowq.filter(Ticket.close_at < dt_to)
            if organization_id:
                slowq = slowq.filter(Ticket.organization_id == organization_id)

            slowest = slowq.order_by(
                (
                    func.extract("epoch", Ticket.close_at) -
                    func.extract("epoch", Ticket.created_at)
                ).desc()
            ).first()
            item["max_ticket_number"] = slowest.number if slowest else ""
            item["max_ticket_time"] = self.format_duration(
                slowest.duration_seconds if slowest else None
            )

        result.sort(key=lambda x: (-x["closed_count"], x["avg_seconds"], x["engineer"], x["region"]))
        return result

    def engineer_report(
        self, date_from=None, date_to=None, region=None,
        group_id=None, engineer_id=None, organization_id=None,
    ):
        """3.1 Engineer report.

        Period is based on ticket creation for assigned/open/new and on close_at
        for closed tickets. SLA thresholds use configured report metrics.
        """
        dt_from = self._parse_date_start(date_from)
        dt_to = self._parse_date_end(date_to)
        response_limit = get_metric_int(self.db, "sla_response_minutes") * 60
        resolution_limit = get_metric_int(self.db, "sla_resolution_hours") * 3600
        closed_states = ["closed", "merged"]
        open_states = ["open"]
        new_states = ["new"]

        q = (
            self.db.query(Ticket, TicketState.name.label("state_name"))
            .outerjoin(TicketState, Ticket.state_id == TicketState.id)
            .filter(Ticket.owner_id.is_not(None), Ticket.owner_id != 1)
        )
        if dt_from:
            q = q.filter(Ticket.created_at >= dt_from)
        if dt_to:
            q = q.filter(Ticket.created_at < dt_to)
        if group_id:
            q = q.filter(Ticket.group_id == group_id)
        if engineer_id:
            q = q.filter(Ticket.owner_id == engineer_id)
        if organization_id:
            q = q.filter(Ticket.organization_id == organization_id)

        users = {
            u.id: self._user_name(u.firstname, u.lastname, u.login)
            for u in self.db.query(User).all()
        }
        groups = {g.id: g.name for g in self.db.query(Group.id, Group.name).all()}
        regions = {r.group_id: r.name for r in self.db.query(ReportRegion.group_id, ReportRegion.name).all()}

        stats = {}
        for ticket, state_name in q.all():
            display_region = regions.get(ticket.group_id) or groups.get(ticket.group_id) or "Без группы"
            if region and display_region != region:
                continue
            key = (ticket.owner_id, ticket.group_id)
            row = stats.setdefault(key, {
                "engineer": users.get(ticket.owner_id, str(ticket.owner_id)),
                "region": display_region,
                "group": groups.get(ticket.group_id, "Без группы"),
                "assigned": 0, "closed": 0, "open": 0, "new": 0,
                "response_seconds": [], "resolution_seconds": [],
                "response_sla_ok": 0, "response_sla_total": 0,
                "resolution_sla_ok": 0, "resolution_sla_total": 0,
                "response_violations": 0, "resolution_violations": 0,
                "overdue": 0,
            })
            row["assigned"] += 1
            state = (state_name or "").lower()
            if state in open_states:
                row["open"] += 1
            if state in new_states:
                row["new"] += 1

            if ticket.first_response_at and ticket.created_at:
                seconds = (ticket.first_response_at - ticket.created_at).total_seconds()
                if seconds >= 0:
                    row["response_seconds"].append(seconds)
                    row["response_sla_total"] += 1
                    if seconds <= response_limit:
                        row["response_sla_ok"] += 1
                    else:
                        row["response_violations"] += 1
            elif state not in closed_states and ticket.created_at:
                reference = dt_to or datetime.utcnow()
                if (reference - ticket.created_at).total_seconds() > response_limit:
                    row["response_violations"] += 1

            if ticket.close_at and ticket.created_at:
                seconds = (ticket.close_at - ticket.created_at).total_seconds()
                if seconds >= 0:
                    row["resolution_seconds"].append(seconds)
                    row["resolution_sla_total"] += 1
                    if seconds <= resolution_limit:
                        row["resolution_sla_ok"] += 1
                    else:
                        row["resolution_violations"] += 1
            elif state not in closed_states and ticket.created_at:
                reference = dt_to or datetime.utcnow()
                if (reference - ticket.created_at).total_seconds() > resolution_limit:
                    row["resolution_violations"] += 1
                    row["overdue"] += 1

        # Closed count is based on close_at within the requested period.
        cq = (
            self.db.query(Ticket)
            .outerjoin(TicketState, Ticket.state_id == TicketState.id)
            .filter(Ticket.owner_id.is_not(None), Ticket.owner_id != 1)
            .filter(Ticket.close_at.is_not(None))
            .filter(func.lower(TicketState.name).in_(closed_states))
        )
        if dt_from:
            cq = cq.filter(Ticket.close_at >= dt_from)
        if dt_to:
            cq = cq.filter(Ticket.close_at < dt_to)
        if group_id:
            cq = cq.filter(Ticket.group_id == group_id)
        if engineer_id:
            cq = cq.filter(Ticket.owner_id == engineer_id)
        if organization_id:
            cq = cq.filter(Ticket.organization_id == organization_id)
        for ticket in cq.all():
            display_region = regions.get(ticket.group_id) or groups.get(ticket.group_id) or "Без группы"
            if region and display_region != region:
                continue
            key = (ticket.owner_id, ticket.group_id)
            row = stats.setdefault(key, {
                "engineer": users.get(ticket.owner_id, str(ticket.owner_id)),
                "region": display_region, "group": groups.get(ticket.group_id, "Без группы"),
                "assigned": 0, "closed": 0, "open": 0, "new": 0,
                "response_seconds": [], "resolution_seconds": [],
                "response_sla_ok": 0, "response_sla_total": 0,
                "resolution_sla_ok": 0, "resolution_sla_total": 0,
                "response_violations": 0, "resolution_violations": 0, "overdue": 0,
            })
            row["closed"] += 1

        # "Overdue" is a current backlog metric and does not depend on the
        # selected report period. Count all currently non-closed tickets whose
        # age has exceeded the configured Resolution SLA.
        for row in stats.values():
            row["overdue"] = 0

        overdue_reference = datetime.utcnow()
        overdueq = (
            self.db.query(Ticket, TicketState.name.label("state_name"))
            .outerjoin(TicketState, Ticket.state_id == TicketState.id)
            .filter(Ticket.owner_id.is_not(None), Ticket.owner_id != 1)
            .filter(Ticket.created_at.is_not(None))
            .filter(or_(TicketState.name.is_(None), ~func.lower(TicketState.name).in_(closed_states)))
        )
        if group_id:
            overdueq = overdueq.filter(Ticket.group_id == group_id)
        if engineer_id:
            overdueq = overdueq.filter(Ticket.owner_id == engineer_id)
        if organization_id:
            overdueq = overdueq.filter(Ticket.organization_id == organization_id)

        for ticket, _state_name in overdueq.all():
            if (overdue_reference - ticket.created_at).total_seconds() <= resolution_limit:
                continue
            display_region = regions.get(ticket.group_id) or groups.get(ticket.group_id) or "Без группы"
            if region and display_region != region:
                continue
            key = (ticket.owner_id, ticket.group_id)
            row = stats.setdefault(key, {
                "engineer": users.get(ticket.owner_id, str(ticket.owner_id)),
                "region": display_region, "group": groups.get(ticket.group_id, "Без группы"),
                "assigned": 0, "closed": 0, "open": 0, "new": 0,
                "response_seconds": [], "resolution_seconds": [],
                "response_sla_ok": 0, "response_sla_total": 0,
                "resolution_sla_ok": 0, "resolution_sla_total": 0,
                "response_violations": 0, "resolution_violations": 0, "overdue": 0,
            })
            row["overdue"] += 1

        result = []
        for key, row in stats.items():
            avg_response = sum(row["response_seconds"]) / len(row["response_seconds"]) if row["response_seconds"] else None
            avg_resolution = sum(row["resolution_seconds"]) / len(row["resolution_seconds"]) if row["resolution_seconds"] else None
            result.append({
                "engineer_id": key[0],
                "engineer": row["engineer"], "region": row["region"], "group": row["group"],
                "assigned": row["assigned"], "closed": row["closed"],
                "open": row["open"], "new": row["new"],
                "avg_first_response": self.format_duration(avg_response),
                "first_response_sla_pct": round(row["response_sla_ok"] * 100 / row["response_sla_total"], 1) if row["response_sla_total"] else None,
                "avg_resolution": self.format_duration(avg_resolution),
                "resolution_sla_pct": round(row["resolution_sla_ok"] * 100 / row["resolution_sla_total"], 1) if row["resolution_sla_total"] else None,
                "response_violations": row["response_violations"],
                "resolution_violations": row["resolution_violations"],
                "overdue": row["overdue"],
            })
        result.sort(key=lambda x: (x["region"], x["group"], x["engineer"]))
        return result

    def engineer_report_filter_options(self):
        options = self.transfer_filter_options()
        options["groups"] = [
            {"id": g.id, "name": g.name}
            for g in self.db.query(Group).filter(Group.active.is_(True)).order_by(Group.name).all()
        ]

        # Only users that actually appear as ticket owners/agents.
        agent_ids = (
            self.db.query(Ticket.owner_id)
            .filter(Ticket.owner_id.is_not(None), Ticket.owner_id != 1)
            .distinct()
            .subquery()
        )
        agents = (
            self.db.query(User)
            .filter(User.active.is_(True))
            .filter(User.id.in_(self.db.query(agent_ids.c.owner_id)))
            .order_by(User.firstname, User.lastname, User.login)
            .all()
        )
        options["engineers"] = [
            {"id": u.id, "name": self._user_name(u.firstname, u.lastname, u.login)}
            for u in agents
        ]
        return options

    def overdue_tickets(
        self, region=None, group_id=None, engineer_id=None, organization_id=None,
    ):
        """Current overdue backlog using configured Resolution SLA."""
        resolution_limit = get_metric_int(self.db, "sla_resolution_hours") * 3600
        closed_states = ["closed", "merged"]
        now = datetime.utcnow()

        query = (
            self.db.query(Ticket, TicketState.name.label("state_name"))
            .outerjoin(TicketState, Ticket.state_id == TicketState.id)
            .filter(Ticket.owner_id.is_not(None), Ticket.owner_id != 1)
            .filter(Ticket.created_at.is_not(None))
            .filter(or_(TicketState.name.is_(None), ~func.lower(TicketState.name).in_(closed_states)))
        )
        if group_id:
            query = query.filter(Ticket.group_id == group_id)
        if engineer_id:
            query = query.filter(Ticket.owner_id == engineer_id)
        if organization_id:
            query = query.filter(Ticket.organization_id == organization_id)

        users = {
            u.id: self._user_name(u.firstname, u.lastname, u.login)
            for u in self.db.query(User).all()
        }
        groups = {g.id: g.name for g in self.db.query(Group.id, Group.name).all()}
        regions = {r.group_id: r.name for r in self.db.query(ReportRegion.group_id, ReportRegion.name).all()}
        organizations = {o.id: o.name for o in self.db.query(Organization.id, Organization.name).all()}

        result = []
        for ticket, state_name in query.all():
            age_seconds = (now - ticket.created_at).total_seconds()
            overdue_seconds = age_seconds - resolution_limit
            if overdue_seconds <= 0:
                continue
            display_region = regions.get(ticket.group_id) or groups.get(ticket.group_id) or "Без группы"
            if region and display_region != region:
                continue
            result.append({
                "ticket_number": ticket.number or str(ticket.id),
                "title": ticket.title or "",
                "engineer": users.get(ticket.owner_id, str(ticket.owner_id)),
                "region": display_region,
                "group": groups.get(ticket.group_id, "Без группы"),
                "organization": organizations.get(ticket.organization_id, ""),
                "state": state_name or "",
                "created_at": ticket.created_at,
                "overdue": self.format_duration(overdue_seconds),
                "overdue_seconds": overdue_seconds,
            })
        result.sort(key=lambda x: x["overdue_seconds"], reverse=True)
        return result

