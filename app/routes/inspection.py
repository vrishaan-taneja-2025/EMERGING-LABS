from fastapi import APIRouter, Request, Form, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from datetime import date
from app.db.session import get_db
from app.core.auth_guard import ensure_user_has_role, get_user_role_name, require_user
from fastapi.templating import Jinja2Templates

from app.models.daily_inspection import DailyInspection
from app.models.di_equipment_log import DIEquipmentLog
from app.models.equipment import Equipment
from app.models.metadata import EquipmentMetadata
from app.models.di_workflow import DIWorkflow
from app.models.di_snapshot import DISnapshot

router = APIRouter(prefix="/inspection", tags=["Inspection"])
templates = Jinja2Templates(directory="app/templates")


def latest_metadata_for_equipment(db: Session, equipment_id: int):
    return (
        db.query(EquipmentMetadata)
        .filter(EquipmentMetadata.equipment_id == equipment_id)
        .order_by(EquipmentMetadata.recorded_at.desc())
        .first()
    )


def upsert_equipment_metadata(
    db: Session,
    equipment_id: int,
    pressure: float | None,
    temperature: float | None,
    voltage: float | None,
    frequency: float | None,
):
    metadata = latest_metadata_for_equipment(db, equipment_id)
    if not metadata:
        metadata = EquipmentMetadata(equipment_id=equipment_id)

    metadata.pressure = pressure
    metadata.temperature = temperature
    metadata.voltage = voltage
    metadata.frequency = frequency

    db.add(metadata)
    db.commit()

# --------------------------------------------------
# VIEW EQUIPMENT CARDS (EVERYONE)
# --------------------------------------------------
@router.get("/equipments")
def equipment_cards(request: Request, db: Session = Depends(get_db), user=Depends(require_user)):
    equipments = db.query(Equipment).all()
    return templates.TemplateResponse(
        request,
        "equipment_cards.html",
        {"request": request, "equipments": equipments, "user": user}
    )

# --------------------------------------------------
# CREATE DI – SHOW EQUIPMENT CARDS
# --------------------------------------------------
@router.get("/di")
def di_cards(request: Request, db: Session = Depends(get_db), user=Depends(require_user)):
    ensure_user_has_role(user, "user")
    equipments = db.query(Equipment).all()
    equipment_cards = [
        {
            "equipment": eq,
            "metadata": latest_metadata_for_equipment(db, eq.id),
        }
        for eq in equipments
    ]
    return templates.TemplateResponse(
        request,
        "di_cards.html",
        {"request": request, "equipments": equipment_cards, "user": user}
    )

# --------------------------------------------------
# SUBMIT DI
# --------------------------------------------------
@router.post("/di")
async def submit_di(request: Request, db: Session = Depends(get_db), user=Depends(require_user)):
    ensure_user_has_role(user, "user")
    form = await request.form()
    di = DailyInspection(
        inspection_date=date.today(),
        created_by=user.id,
        status="submitted"
    )
    db.add(di)
    db.commit()
    db.refresh(di)

    for key, value in form.items():
        if key.startswith("serviceability_"):
            eq_id = int(key.split("_")[1])
            remarks = form.get(f"remarks_{eq_id}", "")
            db.add(DIEquipmentLog(
                di_id=di.id,
                equipment_id=eq_id,
                serviceability=value,
                remarks=remarks
            ))

    db.commit()
    return RedirectResponse("/inspection/status", 302)

# --------------------------------------------------
# SUPERVISOR – ADD METADATA
# --------------------------------------------------
@router.post("/metadata/{equipment_id}")
def add_metadata(
    equipment_id: int,
    pressure: float = Form(None),
    temperature: float = Form(None),
    voltage: float = Form(None),
    frequency: float = Form(None),
    db: Session = Depends(get_db),
    user=Depends(require_user)
):
    ensure_user_has_role(user, "user", "supervisor")

    if not any([pressure, temperature, voltage, frequency]):
        return RedirectResponse("/inspection/di", 302)

    upsert_equipment_metadata(db, equipment_id, pressure, temperature, voltage, frequency)
    return RedirectResponse("/inspection/di", 302)

