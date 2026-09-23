import os

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.auth import bootstrap_admin
from app.config import settings
from app.db import Base, SessionLocal, engine
from app.routes import api, auth_routes, sync, ui, users_admin
from app.routes import admin_regions, excluded_groups, sla_dashboard
from app.services.app_settings_service import get_app_setting
from app.services.report_group_exclusions import (
    parse_excluded_group_ids,
    reset_report_excluded_group_ids,
    set_report_excluded_group_ids,
)

Base.metadata.create_all(bind=engine)

app = FastAPI(title=settings.app_name, debug=settings.debug)

app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SECRET_KEY", "change-me"),
    same_site="lax",
    https_only=os.getenv("SESSION_HTTPS_ONLY", "false").lower() == "true",
)


@app.middleware("http")
async def report_group_exclusion_middleware(request: Request, call_next):
    # Exclusions affect analytics only. Sync/API/admin data remains complete.
    is_report_request = request.url.path == "/" or request.url.path.startswith("/reports/")
    token = None
    if is_report_request:
        db = SessionLocal()
        try:
            group_ids = parse_excluded_group_ids(get_app_setting(db, "excluded_report_group_ids"))
        finally:
            db.close()
        token = set_report_excluded_group_ids(group_ids)

    try:
        return await call_next(request)
    finally:
        if token is not None:
            reset_report_excluded_group_ids(token)


app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(auth_routes.router)
app.include_router(ui.router)
app.include_router(sla_dashboard.router)
app.include_router(sync.router)
app.include_router(api.router)
app.include_router(users_admin.router)
app.include_router(admin_regions.router)
app.include_router(excluded_groups.router)


@app.on_event("startup")
def startup():
    db = SessionLocal()
    try:
        bootstrap_admin(db)
    finally:
        db.close()


@app.get("/health")
def health():
    return {"status": "ok"}
