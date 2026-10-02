from collections import defaultdict
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models import CategoryLabel, Group, ReportRegion, Ticket


EMPTY_SUBCATEGORY = "__not_filled__"


class CategoryReportService:
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

    def report(self, date_from=None, date_to=None, region=None, group_id=None, engineer_id=None, organization_id=None, category=None):
        labels = {
            (row.field_name, row.technical_value): row.display_name
            for row in self.db.query(CategoryLabel).all()
        }
        groups = {g.id: g.name for g in self.db.query(Group).all()}
        regions = {r.group_id: r.name for r in self.db.query(ReportRegion).all()}

        q = self.db.query(Ticket).filter(Ticket.is_deleted.is_(False), Ticket.category.isnot(None), Ticket.category != "")
        if date_from:
            q = q.filter(Ticket.created_at >= self._date_start(date_from))
        if date_to:
            q = q.filter(Ticket.created_at < self._date_end(date_to))
        if group_id:
            q = q.filter(Ticket.group_id == group_id)
        if engineer_id:
            q = q.filter(Ticket.owner_id == engineer_id)
        if organization_id:
            q = q.filter(Ticket.organization_id == organization_id)

        categories = defaultdict(lambda: {"total": 0, "open": 0, "closed": 0, "fr_ok": 0, "fr_total": 0, "res_ok": 0, "res_total": 0})
        subcategories = defaultdict(lambda: {"total": 0, "open": 0, "closed": 0, "fr_ok": 0, "fr_total": 0, "res_ok": 0, "res_total": 0})

        for t in q.all():
            display_region = regions.get(t.group_id) or groups.get(t.group_id) or "Без группы"
            if region and display_region != region:
                continue
            is_closed = t.close_at is not None
            c = categories[t.category]
            c["total"] += 1; c["closed" if is_closed else "open"] += 1
            if t.first_response_diff_in_min is not None:
                c["fr_total"] += 1; c["fr_ok"] += int(t.first_response_diff_in_min >= 0)
            if t.close_diff_in_min is not None:
                c["res_total"] += 1; c["res_ok"] += int(t.close_diff_in_min >= 0)

            # Drill-down is based on both values from the same ticket:
            # 1) ticket.category must equal the selected category;
            # 2) then the ticket is counted by its sub_accesses value.
            # Empty/blank sub_accesses is kept as a separate bucket so the
            # subcategory totals always reconcile with the selected category.
            if category and t.category == category:
                sub_value = (t.sub_accesses or "").strip() or EMPTY_SUBCATEGORY
                s = subcategories[sub_value]
                s["total"] += 1; s["closed" if is_closed else "open"] += 1
                if t.first_response_diff_in_min is not None:
                    s["fr_total"] += 1; s["fr_ok"] += int(t.first_response_diff_in_min >= 0)
                if t.close_diff_in_min is not None:
                    s["res_total"] += 1; s["res_ok"] += int(t.close_diff_in_min >= 0)

        def rows(source, field_name):
            result = []
            for value, x in source.items():
                if field_name == "sub_accesses" and value == EMPTY_SUBCATEGORY:
                    display_name = "Подкатегория не заполнена"
                else:
                    display_name = labels.get((field_name, value), value)
                result.append({
                    "value": value,
                    "name": display_name,
                    "total": x["total"], "open": x["open"], "closed": x["closed"],
                    "first_response_pct": self._pct(x["fr_ok"], x["fr_total"]),
                    "resolution_pct": self._pct(x["res_ok"], x["res_total"]),
                })
            return sorted(result, key=lambda x: (-x["total"], x["name"]))

        return {
            "categories": rows(categories, "category"),
            "subcategories": rows(subcategories, "sub_accesses"),
            "selected_category_name": labels.get(("category", category), category) if category else None,
        }
