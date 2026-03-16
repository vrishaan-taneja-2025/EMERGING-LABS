
from fastapi import FastAPI
from fastapi.exceptions import HTTPException
from fastapi.staticfiles import StaticFiles
from app.core.exception_handlers import http_exception_handler
from app.routes import auth, equipment, di, places, roles, users, inspection,dashboard
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
app.add_exception_handler(HTTPException, http_exception_handler)