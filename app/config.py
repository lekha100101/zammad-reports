from pydantic import BaseModel
from dotenv import load_dotenv
import os

load_dotenv()


def to_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class Settings(BaseModel):
    app_name: str = os.getenv("APP_NAME", "Zammad Reports MVP")
    debug: bool = to_bool(os.getenv("DEBUG"), True)
    secret_key: str = os.getenv("SECRET_KEY", "change-me")

    zammad_url: str = os.getenv("ZAMMAD_URL", "").rstrip("/")
    zammad_token: str = os.getenv("ZAMMAD_TOKEN", "")
    zammad_verify_ssl: bool = to_bool(os.getenv("ZAMMAD_VERIFY_SSL"), True)
    zammad_per_page: int = int(os.getenv("ZAMMAD_PER_PAGE", "100"))

    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5433/zammad_reports",
    )

    tz: str = os.getenv("TZ", "Asia/Almaty")


settings = Settings()
