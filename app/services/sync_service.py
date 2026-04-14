import requests
from datetime import datetime
from sqlalchemy.orm import Session
from app.models import TicketState

from app.models import Ticket, User, Group, Organization, TimeAccounting, SyncLog

def parse_dt(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value

    value = str(value).strip()
    if not value:
        return None

    formats = [
        None,  # fromisoformat
        "%Y-%m-%d %H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
    ]

    for fmt in formats:
        try:
            if fmt is None:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            return datetime.strptime(value, fmt)
        except Exception:
            continue

    return None

class SyncService:

    def __init__(self, db: Session, base_url: str, token: str):
        self.db = db
        self.base_url = base_url.rstrip("/")
        self.headers = {
            "Authorization": f"Token token={token}",
            "Content-Type": "application/json"
        }

    def _log_start(self, sync_type):
        log = SyncLog(
            sync_type=sync_type,
            status="running",
            started_at=datetime.utcnow()
        )
        self.db.add(log)
        self.db.commit()
        return log

    def _log_finish(self, log, count):
        log.status = "finished"
        log.finished_at = datetime.utcnow()
        log.items_count = count
        self.db.commit()

    def sync_users(self):
        log = self._log_start("users")
        page = 1
        count = 0

        while True:
            r = requests.get(
                f"{self.base_url}/api/v1/users?page={page}",
                headers=self.headers
            )

            data = r.json()

            if not data:
                break

            for u in data:
                obj = self.db.get(User, u["id"])
                if not obj:
                    obj = User(id=u["id"])
                    self.db.add(obj)

                obj.login = u.get("login")
                obj.firstname = u.get("firstname")
                obj.lastname = u.get("lastname")
                obj.email = u.get("email")

                count += 1

            self.db.commit()
            page += 1

        self._log_finish(log, count)
        return count

    def sync_groups(self):
        log = self._log_start("groups")
        r = requests.get(
            f"{self.base_url}/api/v1/groups",
            headers=self.headers
        )

        data = r.json()
        count = 0

        for g in data:
            obj = self.db.get(Group, g["id"])
            if not obj:
                obj = Group(id=g["id"])
                self.db.add(obj)

            obj.name = g.get("name")
            count += 1

        self.db.commit()
        self._log_finish(log, count)
        return count

    def sync_organizations(self):
        log = self._log_start("organizations")
        r = requests.get(
            f"{self.base_url}/api/v1/organizations",
            headers=self.headers
        )

        data = r.json()
        count = 0

        for o in data:
            obj = self.db.get(Organization, o["id"])
            if not obj:
                obj = Organization(id=o["id"])
                self.db.add(obj)

            obj.name = o.get("name")
            count += 1

        self.db.commit()
        self._log_finish(log, count)
        return count

    def sync_ticket_states(self):
        log = self._log_start("ticket_states")

        r = requests.get(
            f"{self.base_url}/api/v1/ticket_states",
            headers=self.headers
        )

        data = r.json()
        count = 0

        for s in data:
            obj = self.db.get(TicketState, s["id"])
            if not obj:
                obj = TicketState(id=s["id"])
                self.db.add(obj)

            obj.name = s.get("name")
            count += 1

        self.db.commit()
        self._log_finish(log, count)
        return count

    from datetime import datetime

    def parse_dt(value):
        if not value:
            return None
        return datetime.fromisoformat(value.replace("Z", "+00:00"))


    def sync_tickets(self):
        log = self._log_start("tickets")
        page = 1
        per_page = 100
        count = 0

        while True:
            r = requests.get(
                f"{self.base_url}/api/v1/tickets",
                headers=self.headers,
                params={"page": page, "per_page": per_page},
                timeout=60
            )

            if r.status_code != 200:
                raise Exception(f"Tickets request failed: {r.status_code} {r.text}")

            data = r.json()

            if not isinstance(data, list):
                raise Exception(f"Unexpected tickets response on page {page}: {data}")

            print(f"page={page}, got={len(data)}")

            if not data:
                break

            for t in data:
                obj = self.db.get(Ticket, t["id"])
                if not obj:
                    obj = Ticket(id=t["id"])
                    self.db.add(obj)

                obj.number = t.get("number")
                obj.title = t.get("title")
                obj.group_id = t.get("group_id")
                obj.owner_id = t.get("owner_id")
                obj.customer_id = t.get("customer_id")
                obj.organization_id = t.get("organization_id")
                obj.state_id = t.get("state_id")
                obj.priority_id = t.get("priority_id")

                obj.first_response_at = parse_dt(t.get("first_response_at"))
                obj.close_at = parse_dt(t.get("close_at"))
                obj.escalation_at = parse_dt(t.get("escalation_at"))
                obj.pending_time = parse_dt(t.get("pending_time"))
                obj.created_at = parse_dt(t.get("created_at"))
                obj.updated_at = parse_dt(t.get("updated_at"))

                count += 1

            self.db.commit()

            if len(data) < per_page:
                break

            page += 1

        self._log_finish(log, count)
        return count

    def sync_time_accounting(self):
        log = self._log_start("time")
        page = 1
        per_page = 100
        count = 0

        while True:
            r = requests.get(
                f"{self.base_url}/api/v1/time_accountings?page={page}&per_page={per_page}",
                headers=self.headers
            )
            data = r.json()

            if isinstance(data, dict):
                data = data.get("assets") or data.get("data") or data.get("time_accountings") or []

            if not isinstance(data, list) or not data:
                break

            for t in data:
                obj = self.db.get(TimeAccounting, t["id"])
                if not obj:
                    obj = TimeAccounting(id=t["id"])
                    self.db.add(obj)

                obj.ticket_id = t.get("ticket_id")
                obj.time_unit = t.get("time_unit")
                obj.created_by_id = t.get("created_by_id")
                obj.created_at = parse_dt(t.get("created_at"))
                obj.updated_at = parse_dt(t.get("updated_at"))

                count += 1

            self.db.commit()

            if len(data) < per_page:
                break

            page += 1

        self._log_finish(log, count)
        return count

    def sync_all(self):
        return {
            "users": self.sync_users(),
            "groups": self.sync_groups(),
            "organizations": self.sync_organizations(),
            "states": self.sync_ticket_states(),
            "tickets": self.sync_tickets(),
            "time_accountings": self.sync_time_accounting(),
        }
