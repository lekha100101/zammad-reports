from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

from app.config import settings, to_bool
from app.models import AppSetting


APP_SETTING_DEFAULTS = {
    "app_name": settings.app_name,
    "debug": "1" if settings.debug else "0",
    "zammad_url": settings.zammad_url,
    "zammad_token": settings.zammad_token,
    "zammad_verify_ssl": "1" if settings.zammad_verify_ssl else "0",
    "zammad_per_page": str(settings.zammad_per_page),
    "tz": settings.tz,
    "sync_token": "",
}


def get_app_settings(db: Session) -> dict[str, str]:
    rows = db.query(AppSetting).all()
    values = {row.key: row.value for row in rows}
    result = dict(APP_SETTING_DEFAULTS)
    result.update(values)
    return result


def get_app_setting(db: Session, key: str) -> str:
    return get_app_settings(db).get(key, APP_SETTING_DEFAULTS.get(key, ""))


def get_app_setting_bool(db: Session, key: str) -> bool:
    return to_bool(get_app_setting(db, key), False)


def update_app_settings(db: Session, payload: dict[str, str]) -> None:
    for key, default in APP_SETTING_DEFAULTS.items():
        raw = payload.get(key)
        value = str(raw).strip() if raw is not None else str(default)
        if key in {"debug", "zammad_verify_ssl"}:
            value = "1" if to_bool(value, False) else "0"
        if key == "zammad_per_page":
            try:
                value = str(max(1, int(value)))
            except Exception:
                value = APP_SETTING_DEFAULTS[key]
        if key == "tz":
            try:
                ZoneInfo(value)
            except ZoneInfoNotFoundError:
                value = APP_SETTING_DEFAULTS[key]

        row = db.query(AppSetting).filter(AppSetting.key == key).first()
        if key == "zammad_token" and value == "" and row is not None:
            continue
        if row is None:
            row = AppSetting(key=key, value=value, updated_at=datetime.utcnow())
            db.add(row)
        else:
            row.value = value
            row.updated_at = datetime.utcnow()
    db.commit()
