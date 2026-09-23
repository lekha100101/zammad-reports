from contextvars import ContextVar

from sqlalchemy import event
from sqlalchemy.orm import Session, with_loader_criteria

from app.models import Ticket

# None means this is not a report request. An empty tuple means it is a report
# request but the administrator has not excluded any groups.
_report_excluded_group_ids: ContextVar[tuple[int, ...] | None] = ContextVar(
    "report_excluded_group_ids", default=None
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

    excluded_group_ids = _report_excluded_group_ids.get()
    if excluded_group_ids is None:
        return

    if excluded_group_ids:
        execute_state.statement = execute_state.statement.options(
            with_loader_criteria(
                Ticket,
                lambda ticket: (ticket.is_deleted.is_(False)) & (~ticket.group_id.in_(excluded_group_ids)),
                include_aliases=True,
            )
        )
    else:
        execute_state.statement = execute_state.statement.options(
            with_loader_criteria(
                Ticket,
                lambda ticket: ticket.is_deleted.is_(False),
                include_aliases=True,
            )
        )
