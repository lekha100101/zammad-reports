from contextvars import ContextVar

from sqlalchemy import event
from sqlalchemy.orm import Session, with_loader_criteria

from app.models import Ticket

_report_excluded_group_ids: ContextVar[tuple[int, ...]] = ContextVar(
    "report_excluded_group_ids", default=()
)


def parse_excluded_group_ids(raw: str) -> tuple[int, ...]:
    return tuple(
        sorted(
            {
                int(value.strip())
                for value in (raw or "").split(",")
                if value.strip().isdigit()
            }
        )
    )


def set_report_excluded_group_ids(group_ids: tuple[int, ...]):
    return _report_excluded_group_ids.set(group_ids)


def reset_report_excluded_group_ids(token) -> None:
    _report_excluded_group_ids.reset(token)


@event.listens_for(Session, "do_orm_execute")
def _apply_report_group_exclusions(execute_state):
    if not execute_state.is_select:
        return

    # This listener is active only inside report requests because the middleware
    # sets the context variable there. Deleted tickets and administratively
    # excluded groups remain available to sync/admin code outside that context.
    excluded_group_ids = _report_excluded_group_ids.get()
    if not excluded_group_ids:
        # An empty tuple is also a valid report context, so deleted tickets are
        # filtered by the middleware setting a sentinel-free report context below.
        return

    execute_state.statement = execute_state.statement.options(
        with_loader_criteria(
            Ticket,
            lambda ticket: (ticket.is_deleted.is_(False)) & (~ticket.group_id.in_(excluded_group_ids)),
            include_aliases=True,
        )
    )
