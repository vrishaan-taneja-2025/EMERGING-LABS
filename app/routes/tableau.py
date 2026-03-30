import csv
from datetime import date, datetime, timedelta
from io import StringIO
from typing import Any, Iterable

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session, joinedload

from app.core.auth_guard import require_user
from app.db.session import get_db
from app.models.daily_inspection import DailyInspection
from app.models.di_workflow import DIWorkflow
from app.models.equipment import Equipment
from app.models.telemetry_alert import TelemetryAlert
from app.models.telemetry_record import TelemetryRecord
from app.models.user import User

router = APIRouter(prefix="/api/tableau", tags=["Tableau Live"])


def _serialize(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def _to_csv(rows: Iterable[dict[str, Any]], fieldnames: list[str]) -> str:
    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow({key: _serialize(row.get(key)) for key in fieldnames})
    return buffer.getvalue()


def _format_response(
    rows: list[dict[str, Any]],
    fieldnames: list[str],
    output_format: str,
    filename: str,
):
    if output_format == "csv":
        csv_body = _to_csv(rows, fieldnames)
        headers = {"Content-Disposition": f"attachment; filename={filename}.csv"}
        return PlainTextResponse(content=csv_body, media_type="text/csv", headers=headers)

    return {
        "source": "postgresql_live",
        "count": len(rows),
        "fields": fieldnames,
        "items": rows,
    }


def _validate_format(output_format: str) -> None:
    if output_format not in {"json", "csv"}:
        raise HTTPException(status_code=400, detail="format must be either 'json' or 'csv'")


@router.get("/health")
def tableau_health(db: Session = Depends(get_db), user=Depends(require_user)):
    if hasattr(user, "status_code"):
        return user

    equipment_count = db.query(Equipment).count()
    telemetry_count = db.query(TelemetryRecord).count()
    return {
        "status": "ok",
        "mode": "live_database",
        "equipment_count": equipment_count,
        "telemetry_count": telemetry_count,
    }


@router.get("/equipment-master")
def equipment_master(
    format: str = Query("json"),
    db: Session = Depends(get_db),
    user=Depends(require_user),
):
    if hasattr(user, "status_code"):
        return user
    _validate_format(format)

    rows = (
        db.query(Equipment)
        .options(joinedload(Equipment.place), joinedload(Equipment.equipment_type))
        .order_by(Equipment.id.asc())
        .all()
    )

    items = [
        {
            "equipment_id": row.id,
            "equipment_name": row.name,
            "equipment_type": row.equipment_type.name if row.equipment_type else None,
            "place": row.place.name if row.place else None,
            "status": row.status,
            "serviceability": row.serviceability,
            "remarks": row.remarks,
            "created_at": row.created_at,
        }
        for row in rows
    ]
    fields = [
        "equipment_id",
        "equipment_name",
        "equipment_type",
        "place",
        "status",
        "serviceability",
        "remarks",
        "created_at",
    ]
    return _format_response(items, fields, format, "tableau_equipment_master")


@router.get("/telemetry-fact")
def telemetry_fact(
    days: int = Query(30, ge=1, le=3650),
    format: str = Query("json"),
    db: Session = Depends(get_db),
    user=Depends(require_user),
):
    if hasattr(user, "status_code"):
        return user
    _validate_format(format)
    cutoff = datetime.utcnow() - timedelta(days=days)

    query = (
        db.query(TelemetryRecord, Equipment)
        .join(Equipment, TelemetryRecord.equipment_id == Equipment.id)
        .filter(TelemetryRecord.created_at >= cutoff)
        .order_by(TelemetryRecord.created_at.desc())
    )
    rows = query.all()

    items = [
        {
            "telemetry_id": record.id,
            "equipment_id": record.equipment_id,
            "equipment_name": equipment.name,
            "component_type": record.component_type,
            "topic": record.topic,
            "status": record.status,
            "temperature": record.temperature,
            "voltage": record.voltage,
            "pressure": record.pressure,
            "frequency": record.frequency,
            "is_anomaly": record.is_anomaly,
            "anomaly_message": record.anomaly_message,
            "created_at": record.created_at,
        }
        for record, equipment in rows
    ]
    fields = [
        "telemetry_id",
        "equipment_id",
        "equipment_name",
        "component_type",
        "topic",
        "status",
        "temperature",
        "voltage",
        "pressure",
        "frequency",
        "is_anomaly",
        "anomaly_message",
        "created_at",
    ]
    return _format_response(items, fields, format, "tableau_telemetry_fact")


@router.get("/inspection-fact")
def inspection_fact(
    format: str = Query("json"),
    db: Session = Depends(get_db),
    user=Depends(require_user),
):
    if hasattr(user, "status_code"):
        return user
    _validate_format(format)

    rows = (
        db.query(DailyInspection)
        .options(joinedload(DailyInspection.user))
        .order_by(DailyInspection.created_at.desc())
        .all()
    )

    items = [
        {
            "inspection_id": row.id,
            "inspection_date": row.inspection_date,
            "status": row.status,
            "created_by": row.created_by,
            "created_by_username": row.user.username if row.user else None,
            "created_at": row.created_at,
        }
        for row in rows
    ]
    fields = [
        "inspection_id",
        "inspection_date",
        "status",
        "created_by",
        "created_by_username",
        "created_at",
    ]
    return _format_response(items, fields, format, "tableau_inspection_fact")


@router.get("/workflow-fact")
def workflow_fact(
    format: str = Query("json"),
    db: Session = Depends(get_db),
    user=Depends(require_user),
):
    if hasattr(user, "status_code"):
        return user
    _validate_format(format)

    user_by_id = {user.id: user.username for user in db.query(User).all()}
    rows = db.query(DIWorkflow).order_by(DIWorkflow.acted_at.desc()).all()

    items = [
        {
            "workflow_id": row.id,
            "di_id": row.di_id,
            "from_role": row.from_role,
            "to_role": row.to_role,
            "action": row.action,
            "comments": row.comments,
            "acted_by": row.acted_by,
            "acted_by_username": user_by_id.get(row.acted_by),
            "acted_at": row.acted_at,
        }
        for row in rows
    ]
    fields = [
        "workflow_id",
        "di_id",
        "from_role",
        "to_role",
        "action",
        "comments",
        "acted_by",
        "acted_by_username",
        "acted_at",
    ]
    return _format_response(items, fields, format, "tableau_workflow_fact")


@router.get("/alert-fact")
def alert_fact(
    format: str = Query("json"),
    db: Session = Depends(get_db),
    user=Depends(require_user),
):
    if hasattr(user, "status_code"):
        return user
    _validate_format(format)

    rows = (
        db.query(TelemetryAlert, Equipment)
        .join(Equipment, TelemetryAlert.equipment_id == Equipment.id)
        .order_by(TelemetryAlert.created_at.desc())
        .all()
    )

    items = [
        {
            "alert_id": row.id,
            "equipment_id": row.equipment_id,
            "equipment_name": equipment.name,
            "severity": row.severity,
            "title": row.title,
            "message": row.message,
            "is_active": row.is_active,
            "created_at": row.created_at,
        }
        for row, equipment in rows
    ]
    fields = [
        "alert_id",
        "equipment_id",
        "equipment_name",
        "severity",
        "title",
        "message",
        "is_active",
        "created_at",
    ]
    return _format_response(items, fields, format, "tableau_alert_fact")


@router.get("/datasets")
def datasets(user=Depends(require_user)):
    if hasattr(user, "status_code"):
        return user

    return {
        "source": "postgresql_live",
        "datasets": [
            {"name": "equipment_master", "path": "/api/tableau/equipment-master?format=csv"},
            {"name": "telemetry_fact", "path": "/api/tableau/telemetry-fact?format=csv"},
            {"name": "inspection_fact", "path": "/api/tableau/inspection-fact?format=csv"},
            {"name": "workflow_fact", "path": "/api/tableau/workflow-fact?format=csv"},
            {"name": "alert_fact", "path": "/api/tableau/alert-fact?format=csv"},
        ],
    }
