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
        latest_meta = db.query(EquipmentMetadata).filter(EquipmentMetadata.equipment_id == eq.id)\
            .order_by(EquipmentMetadata.recorded_at.desc()).first()
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
            "pressure": latest_meta.pressure if latest_meta else None,
            "temperature": latest_meta.temperature if latest_meta else None,
            "voltage": latest_meta.voltage if latest_meta else None,
            "frequency": latest_meta.frequency if latest_meta else None,
        })

    places = db.query(Place).all()
    equipment_types = db.query(EquipmentType).all()
    print("equipment_types: ",equipment_types)
    print("places: ",places)

    return templates.TemplateResponse("equipments.html", {
        "request": request,
        "user": user,
        "equipments": equipment_list,
        "places": places,
        "equipment_types": equipment_types,
        "page": page,
        "per_page": per_page,
        "total": total,
        "search": search
    })


# -------------------------
# Create Equipment
# -------------------------
@router.post("/create")
def create_equipment(
    name: str = Form(...),

    equipment_type_id: int | None = Form(None),
    equipment_type_name: str | None = Form(None),

    place_id: int = Form(...),
    status: str = Form(...),
    serviceability: str = Form(...),
    remarks: str = Form(None),

    db: Session = Depends(get_db),
    user=Depends(require_user)
):
    # --------------------------------------------------
    # Equipment Type handling
    # --------------------------------------------------
    if equipment_type_id:
        etype = db.query(EquipmentType).filter(
            EquipmentType.id == equipment_type_id
        ).first()
    else:
        if not equipment_type_name:
            raise HTTPException(400, "Equipment type required")

        type_name = equipment_type_name.strip().lower()

        etype = db.query(EquipmentType).filter(
            EquipmentType.name == type_name
        ).first()

        if not etype:
            etype = EquipmentType(name=type_name)
            db.add(etype)
            db.commit()
            db.refresh(etype)

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

    # Check or create equipment type
    etype = db.query(EquipmentType).filter(EquipmentType.name == equipment_type_name).first()
    if not etype:
        etype = EquipmentType(name=equipment_type_name)
        db.add(etype)
        db.commit()
        db.refresh(etype)

    eq.name = name
    eq.equipment_type_id = etype.id
    eq.place_id = place_id
    eq.status = status
    eq.serviceability = serviceability
    eq.remarks = remarks
    db.commit()

    # Add new metadata record
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

    return {
        "id": eq.id,
        "name": eq.name,
        "equipment_type_name": eq.equipment_type.name if eq.equipment_type else "",
        "place_name": eq.place.name if eq.place else "",
        "status": eq.status,
        "serviceability": eq.serviceability,
        "remarks": eq.remarks
    }