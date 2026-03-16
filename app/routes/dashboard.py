
from fastapi import APIRouter, Request, Depends
from sqlalchemy.orm import Session
from fastapi.templating import Jinja2Templates

from app.db.session import get_db
from app.core.auth_guard import require_user
from app.models.equipment import Equipment
from app.models.metadata import EquipmentMetadata

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/dashboard")
def dashboard(
    request: Request,
    db: Session = Depends(get_db),
    user = Depends(require_user)
):
    equipments = db.query(Equipment).all()

    cards = []
    serviceable = 0
    unserviceable = 0

    for eq in equipments:
        meta = (
            db.query(EquipmentMetadata)
            .filter_by(equipment_id=eq.id)
            .order_by(EquipmentMetadata.recorded_at.desc())
            .first()
        )

        if eq.serviceability == "S":
            serviceable += 1
        else:
            unserviceable += 1

        cards.append({
            "id": eq.id,
            "name": eq.name,
            "type": eq.equipment_type.name if eq.equipment_type else "—",
            "place": eq.place.name if eq.place else "—",
            "status": eq.status,
            "serviceability": eq.serviceability,
            "remarks": eq.remarks,
            "temperature": meta.temperature if meta else None,
            "voltage": meta.voltage if meta else None,
            "pressure": meta.pressure if meta else None,
            "frequency": meta.frequency if meta else None,
        })

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "user": user,
            "equipments": cards,
            "serviceable": serviceable,
            "unserviceable": unserviceable
        }
    )