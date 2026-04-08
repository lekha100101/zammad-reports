from datetime import datetime
from sqlalchemy.orm import Session
from app.models import Ticket, TimeAccounting
from app.zammad_client import ZammadClient

def parse_dt(value):
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))

def sync_tickets(db: Session) -> int:
    client = ZammadClient()
    page = 1
    per_page = 100
    total = 0

    while True:
        items = client.get_tickets_page(page=page, per_page=per_page)
        if not items:
            break

        for item in items:
            ticket = db.get(Ticket, item["id"])
            if not ticket:
                ticket = Ticket(id=item["id"])
                db.add(ticket)

            ticket.number = item.get("number")
            ticket.title = item.get("title")
            ticket.group_id = item.get("group_id")
            ticket.owner_id = item.get("owner_id")
            ticket.customer_id = item.get("customer_id")
            ticket.organization_id = item.get("organization_id")
            ticket.state_id = item.get("state_id")
            ticket.priority_id = item.get("priority_id")
            ticket.created_at = parse_dt(item.get("created_at"))
            ticket.updated_at = parse_dt(item.get("updated_at"))
            ticket.close_at = parse_dt(item.get("close_at"))
            ticket.escalation_at = parse_dt(item.get("escalation_at"))
            ticket.first_response_at = parse_dt(item.get("first_response_at"))

            total += 1

        db.commit()
        page += 1

    return total

def sync_time_accountings(db: Session) -> int:
    client = ZammadClient()
    tickets = db.query(Ticket).all()
    total = 0

    for ticket in tickets:
        items = client.get_time_accountings(ticket.id)

        for item in items:
            obj = db.get(TimeAccounting, item["id"])
            if not obj:
                obj = TimeAccounting(id=item["id"])
                db.add(obj)

            obj.ticket_id = item.get("ticket_id")
            obj.ticket_article_id = item.get("ticket_article_id")
            obj.time_unit = float(item["time_unit"]) if item.get("time_unit") else 0.0
            obj.type_id = item.get("type_id")
            obj.created_by_id = item.get("created_by_id")
            obj.created_at = parse_dt(item.get("created_at"))
            obj.updated_at = parse_dt(item.get("updated_at"))
            total += 1

        db.commit()

    return total
