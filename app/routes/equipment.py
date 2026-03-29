from fastapi import APIRouter, Request, Form, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.equipment import Equipment
from app.models.metadata import EquipmentMetadata
from app.models.place import Place
from app.models.equipment_type import EquipmentType
from app.core.auth_guard import require_user
from fastapi.templating import Jinja2Templates

router = APIRouter(prefix="/equipments")
templates = Jinja2Templates(directory="app/templates")


def get_latest_metadata(db: Session, equipment_id: int):
    return (
        db.query(EquipmentMetadata)
        .filter(EquipmentMetadata.equipment_id == equipment_id)
        .order_by(EquipmentMetadata.recorded_at.desc())
        .first()
    )


def resolve_equipment_type(
    db: Session,
    equipment_type_id: int | None,
    equipment_type_name: str | None,
    new_equipment_type: str | None = None,
):
    if equipment_type_id:
        etype = db.query(EquipmentType).filter(
            EquipmentType.id == equipment_type_id
        ).first()
        if not etype:
            raise HTTPException(400, "Invalid equipment type")
        return etype

    selected_name = (equipment_type_name or "").strip()
    if selected_name == "__other__":
        selected_name = (new_equipment_type or "").strip()

    if not selected_name:
        raise HTTPException(400, "Equipment type required")

    normalized_name = selected_name.lower()
    etype = db.query(EquipmentType).filter(
        EquipmentType.name == normalized_name
    ).first()

    if not etype:
        etype = EquipmentType(name=normalized_name)
        db.add(etype)
        db.commit()
        db.refresh(etype)

    return etype


# -------------------------
# List Equipments
# -------------------------
@router.get("/")
def list_equipments(request: Request, user=Depends(require_user), db: Session = Depends(get_db)):
    search = request.query_params.get("search", "")
    page = int(request.query_params.get("page", 1))
    per_page = 10

    query = db.query(Equipment)
    if search:
        query = query.filter(Equipment.name.ilike(f"%{search}%"))

    total = query.count()
    equipments = query.offset((page - 1) * per_page).limit(per_page).all()

    # Add latest metadata
    equipment_list = []
    for eq in equipments:
        latest_meta = get_latest_metadata(db, eq.id)
        equipment_list.append({
            "id": eq.id,
            "name": eq.name,
            "place_id": eq.place_id,
            "place_name": eq.place.name if eq.place else "",
            "equipment_type_id": eq.equipment_type_id,
            "equipment_type_name": eq.equipment_type.name if eq.equipment_type else "",
            "status": eq.status,
            "serviceability": eq.serviceability,
            "remarks": eq.remarks,
            "has_metadata": latest_meta is not None,
            "pressure": latest_meta.pressure if latest_meta else None,
            "temperature": latest_meta.temperature if latest_meta else None,
            "voltage": latest_meta.voltage if latest_meta else None,
            "frequency": latest_meta.frequency if latest_meta else None,
        })

    places = db.query(Place).all()
    equipment_types = db.query(EquipmentType).all()
    print("equipment_types: ",equipment_types)
    print("places: ",places)

    return templates.TemplateResponse(
        request,
        "equipments.html",
        {
            "request": request,
            "user": user,
            "equipments": equipment_list,
            "places": places,
            "equipment_types": equipment_types,
            "page": page,
            "per_page": per_page,
            "total": total,
            "search": search
        },
    )


# -------------------------
# Create Equipment
# -------------------------
@router.post("/create")
def create_equipment(
    name: str = Form(...),

    equipment_type_id: int | None = Form(None),
    equipment_type_name: str | None = Form(None),
    new_equipment_type: str | None = Form(None),

    place_id: int = Form(...),
    status: str = Form(...),
    serviceability: str = Form(...),
    remarks: str = Form(None),

    db: Session = Depends(get_db),
    user=Depends(require_user)
):
    etype = resolve_equipment_type(
        db,
        equipment_type_id=equipment_type_id,
        equipment_type_name=equipment_type_name,
        new_equipment_type=new_equipment_type,
    )

    # --------------------------------------------------
    # Create Equipment (NO METADATA HERE)
    # --------------------------------------------------
    equipment = Equipment(
        name=name,
        equipment_type_id=etype.id,
        place_id=place_id,
        status=status,
        serviceability=serviceability,
        remarks=remarks
    )

    db.add(equipment)
    db.commit()

    return RedirectResponse("/equipments/", status_code=302)
# -------------------------
# Edit Equipment
# -------------------------
@router.post("/edit/{eq_id}")
def edit_equipment(
    eq_id: int,
    name: str = Form(...),
    equipment_type_name: str = Form(...),
    new_equipment_type: str | None = Form(None),
    place_id: int = Form(...),
    status: str = Form(...),
    serviceability: str = Form(...),
    remarks: str = Form(None),
    pressure: float = Form(None),
    temperature: float = Form(None),
    voltage: float = Form(None),
    frequency: float = Form(None),
    db: Session = Depends(get_db),
    user=Depends(require_user)
):
    eq = db.query(Equipment).filter(Equipment.id == eq_id).first()
    if not eq:
        raise HTTPException(status_code=404, detail="Equipment not found")

    etype = resolve_equipment_type(
        db,
        equipment_type_id=None,
        equipment_type_name=equipment_type_name,
        new_equipment_type=new_equipment_type,
    )

    eq.name = name
    eq.equipment_type_id = etype.id
    eq.place_id = place_id
    eq.status = status
    eq.serviceability = serviceability
    eq.remarks = remarks
    db.commit()

    if any(value is not None for value in [pressure, temperature, voltage, frequency]):
        meta = EquipmentMetadata(
            equipment_id=eq.id,
            pressure=pressure,
            temperature=temperature,
            voltage=voltage,
            frequency=frequency
        )
        db.add(meta)
        db.commit()

    return RedirectResponse("/equipments/", status_code=302)


# -------------------------
# Delete Equipment
# -------------------------
@router.get("/delete/{eq_id}")
def delete_equipment(eq_id: int, db: Session = Depends(get_db), user=Depends(require_user)):
    eq = db.query(Equipment).filter(Equipment.id == eq_id).first()
    if not eq:
        raise HTTPException(status_code=404, detail="Equipment not found")

    # Delete all metadata first
    db.query(EquipmentMetadata).filter(EquipmentMetadata.equipment_id == eq.id).delete()
    db.delete(eq)
    db.commit()
    return RedirectResponse("/equipments/", status_code=302)
# -------------------------
# View Equipment
# -------------------------
@router.get("/get/{eq_id}")
def get_equipment(eq_id: int, db: Session = Depends(get_db), user=Depends(require_user)):
    eq = db.query(Equipment).filter(Equipment.id == eq_id).first()
    if not eq:
        raise HTTPException(status_code=404, detail="Equipment not found")

    latest_meta = get_latest_metadata(db, eq.id)

    return {
        "id": eq.id,
        "name": eq.name,
        "place_id": eq.place_id,
        "equipment_type_name": eq.equipment_type.name if eq.equipment_type else "",
        "place_name": eq.place.name if eq.place else "",
        "status": eq.status,
        "serviceability": eq.serviceability,
        "remarks": eq.remarks,
        "has_metadata": latest_meta is not None,
        "metadata": {
            "pressure": latest_meta.pressure,
            "temperature": latest_meta.temperature,
            "voltage": latest_meta.voltage,
            "frequency": latest_meta.frequency,
        } if latest_meta else None,
    }
