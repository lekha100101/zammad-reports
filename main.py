from fastapi import FastAPI
from app.db import Base, engine
from app.routes import reports, sync

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Zammad Reports")

app.include_router(sync.router)
app.include_router(reports.router)

@app.get("/")
def root():
    return {"message": "Zammad Reports API is running"}
