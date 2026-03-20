from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload

from app.core.auth_guard import require_user
from app.core.telemetry import (
    TELEMETRY_API_KEY,
    TelemetryEvent,
    build_topic,
    normalize_component_type,
    telemetry_hub,
)
from app.db.session import get_db
from app.models.equipment import Equipment
from app.models.telemetry_alert import TelemetryAlert
from app.models.telemetry_record import TelemetryRecord

router = APIRouter(prefix="/api/telemetry", tags=["Telemetry"])


class TelemetryPublishPayload(BaseModel):
    equipment_id: int
    component_type: str
    status: str
    temperature: float | None = None
    voltage: float | None = None
    pressure: float | None = None
    frequency: float | None = None


def _verify_publisher_key(key: str | None):
    if key != TELEMETRY_API_KEY:
        raise HTTPException(401, "Invalid telemetry publisher key")


@router.get("/components")
def list_components(
    db: Session = Depends(get_db),
    x_telemetry_key: str | None = Header(default=None),
):
    _verify_publisher_key(x_telemetry_key)

    equipments = (
        db.query(Equipment)
        .options(joinedload(Equipment.equipment_type))
        .all()
    )

    return {
        "components": [
            {
                "equipment_id": eq.id,
                "name": eq.name,
                "status": (eq.status or "Off"),
                "component_type": normalize_component_type(eq.equipment_type.name if eq.equipment_type else None),
                "topic": build_topic(
                    normalize_component_type(eq.equipment_type.name if eq.equipment_type else None),
                    eq.id,
                ),
            }
            for eq in equipments
        ]
    }


@router.post("/publish")
async def publish_telemetry(
    payload: TelemetryPublishPayload,
    db: Session = Depends(get_db),
    x_telemetry_key: str | None = Header(default=None),
):
    _verify_publisher_key(x_telemetry_key)

    equipment = db.query(Equipment).filter(Equipment.id == payload.equipment_id).first()
    if not equipment:
        raise HTTPException(404, "Equipment not found")

    if (payload.status or "").lower() != "on":
        return {"published": False, "reason": "component is off"}

    await telemetry_hub.publish(
        TelemetryEvent(
            equipment_id=equipment.id,
            equipment_name=equipment.name,
            component_type=normalize_component_type(payload.component_type),
            topic=build_topic(normalize_component_type(payload.component_type), equipment.id),
            status=payload.status,
            temperature=payload.temperature,
            voltage=payload.voltage,
            pressure=payload.pressure,
            frequency=payload.frequency,
            published_at=datetime.now(timezone.utc),
        )
    )
    return {"published": True}


@router.get("/dashboard")
def telemetry_dashboard(
    db: Session = Depends(get_db),
    user=Depends(require_user),
):
    items = telemetry_hub.snapshot()
    if items:
        return {"items": items}

    latest_records = (
        db.query(TelemetryRecord)
        .options(joinedload(TelemetryRecord.equipment).joinedload(Equipment.place))
        .options(joinedload(TelemetryRecord.equipment).joinedload(Equipment.equipment_type))
        .order_by(TelemetryRecord.created_at.desc())
        .limit(200)
        .all()
    )

    latest_by_equipment: dict[int, TelemetryRecord] = {}
    for record in latest_records:
        if record.equipment_id not in latest_by_equipment:
            latest_by_equipment[record.equipment_id] = record

    return {
        "items": [
            {
                "id": record.equipment_id,
                "name": record.equipment.name if record.equipment else f"Equipment {record.equipment_id}",
                "topic": record.topic,
                "component_type": record.component_type,
                "status": record.status,
                "temperature": record.temperature,
                "voltage": record.voltage,
                "pressure": record.pressure,
                "frequency": record.frequency,
                "place": record.equipment.place.name if record.equipment and record.equipment.place else "-",
                "type": record.equipment.equipment_type.name if record.equipment and record.equipment.equipment_type else record.component_type,
                "updated_at": record.created_at.isoformat() if record.created_at else None,
                "is_anomaly": record.is_anomaly,
            }
            for record in latest_by_equipment.values()
        ]
    }


@router.get("/alerts")
def telemetry_alerts(
    db: Session = Depends(get_db),
    user=Depends(require_user),
):
    alerts = (
        db.query(TelemetryAlert)
        .options(joinedload(TelemetryAlert.equipment))
        .filter(TelemetryAlert.is_active.is_(True))
        .order_by(TelemetryAlert.created_at.desc())
        .limit(20)
        .all()
    )

    return {
        "alerts": [
            {
                "id": alert.id,
                "title": alert.title,
                "message": alert.message,
                "severity": alert.severity,
                "equipment_name": alert.equipment.name if alert.equipment else "-",
                "created_at": alert.created_at.isoformat() if alert.created_at else None,
            }
            for alert in alerts
        ]
    }