# --------------------------------------------------
# REVIEW & APPROVAL
# --------------------------------------------------
@router.post("/approve/{di_id}")
def approve_di(
    di_id: int,
    comments: str = Form(None),
    db: Session = Depends(get_db),
    user=Depends(require_user)
):
    di = db.query(DailyInspection).filter_by(id=di_id).first()
    if not di:
        raise HTTPException(404)

    FLOW = {
        "submitted": ("supervisor", "supervisor_approved"),
        "supervisor_approved": ("reviewer", "reviewer_approved"),
        "reviewer_approved": ("manager", "completed"),
    }

    if di.status not in FLOW:
        raise HTTPException(403, "Invalid state")

    required_role, next_status = FLOW[di.status]

    if get_user_role_name(user) != required_role:
        raise HTTPException(403, "Unauthorized")

    di.status = next_status

    db.add(DIWorkflow(
        di_id=di.id,
        from_role=required_role,
        to_role=next_status,
        action="approved",
        comments=comments,
        acted_by=user.id
    ))

    # -------------------------
    # FINAL SNAPSHOT (SAFE)
    # -------------------------
    if next_status == "completed":
        snapshot = []

        equipments = db.query(Equipment).all()
        for eq in equipments:
            meta = db.query(EquipmentMetadata)\
                     .filter_by(equipment_id=eq.id)\
                     .first()

            snapshot.append({
                "equipment_id": eq.id,
                "equipment_name": eq.name,
                "place": eq.place.name if eq.place else None,
                "equipment_type": eq.equipment_type.name if eq.equipment_type else None,
                "status": eq.status,
                "serviceability": eq.serviceability,
                "remarks": eq.remarks,
                "metadata": {
                    "pressure": meta.pressure,
                    "temperature": meta.temperature,
                    "humidity": meta.humidity,
                    "voltage": meta.voltage,
                    "frequency": meta.frequency,
                    "recorded_at": meta.recorded_at.isoformat()
                } if meta else None
            })

        db.add(DISnapshot(
            di_id=di.id,
            snapshot_date=di.inspection_date,
            data=snapshot
        ))

    db.commit()
    return RedirectResponse("/inspection/status", 302)

# --------------------------------------------------
# STATUS PAGE
# --------------------------------------------------
@router.get("/status")
def di_status(request: Request, db: Session = Depends(get_db), user=Depends(require_user)):
    di_list = db.query(DailyInspection).order_by(DailyInspection.created_at.desc()).all()
    return templates.TemplateResponse(
        request,
        "di_status.html",
        {"request": request, "di_list": di_list, "user": user}
    )


@router.post("/reject/{di_id}")
def reject_di(
    di_id: int,
    comments: str = Form(...),
    db: Session = Depends(get_db),
    user=Depends(require_user)
):
    ensure_user_has_role(user, "supervisor", "reviewer", "manager")
    di = db.query(DailyInspection).filter_by(id=di_id).first()
    if not di:
        raise HTTPException(404)

    if di.status in {"completed", "rejected"}:
        raise HTTPException(403)

    flow = {
        "submitted": "supervisor",
        "supervisor_approved": "reviewer",
        "reviewer_approved": "manager",
    }
    required_role = flow.get(di.status)
    if required_role and get_user_role_name(user) != required_role:
        raise HTTPException(403, "Unauthorized")

    di.status = "rejected"

    db.add(DIWorkflow(
        di_id=di.id,
        from_role=user.role.name,
        to_role="rejected",
        action="rejected",
        comments=comments,
        acted_by=user.id
    ))

    db.commit()
    return RedirectResponse("/inspection/status", 302)
