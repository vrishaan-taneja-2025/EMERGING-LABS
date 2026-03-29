from fastapi import APIRouter, Request, Depends
from datetime import datetime, timedelta, timezone

from sqlalchemy import case, func
from sqlalchemy.orm import Session, joinedload
from fastapi.templating import Jinja2Templates

from app.db.session import get_db
from app.core.auth_guard import require_user
from app.models.daily_inspection import DailyInspection
from app.models.equipment import Equipment
from app.models.equipment_type import EquipmentType
from app.models.metadata import EquipmentMetadata
from app.models.place import Place
from app.models.telemetry_alert import TelemetryAlert
from app.models.telemetry_record import TelemetryRecord
from app.models.user import User

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/dashboard")
def dashboard(
    request: Request,
    db: Session = Depends(get_db),
    user = Depends(require_user)
):
    now_utc = datetime.now(timezone.utc)
    since_24h = now_utc - timedelta(hours=24)
    since_7d = now_utc - timedelta(days=6)

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

    total_places = db.query(func.count(Place.id)).scalar() or 0
    total_users = db.query(func.count(User.id)).scalar() or 0
    total_inspections = db.query(func.count(DailyInspection.id)).scalar() or 0
    completed_inspections = (
        db.query(func.count(DailyInspection.id))
        .filter(DailyInspection.status == "completed")
        .scalar()
        or 0
    )
    pending_inspections = (
        db.query(func.count(DailyInspection.id))
        .filter(DailyInspection.status.notin_(["completed", "rejected"]))
        .scalar()
        or 0
    )
    active_alerts = (
        db.query(func.count(TelemetryAlert.id))
        .filter(TelemetryAlert.is_active.is_(True))
        .scalar()
        or 0
    )
    telemetry_24h = (
        db.query(func.count(TelemetryRecord.id))
        .filter(TelemetryRecord.created_at >= since_24h)
        .scalar()
        or 0
    )
    anomalies_24h = (
        db.query(func.count(TelemetryRecord.id))
        .filter(
            TelemetryRecord.created_at >= since_24h,
            TelemetryRecord.is_anomaly.is_(True),
        )
        .scalar()
        or 0
    )
    avg_temp_24h = (
        db.query(func.avg(TelemetryRecord.temperature))
        .filter(
            TelemetryRecord.created_at >= since_24h,
            TelemetryRecord.temperature.isnot(None),
        )
        .scalar()
    )

    inspection_status_rows = (
        db.query(DailyInspection.status, func.count(DailyInspection.id))
        .group_by(DailyInspection.status)
        .order_by(DailyInspection.status.asc())
        .all()
    )

    equipment_type_rows = (
        db.query(EquipmentType.name, func.count(Equipment.id))
        .outerjoin(Equipment, Equipment.equipment_type_id == EquipmentType.id)
        .group_by(EquipmentType.name)
        .order_by(func.count(Equipment.id).desc(), EquipmentType.name.asc())
        .all()
    )

    place_serviceability_rows = (
        db.query(
            Place.name,
            func.sum(case((Equipment.serviceability == "S", 1), else_=0)).label("serviceable"),
            func.sum(case((Equipment.serviceability != "S", 1), else_=0)).label("unserviceable"),
        )
        .outerjoin(Equipment, Equipment.place_id == Place.id)
        .group_by(Place.name)
        .order_by(Place.name.asc())
        .all()
    )

    telemetry_daily_rows = (
        db.query(
            func.date(TelemetryRecord.created_at).label("day"),
            func.count(TelemetryRecord.id).label("events"),
            func.sum(case((TelemetryRecord.is_anomaly.is_(True), 1), else_=0)).label("anomalies"),
        )
        .filter(TelemetryRecord.created_at >= since_7d)
        .group_by(func.date(TelemetryRecord.created_at))
        .order_by(func.date(TelemetryRecord.created_at).asc())
        .all()
    )

    recent_alerts = (
        db.query(TelemetryAlert)
        .options(joinedload(TelemetryAlert.equipment))
        .filter(TelemetryAlert.is_active.is_(True))
        .order_by(TelemetryAlert.created_at.desc())
        .limit(5)
        .all()
    )
    recent_inspections = (
        db.query(DailyInspection)
        .options(joinedload(DailyInspection.user))
        .order_by(DailyInspection.created_at.desc())
        .limit(6)
        .all()
    )

    summary_cards = [
        {
            "label": "Total Equipments",
            "value": len(cards),
            "hint": "Registered assets in the platform",
            "tone": "slate",
        },
        {
            "label": "Serviceable",
            "value": serviceable,
            "hint": "Equipment ready for operations",
            "tone": "green",
        },
        {
            "label": "Unserviceable",
            "value": unserviceable,
            "hint": "Assets needing follow-up",
            "tone": "red",
        },
        {
            "label": "Active Alerts",
            "value": active_alerts,
            "hint": "Current telemetry anomalies",
            "tone": "amber",
        },
        {
            "label": "Telemetry Events (24h)",
            "value": telemetry_24h,
            "hint": "DB-backed recent telemetry volume",
            "tone": "blue",
        },
        {
            "label": "Pending Inspections",
            "value": pending_inspections,
            "hint": "Awaiting approval or completion",
            "tone": "violet",
        },
    ]

    secondary_metrics = [
        {
            "label": "Total Places",
            "value": total_places,
        },
        {
            "label": "Total Users",
            "value": total_users,
        },
        {
            "label": "Total Inspections",
            "value": total_inspections,
        },
        {
            "label": "Completed Inspections",
            "value": completed_inspections,
        },
        {
            "label": "Anomalies (24h)",
            "value": anomalies_24h,
        },
        {
            "label": "Avg Temp (24h)",
            "value": round(avg_temp_24h, 1) if avg_temp_24h is not None else "—",
        },
    ]

    chart_data = {
        "telemetry_daily": {
            "labels": [str(row.day) for row in telemetry_daily_rows],
            "events": [int(row.events or 0) for row in telemetry_daily_rows],
            "anomalies": [int(row.anomalies or 0) for row in telemetry_daily_rows],
        },
        "inspection_status": {
            "labels": [row.status.replace("_", " ").title() for row in inspection_status_rows],
            "values": [int(row[1]) for row in inspection_status_rows],
        },
        "equipment_type": {
            "labels": [row[0].title() if row[0] else "Unknown" for row in equipment_type_rows],
            "values": [int(row[1] or 0) for row in equipment_type_rows],
        },
    }

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "request": request,
            "user": user,
            "equipments": cards,
            "serviceable": serviceable,
            "unserviceable": unserviceable,
            "summary_cards": summary_cards,
            "secondary_metrics": secondary_metrics,
            "place_serviceability": place_serviceability_rows,
            "recent_alerts": recent_alerts,
            "recent_inspections": recent_inspections,
            "chart_data": chart_data,
        }
    )
