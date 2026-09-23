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

    excluded_group_ids = _report_excluded_group_ids.get()
    if not excluded_group_ids:
        return

    execute_state.statement = execute_state.statement.options(
        with_loader_criteria(
            Ticket,
            lambda ticket: ~ticket.group_id.in_(excluded_group_ids),
            include_aliases=True,
        )
    )
