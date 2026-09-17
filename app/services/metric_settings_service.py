from datetime import datetime

from sqlalchemy.orm import Session

from app.config import settings
from app.models import ReportMetricSetting


METRIC_DEFAULTS = {
    "sla_response_minutes": str(settings.sla_response_minutes),
    "sla_resolution_hours": str(settings.sla_resolution_hours),
    "workload_open_warning": "20",
    "workload_open_critical": "35",
    "backlog_delta_warning": "10",
}


def get_metric_settings(db: Session) -> dict[str, str]:
    rows = db.query(ReportMetricSetting).all()
    values = {row.key: row.value for row in rows}
    result = dict(METRIC_DEFAULTS)
    result.update(values)
    return result


def get_metric_int(db: Session, key: str) -> int:
    values = get_metric_settings(db)
    try:
        return int(values.get(key, METRIC_DEFAULTS[key]))
    except Exception:
        return int(METRIC_DEFAULTS[key])


def update_metric_settings(db: Session, payload: dict[str, str]) -> None:
    for key, default in METRIC_DEFAULTS.items():
        raw = (payload.get(key) or "").strip()
        if not raw:
            raw = default
        try:
            normalized = str(max(1, int(raw)))
        except Exception:
            normalized = default

        row = db.query(ReportMetricSetting).filter(ReportMetricSetting.key == key).first()
        if row is None:
            row = ReportMetricSetting(key=key, value=normalized, updated_at=datetime.utcnow())
            db.add(row)
        else:
            row.value = normalized
            row.updated_at = datetime.utcnow()

    db.commit()
