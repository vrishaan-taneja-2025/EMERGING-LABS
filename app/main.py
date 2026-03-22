from fastapi import FastAPI
from fastapi.exceptions import HTTPException
from fastapi.staticfiles import StaticFiles
import app.models  # noqa: F401
from app.core.bootstrap import ensure_default_auth_data, ensure_default_telemetry_entities
from app.core.exception_handlers import http_exception_handler
from app.core.telemetry import telemetry_hub
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.routes import auth, equipment, di, places, roles, users, inspection, dashboard, telemetry, vector
from app.routes import pages

app = FastAPI(title="Datacenter DI System")

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(auth.router)
app.include_router(equipment.router)
app.include_router(dashboard.router)
app.include_router(di.router)
app.include_router(pages.router)
app.include_router(places.router)
app.include_router(roles.router)
app.include_router(users.router)
app.include_router(inspection.router)
app.include_router(telemetry.router)
app.include_router(vector.router)
app.add_exception_handler(HTTPException, http_exception_handler)


@app.on_event("startup")
async def startup_event():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        ensure_default_auth_data(db)
        ensure_default_telemetry_entities(db)
    finally:
        db.close()
    await telemetry_hub.start()


@app.on_event("shutdown")
async def shutdown_event():
    await telemetry_hub.stop()
