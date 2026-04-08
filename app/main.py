import os

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.auth import bootstrap_admin
from app.config import settings
from app.db import Base, SessionLocal, engine
from app.routes import api, auth_routes, sync, ui, users_admin
from app.routes import admin_regions

Base.metadata.create_all(bind=engine)

app = FastAPI(title=settings.app_name, debug=settings.debug)

app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SECRET_KEY", "change-me"),
    same_site="lax",
    https_only=os.getenv("SESSION_HTTPS_ONLY", "false").lower() == "true",
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(auth_routes.router)
app.include_router(ui.router)
app.include_router(sync.router)
app.include_router(api.router)
app.include_router(users_admin.router)
app.include_router(admin_regions.router)


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
