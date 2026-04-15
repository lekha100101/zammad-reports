from datetime import datetime, timedelta
from sqlalchemy import and_, case, cast, Date, func, or_
from sqlalchemy.orm import Session

from app.config import settings
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

    def sla_report(self, date_from=None, date_to=None):
        dt_from = self._parse_date_start(date_from)
        dt_to = self._parse_date_end(date_to)

        response_sla_seconds = settings.sla_response_minutes * 60
        resolution_sla_seconds = settings.sla_resolution_hours * 60 * 60

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
