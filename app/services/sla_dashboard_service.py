from collections import defaultdict
from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Group, ReportRegion, Ticket, User


class SlaDashboardService:
    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _date_start(value):
        return datetime.strptime(value, "%Y-%m-%d") if value else None

    @staticmethod
    def _date_end(value):
        return datetime.strptime(value, "%Y-%m-%d") + timedelta(days=1) if value else None

    @staticmethod
    def _pct(ok, total):
        return round(ok * 100 / total, 1) if total else None

    @staticmethod
    def _bucket(dt, mode):
        if mode == "month":
            return dt.strftime("%Y-%m")
        if mode == "week":
            monday = dt.date() - timedelta(days=dt.weekday())
            return monday.strftime("%Y-%m-%d")
        return dt.strftime("%Y-%m-%d")

    def report(self, date_from=None, date_to=None, region=None, group_id=None, engineer_id=None, organization_id=None):
        dt_from = self._date_start(date_from)
        dt_to = self._date_end(date_to)
        span_days = ((dt_to - dt_from).days if dt_from and dt_to else 31)
        bucket_mode = "month" if span_days > 120 else ("week" if span_days > 45 else "day")

        groups = {g.id: g.name for g in self.db.query(Group.id, Group.name).all()}
        regions = {r.group_id: r.name for r in self.db.query(ReportRegion.group_id, ReportRegion.name).all()}
        users = {
            u.id: " ".join(x for x in [u.firstname, u.lastname] if x).strip() or u.login or str(u.id)
            for u in self.db.query(User).all()
        }

        q = self.db.query(Ticket).filter(Ticket.owner_id.is_not(None), Ticket.owner_id != 1)
        if group_id:
            q = q.filter(Ticket.group_id == group_id)
        if engineer_id:
            q = q.filter(Ticket.owner_id == engineer_id)
        if organization_id:
            q = q.filter(Ticket.organization_id == organization_id)

        # A ticket can contribute to First Response and Resolution independently.
        # Period filtering is applied to the actual SLA completion event:
        # first_response_at for response, close_at for resolution.
        tickets = q.all()
        trend = defaultdict(lambda: {"response_ok": 0, "response_total": 0, "resolution_ok": 0, "resolution_total": 0})
        engineers = defaultdict(lambda: {"response_ok": 0, "response_total": 0, "resolution_ok": 0, "resolution_total": 0})
        totals = {"response_ok": 0, "response_total": 0, "resolution_ok": 0, "resolution_total": 0}

        for t in tickets:
            display_region = regions.get(t.group_id) or groups.get(t.group_id) or "Без группы"
            if region and display_region != region:
                continue

            engineer_key = (t.owner_id, users.get(t.owner_id, str(t.owner_id)))

            response_in_period = (
                t.first_response_at is not None
                and (dt_from is None or t.first_response_at >= dt_from)
                and (dt_to is None or t.first_response_at < dt_to)
            )
            if response_in_period and t.first_response_diff_in_min is not None:
                ok = t.first_response_diff_in_min >= 0
                bucket = self._bucket(t.first_response_at, bucket_mode)
                trend[bucket]["response_total"] += 1
                engineers[engineer_key]["response_total"] += 1
                totals["response_total"] += 1
                if ok:
                    trend[bucket]["response_ok"] += 1
                    engineers[engineer_key]["response_ok"] += 1
                    totals["response_ok"] += 1

            resolution_in_period = (
                t.close_at is not None
                and (dt_from is None or t.close_at >= dt_from)
                and (dt_to is None or t.close_at < dt_to)
            )
            if resolution_in_period and t.close_diff_in_min is not None:
                ok = t.close_diff_in_min >= 0
                bucket = self._bucket(t.close_at, bucket_mode)
                trend[bucket]["resolution_total"] += 1
                engineers[engineer_key]["resolution_total"] += 1
                totals["resolution_total"] += 1
                if ok:
                    trend[bucket]["resolution_ok"] += 1
                    engineers[engineer_key]["resolution_ok"] += 1
                    totals["resolution_ok"] += 1

        trend_rows = []
        for bucket in sorted(trend):
            x = trend[bucket]
            trend_rows.append({
                "period": bucket,
                "first_response_pct": self._pct(x["response_ok"], x["response_total"]),
                "resolution_pct": self._pct(x["resolution_ok"], x["resolution_total"]),
                "response_total": x["response_total"],
                "resolution_total": x["resolution_total"],
            })

        engineer_rows = []
        for (eid, name), x in engineers.items():
            engineer_rows.append({
                "engineer_id": eid,
                "engineer": name,
                "response_total": x["response_total"],
                "first_response_pct": self._pct(x["response_ok"], x["response_total"]),
                "response_violations": x["response_total"] - x["response_ok"],
                "resolution_total": x["resolution_total"],
                "resolution_pct": self._pct(x["resolution_ok"], x["resolution_total"]),
                "resolution_violations": x["resolution_total"] - x["resolution_ok"],
            })
        engineer_rows.sort(key=lambda x: x["engineer"])

        return {
            "summary": {
                "response_total": totals["response_total"],
                "response_ok": totals["response_ok"],
                "response_violations": totals["response_total"] - totals["response_ok"],
                "first_response_pct": self._pct(totals["response_ok"], totals["response_total"]),
                "resolution_total": totals["resolution_total"],
                "resolution_ok": totals["resolution_ok"],
                "resolution_violations": totals["resolution_total"] - totals["resolution_ok"],
                "resolution_pct": self._pct(totals["resolution_ok"], totals["resolution_total"]),
            },
            "trend": trend_rows,
            "engineers": engineer_rows,
            "bucket_mode": bucket_mode,
        }
