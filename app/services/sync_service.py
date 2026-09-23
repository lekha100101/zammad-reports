import requests
from datetime import datetime

from sqlalchemy.orm import Session

from app.models import (
    Group,
    Organization,
    SyncLog,
    Ticket,
    TicketHistory,
    TicketState,
    TimeAccounting,
    User,
)


def parse_dt(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.replace(tzinfo=None) if dt.tzinfo else dt
    except (TypeError, ValueError):
        return None


class SyncService:
    def __init__(self, db: Session, base_url: str, token: str):
        self.db = db
        self.base_url = base_url.rstrip("/")
        self.headers = {
            "Authorization": f"Token token={token}",
            "Content-Type": "application/json",
        }

    def _log_start(self, sync_type):
        log = SyncLog(sync_type=sync_type, status="running", started_at=datetime.utcnow())
        self.db.add(log)
        self.db.commit()
        return log

    def _log_finish(self, log, count, message=None):
        log.status = "finished"
        log.finished_at = datetime.utcnow()
        log.items_count = count
        log.message = message
        self.db.commit()

    def _log_fail(self, log, exc):
        self.db.rollback()
        log = self.db.get(SyncLog, log.id)
        if log:
            log.status = "failed"
            log.finished_at = datetime.utcnow()
            log.message = str(exc)[:4000]
            self.db.commit()

    def _get_json(self, path, **kwargs):
        response = requests.get(
            f"{self.base_url}{path}",
            headers=self.headers,
            timeout=60,
            **kwargs,
        )
        if response.status_code != 200:
            raise RuntimeError(
                f"Zammad request failed: GET {path}: "
                f"{response.status_code} {response.text[:1000]}"
            )
        return response.json()

    def sync_users(self):
        log = self._log_start("users")
        try:
            page, count = 1, 0
            while True:
                data = self._get_json("/api/v1/users", params={"page": page, "per_page": 100})
                if not data:
                    break
                for u in data:
                    obj = self.db.get(User, u["id"]) or User(id=u["id"])
                    self.db.add(obj)
                    obj.login = u.get("login")
                    obj.firstname = u.get("firstname")
                    obj.lastname = u.get("lastname")
                    obj.email = u.get("email")
                    obj.organization_id = u.get("organization_id")
                    obj.active = u.get("active", True)
                    obj.created_at = parse_dt(u.get("created_at"))
                    obj.updated_at = parse_dt(u.get("updated_at"))
                    count += 1
                self.db.commit()
                if len(data) < 100:
                    break
                page += 1
            self._log_finish(log, count)
            return count
        except Exception as exc:
            self._log_fail(log, exc)
            raise

    def sync_groups(self):
        return self._sync_simple("/api/v1/groups", Group, "groups")

    def sync_organizations(self):
        return self._sync_simple("/api/v1/organizations", Organization, "organizations")

    def sync_ticket_states(self):
        return self._sync_simple("/api/v1/ticket_states", TicketState, "ticket_states")

    def _sync_simple(self, path, model, sync_type):
        log = self._log_start(sync_type)
        try:
            data = self._get_json(path)
            if not isinstance(data, list):
                raise RuntimeError(f"Unexpected {sync_type} response: {data}")
            count = 0
            for item in data:
                obj = self.db.get(model, item["id"]) or model(id=item["id"])
                self.db.add(obj)
                if hasattr(obj, "name"):
                    obj.name = item.get("name")
                count += 1
            self.db.commit()
            self._log_finish(log, count)
            return count
        except Exception as exc:
            self._log_fail(log, exc)
            raise

    def sync_tickets(self):
        log = self._log_start("tickets")
        changed_ticket_ids = []
        seen_ticket_ids = set()
        try:
            page, per_page, count = 1, 100, 0
            while True:
                data = self._get_json(
                    "/api/v1/tickets",
                    params={"page": page, "per_page": per_page},
                )
                if not isinstance(data, list):
                    raise RuntimeError(f"Unexpected tickets response on page {page}: {data}")
                print(f"tickets page={page}, got={len(data)}")
                if not data:
                    break

                for t in data:
                    seen_ticket_ids.add(int(t["id"]))
                    sla_fields = (
                        "first_response_escalation_at",
                        "first_response_in_min",
                        "first_response_diff_in_min",
                        "close_escalation_at",
                        "close_in_min",
                        "close_diff_in_min",
                        "update_escalation_at",
                        "update_in_min",
                        "update_diff_in_min",
                    )
                    ticket_data = t
                    if not any(field in t for field in sla_fields):
                        try:
                            ticket_data = self._get_json(f"/api/v1/tickets/{t['id']}")
                        except RuntimeError as exc:
                            print(f"ticket SLA detail fetch failed id={t['id']}: {exc}")
                            ticket_data = t

                    obj = self.db.get(Ticket, ticket_data["id"]) or Ticket(id=ticket_data["id"])
                    remote_updated_at = parse_dt(ticket_data.get("updated_at"))
                    if obj.updated_at != remote_updated_at:
                        changed_ticket_ids.append(ticket_data["id"])
                    self.db.add(obj)
                    t = ticket_data
                    obj.number = t.get("number")
                    obj.title = t.get("title")
                    obj.group_id = t.get("group_id")
                    obj.owner_id = t.get("owner_id")
                    obj.customer_id = t.get("customer_id")
                    obj.organization_id = t.get("organization_id")
                    obj.state_id = t.get("state_id")
                    obj.priority_id = t.get("priority_id")
                    obj.first_response_at = parse_dt(t.get("first_response_at"))
                    obj.first_response_escalation_at = parse_dt(t.get("first_response_escalation_at"))
                    obj.first_response_in_min = t.get("first_response_in_min")
                    obj.first_response_diff_in_min = t.get("first_response_diff_in_min")
                    obj.close_at = parse_dt(t.get("close_at"))
                    obj.close_escalation_at = parse_dt(t.get("close_escalation_at"))
                    obj.close_in_min = t.get("close_in_min")
                    obj.close_diff_in_min = t.get("close_diff_in_min")
                    obj.update_escalation_at = parse_dt(t.get("update_escalation_at"))
                    obj.update_in_min = t.get("update_in_min")
                    obj.update_diff_in_min = t.get("update_diff_in_min")
                    obj.escalation_at = parse_dt(t.get("escalation_at"))
                    obj.pending_time = parse_dt(t.get("pending_time"))
                    obj.created_at = parse_dt(t.get("created_at"))
                    obj.updated_at = remote_updated_at
                    obj.is_deleted = False
                    count += 1
                self.db.commit()
                if len(data) < per_page:
                    break
                page += 1

            # Reconcile deletions only after the complete pagination loop succeeds.
            # If any page request raises, execution jumps to except before this block,
            # so a partial Zammad response can never mass-mark tickets as deleted.
            deleted_count = 0
            if seen_ticket_ids:
                deleted_count = (
                    self.db.query(Ticket)
                    .filter(Ticket.is_deleted.is_(False))
                    .filter(~Ticket.id.in_(seen_ticket_ids))
                    .update({Ticket.is_deleted: True}, synchronize_session=False)
                )
                self.db.commit()

            message = (
                f"changed_tickets={len(set(changed_ticket_ids))}, "
                f"deleted_in_zammad={deleted_count}"
            )
            self._log_finish(log, count, message=message)
            return {
                "count": count,
                "changed_ticket_ids": list(dict.fromkeys(changed_ticket_ids)),
                "deleted_in_zammad": deleted_count,
            }
        except Exception as exc:
            self._log_fail(log, exc)
            raise

    def sync_ticket_history(self, ticket_id=None):
        log = self._log_start("ticket_history")
        try:
            if ticket_id is not None:
                ticket_ids = [int(ticket_id)]
            else:
                ticket_ids = [row[0] for row in self.db.query(Ticket.id).order_by(Ticket.id).all()]

            count = 0
            tickets_done = 0
            skipped = 0
            failed = 0
            for current_ticket_id in ticket_ids:
                try:
                    data = self._get_json(f"/api/v1/ticket_history/{current_ticket_id}")
                except RuntimeError as exc:
                    if " 404 " in str(exc):
                        skipped += 1
                        tickets_done += 1
                        print(f"ticket_history skip missing ticket={current_ticket_id}")
                        continue
                    failed += 1
                    tickets_done += 1
                    print(f"ticket_history failed ticket={current_ticket_id}: {exc}")
                    continue

                history = data.get("history", []) if isinstance(data, dict) else data
                if not isinstance(history, list):
                    failed += 1
                    tickets_done += 1
                    print(f"ticket_history unexpected response ticket={current_ticket_id}: {data}")
                    continue

                for event in history:
                    if event.get("object") != "Ticket":
                        continue
                    zammad_id = event.get("id")
                    if zammad_id is None:
                        continue
                    obj = (
                        self.db.query(TicketHistory)
                        .filter(TicketHistory.zammad_history_id == zammad_id)
                        .one_or_none()
                    )
                    if obj is None:
                        obj = TicketHistory(zammad_history_id=zammad_id)
                        self.db.add(obj)
                    obj.ticket_id = current_ticket_id
                    obj.object = event.get("object")
                    obj.event_type = event.get("type")
                    obj.attribute = event.get("attribute")
                    obj.id_from = event.get("id_from")
                    obj.id_to = event.get("id_to")
                    obj.value_from = event.get("value_from")
                    obj.value_to = event.get("value_to")
                    obj.created_by_id = event.get("created_by_id")
                    obj.created_at = parse_dt(event.get("created_at"))
                    count += 1

                self.db.commit()
                tickets_done += 1
                if tickets_done % 100 == 0:
                    print(f"ticket_history tickets={tickets_done}/{len(ticket_ids)}, events={count}")

            self._log_finish(
                log,
                count,
                message=f"tickets={tickets_done}, events={count}, skipped={skipped}, failed={failed}",
            )
            return {"tickets": tickets_done, "events": count, "skipped": skipped, "failed": failed}
        except Exception as exc:
            self._log_fail(log, exc)
            raise

    def sync_time_accounting(self):
        log = self._log_start("time")
        try:
            data = self._get_json("/api/v1/time_accountings")
            count = 0
            for t in data:
                obj = self.db.get(TimeAccounting, t["id"]) or TimeAccounting(id=t["id"])
                self.db.add(obj)
                obj.ticket_id = t.get("ticket_id")
                obj.time_unit = t.get("time_unit")
                obj.created_by_id = t.get("created_by_id")
                obj.created_at = parse_dt(t.get("created_at"))
                count += 1
            self.db.commit()
            self._log_finish(log, count)
            return count
        except Exception as exc:
            self._log_fail(log, exc)
            raise

    def sync_all(self):
        users = self.sync_users()
        groups = self.sync_groups()
        organizations = self.sync_organizations()
        states = self.sync_ticket_states()
        tickets_result = self.sync_tickets()
        changed_ticket_ids = tickets_result["changed_ticket_ids"]

        history = {"tickets": 0, "events": 0, "skipped": 0, "failed": 0}
        for ticket_id in changed_ticket_ids:
            result = self.sync_ticket_history(ticket_id=ticket_id)
            for key in history:
                history[key] += result.get(key, 0)

        return {
            "users": users,
            "groups": groups,
            "organizations": organizations,
            "states": states,
            "tickets": tickets_result["count"],
            "deleted_in_zammad": tickets_result.get("deleted_in_zammad", 0),
            "history": history,
            "history_changed_tickets": len(changed_ticket_ids),
        }
