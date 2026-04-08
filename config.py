from pydantic import BaseModel
from dotenv import load_dotenv
import os

load_dotenv()

class Settings(BaseModel):
    app_name: str = "Zammad Reports"
    debug: bool = os.getenv("DEBUG", "false").lower() == "true"

    zammad_url: str = os.getenv("ZAMMAD_URL", "https://support.dcsource.kz").rstrip("/")
    zammad_token: str = os.getenv("ZAMMAD_TOKEN", "CLkvrl_b2y866jHXvX3a3hx3wynQfHqLZubR-cdhr_WJHu0nPHOiQg")

    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5432/zammad_reports"
    )

settings = Settings()
