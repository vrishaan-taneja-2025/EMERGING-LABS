import argparse
import csv
import json
from datetime import date, datetime
from pathlib import Path
from typing import Iterable

import app.models  # noqa: F401
from sqlalchemy.orm import joinedload

from app.db.session import SessionLocal
from app.models.daily_inspection import DailyInspection
from app.models.di_equipment_log import DIEquipmentLog
from app.models.di_workflow import DIWorkflow
from app.models.equipment import Equipment
from app.models.equipment_type import EquipmentType
from app.models.metadata import EquipmentMetadata
from app.models.place import Place
from app.models.role import Role
from app.models.telemetry_alert import TelemetryAlert
from app.models.telemetry_record import TelemetryRecord
from app.models.user import User


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export raw and Tableau-friendly CSV datasets from the app database."
    )
    parser.add_argument(
        "--output-dir",
        default="exports/tableau",
        help="Directory where CSV files will be written.",
    )
    return parser.parse_args()


def _serialize_value(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if value is None:
        return ""
    return value


def write_csv(path: Path, rows: Iterable[dict], fieldnames: list[str]) -> int:
    count = 0
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _serialize_value(row.get(key)) for key in fieldnames})
            count += 1
    return count


def export_raw_tables(db, output_dir: Path) -> dict[str, int]:
    counts: dict[str, int] = {}

    roles = db.query(Role).order_by(Role.id.asc()).all()
    counts["raw_roles.csv"] = write_csv(
        output_dir / "raw_roles.csv",
        ({"id": role.id, "name": role.name} for role in roles),
        ["id", "name"],
    )

    users = (
        db.query(User)
        .options(joinedload(User.role))
        .order_by(User.id.asc())
        .all()
    )
    counts["raw_users.csv"] = write_csv(
        output_dir / "raw_users.csv",
        (
            {
                "id": user.id,
                "username": user.username,
                "role_id": user.role_id,
                "role_name": user.role.name if user.role else "",
                "is_active": user.is_active,
                "created_at": user.created_at,
            }
            for user in users
        ),
        ["id", "username", "role_id", "role_name", "is_active", "created_at"],
    )

    places = db.query(Place).order_by(Place.id.asc()).all()
    counts["raw_places.csv"] = write_csv(
        output_dir / "raw_places.csv",
        (
            {
                "id": place.id,
                "name": place.name,
                "description": place.description,
            }
            for place in places
        ),
        ["id", "name", "description"],
    )

    equipment_types = db.query(EquipmentType).order_by(EquipmentType.id.asc()).all()
    counts["raw_equipment_types.csv"] = write_csv(
        output_dir / "raw_equipment_types.csv",
        (
            {
                "id": equipment_type.id,
                "name": equipment_type.name,
            }
            for equipment_type in equipment_types
        ),
        ["id", "name"],
    )

    equipments = (
        db.query(Equipment)
        .options(joinedload(Equipment.place), joinedload(Equipment.equipment_type))
        .order_by(Equipment.id.asc())
        .all()
    )
    counts["raw_equipments.csv"] = write_csv(
        output_dir / "raw_equipments.csv",
        (
            {
                "id": equipment.id,
                "name": equipment.name,
                "equipment_type_id": equipment.equipment_type_id,
                "equipment_type_name": equipment.equipment_type.name if equipment.equipment_type else "",
                "place_id": equipment.place_id,
                "place_name": equipment.place.name if equipment.place else "",
                "status": equipment.status,
                "serviceability": equipment.serviceability,
                "remarks": equipment.remarks,
                "created_at": equipment.created_at,
            }
            for equipment in equipments
        ),
        [
            "id",
            "name",
            "equipment_type_id",
            "equipment_type_name",
            "place_id",
            "place_name",
            "status",
            "serviceability",
            "remarks",
            "created_at",
        ],
    )

    metadata_rows = (
        db.query(EquipmentMetadata)
        .order_by(EquipmentMetadata.id.asc())
        .all()
    )
    counts["raw_equipment_metadata.csv"] = write_csv(
        output_dir / "raw_equipment_metadata.csv",
        (
            {
                "id": metadata.id,
                "equipment_id": metadata.equipment_id,
                "pressure": metadata.pressure,
                "temperature": metadata.temperature,
                "humidity": metadata.humidity,
                "frequency": metadata.frequency,
                "voltage": metadata.voltage,
                "recorded_at": metadata.recorded_at,
            }
            for metadata in metadata_rows
        ),
        [
            "id",
            "equipment_id",
            "pressure",
            "temperature",
            "humidity",
            "frequency",
            "voltage",
            "recorded_at",
        ],
    )

    inspections = (
        db.query(DailyInspection)
        .options(joinedload(DailyInspection.user))
        .order_by(DailyInspection.id.asc())
        .all()
    )
    counts["raw_daily_inspections.csv"] = write_csv(
        output_dir / "raw_daily_inspections.csv",
        (
            {
                "id": inspection.id,
                "inspection_date": inspection.inspection_date,
                "created_by": inspection.created_by,
                "created_by_username": inspection.user.username if inspection.user else "",
                "status": inspection.status,
                "created_at": inspection.created_at,
            }
            for inspection in inspections
        ),
        ["id", "inspection_date", "created_by", "created_by_username", "status", "created_at"],
    )

    di_logs = db.query(DIEquipmentLog).order_by(DIEquipmentLog.id.asc()).all()
    counts["raw_di_equipment_logs.csv"] = write_csv(
        output_dir / "raw_di_equipment_logs.csv",
        (
            {
                "id": log.id,
                "di_id": log.di_id,
                "equipment_id": log.equipment_id,
                "serviceability": log.serviceability,
                "remarks": log.remarks,
            }
            for log in di_logs
        ),
        ["id", "di_id", "equipment_id", "serviceability", "remarks"],
    )

    workflows = db.query(DIWorkflow).order_by(DIWorkflow.id.asc()).all()
    counts["raw_di_workflow.csv"] = write_csv(
        output_dir / "raw_di_workflow.csv",
        (
            {
                "id": workflow.id,
                "di_id": workflow.di_id,
                "from_role": workflow.from_role,
                "to_role": workflow.to_role,
                "action": workflow.action,
                "comments": workflow.comments,
                "acted_by": workflow.acted_by,
                "acted_at": workflow.acted_at,
            }
            for workflow in workflows
        ),
        ["id", "di_id", "from_role", "to_role", "action", "comments", "acted_by", "acted_at"],
    )

    telemetry_records = (
        db.query(TelemetryRecord)
        .order_by(TelemetryRecord.id.asc())
        .all()
    )
    counts["raw_telemetry_records.csv"] = write_csv(
        output_dir / "raw_telemetry_records.csv",
        (
            {
                "id": record.id,
                "equipment_id": record.equipment_id,
                "topic": record.topic,
                "component_type": record.component_type,
                "status": record.status,
                "temperature": record.temperature,
                "voltage": record.voltage,
                "pressure": record.pressure,
                "frequency": record.frequency,
                "is_anomaly": record.is_anomaly,
                "anomaly_message": record.anomaly_message,
                "created_at": record.created_at,
            }
            for record in telemetry_records
        ),
        [
            "id",
            "equipment_id",
            "topic",
            "component_type",
            "status",
            "temperature",
            "voltage",
            "pressure",
            "frequency",
            "is_anomaly",
            "anomaly_message",
            "created_at",
        ],
    )

    alerts = db.query(TelemetryAlert).order_by(TelemetryAlert.id.asc()).all()
    counts["raw_telemetry_alerts.csv"] = write_csv(
        output_dir / "raw_telemetry_alerts.csv",
        (
            {
                "id": alert.id,
                "equipment_id": alert.equipment_id,
                "severity": alert.severity,
                "title": alert.title,
                "message": alert.message,
                "is_active": alert.is_active,
                "created_at": alert.created_at,
            }
            for alert in alerts
        ),
        ["id", "equipment_id", "severity", "title", "message", "is_active", "created_at"],
    )

    return counts


def export_tableau_tables(db, output_dir: Path) -> dict[str, int]:
    counts: dict[str, int] = {}

    equipments = (
        db.query(Equipment)
        .options(joinedload(Equipment.place), joinedload(Equipment.equipment_type))
        .order_by(Equipment.id.asc())
        .all()
    )
    latest_metadata_by_equipment: dict[int, EquipmentMetadata] = {}
    for metadata in (
        db.query(EquipmentMetadata)
        .order_by(EquipmentMetadata.equipment_id.asc(), EquipmentMetadata.recorded_at.desc())
        .all()
    ):
        latest_metadata_by_equipment.setdefault(metadata.equipment_id, metadata)

    counts["tableau_equipment_master.csv"] = write_csv(
        output_dir / "tableau_equipment_master.csv",
        (
            {
                "equipment_id": equipment.id,
                "equipment_name": equipment.name,
                "equipment_type": equipment.equipment_type.name if equipment.equipment_type else "",
                "place": equipment.place.name if equipment.place else "",
                "place_description": equipment.place.description if equipment.place else "",
                "equipment_status": equipment.status,
                "serviceability": equipment.serviceability,
                "remarks": equipment.remarks,
                "latest_temperature": latest_metadata_by_equipment.get(equipment.id).temperature if latest_metadata_by_equipment.get(equipment.id) else "",
                "latest_voltage": latest_metadata_by_equipment.get(equipment.id).voltage if latest_metadata_by_equipment.get(equipment.id) else "",
                "latest_pressure": latest_metadata_by_equipment.get(equipment.id).pressure if latest_metadata_by_equipment.get(equipment.id) else "",
                "latest_frequency": latest_metadata_by_equipment.get(equipment.id).frequency if latest_metadata_by_equipment.get(equipment.id) else "",
                "latest_humidity": latest_metadata_by_equipment.get(equipment.id).humidity if latest_metadata_by_equipment.get(equipment.id) else "",
                "latest_recorded_at": latest_metadata_by_equipment.get(equipment.id).recorded_at if latest_metadata_by_equipment.get(equipment.id) else "",
            }
            for equipment in equipments
        ),
        [
            "equipment_id",
            "equipment_name",
            "equipment_type",
            "place",
            "place_description",
            "equipment_status",
            "serviceability",
            "remarks",
            "latest_temperature",
            "latest_voltage",
            "latest_pressure",
            "latest_frequency",
            "latest_humidity",
            "latest_recorded_at",
        ],
    )

    equipment_by_id = {equipment.id: equipment for equipment in equipments}
    counts["tableau_telemetry_fact.csv"] = write_csv(
        output_dir / "tableau_telemetry_fact.csv",
        (
            {
                "telemetry_id": record.id,
                "created_at": record.created_at,
                "equipment_id": record.equipment_id,
                "equipment_name": equipment_by_id[record.equipment_id].name if record.equipment_id in equipment_by_id else "",
                "equipment_type": equipment_by_id[record.equipment_id].equipment_type.name if record.equipment_id in equipment_by_id and equipment_by_id[record.equipment_id].equipment_type else "",
                "place": equipment_by_id[record.equipment_id].place.name if record.equipment_id in equipment_by_id and equipment_by_id[record.equipment_id].place else "",
                "topic": record.topic,
                "component_type": record.component_type,
                "status": record.status,
                "temperature": record.temperature,
                "voltage": record.voltage,
                "pressure": record.pressure,
                "frequency": record.frequency,
                "is_anomaly": record.is_anomaly,
                "anomaly_message": record.anomaly_message,
            }
            for record in db.query(TelemetryRecord).order_by(TelemetryRecord.id.asc()).yield_per(2000)
        ),
        [
            "telemetry_id",
            "created_at",
            "equipment_id",
            "equipment_name",
            "equipment_type",
            "place",
            "topic",
            "component_type",
            "status",
            "temperature",
            "voltage",
            "pressure",
            "frequency",
            "is_anomaly",
            "anomaly_message",
        ],
    )

    inspections = (
        db.query(DailyInspection)
        .options(joinedload(DailyInspection.user))
        .order_by(DailyInspection.id.asc())
        .all()
    )
    inspections_by_id = {inspection.id: inspection for inspection in inspections}
    counts["tableau_inspection_fact.csv"] = write_csv(
        output_dir / "tableau_inspection_fact.csv",
        (
            {
                "di_log_id": log.id,
                "inspection_id": log.di_id,
                "inspection_date": inspections_by_id[log.di_id].inspection_date if log.di_id in inspections_by_id else "",
                "inspection_status": inspections_by_id[log.di_id].status if log.di_id in inspections_by_id else "",
                "inspection_created_at": inspections_by_id[log.di_id].created_at if log.di_id in inspections_by_id else "",
                "created_by_user_id": inspections_by_id[log.di_id].created_by if log.di_id in inspections_by_id else "",
                "created_by_username": inspections_by_id[log.di_id].user.username if log.di_id in inspections_by_id and inspections_by_id[log.di_id].user else "",
                "equipment_id": log.equipment_id,
                "equipment_name": equipment_by_id[log.equipment_id].name if log.equipment_id in equipment_by_id else "",
                "equipment_type": equipment_by_id[log.equipment_id].equipment_type.name if log.equipment_id in equipment_by_id and equipment_by_id[log.equipment_id].equipment_type else "",
                "place": equipment_by_id[log.equipment_id].place.name if log.equipment_id in equipment_by_id and equipment_by_id[log.equipment_id].place else "",
                "serviceability": log.serviceability,
                "remarks": log.remarks,
            }
            for log in db.query(DIEquipmentLog).order_by(DIEquipmentLog.id.asc()).yield_per(2000)
        ),
        [
            "di_log_id",
            "inspection_id",
            "inspection_date",
            "inspection_status",
            "inspection_created_at",
            "created_by_user_id",
            "created_by_username",
            "equipment_id",
            "equipment_name",
            "equipment_type",
            "place",
            "serviceability",
            "remarks",
        ],
    )

    users_by_id = {user.id: user for user in db.query(User).options(joinedload(User.role)).all()}
    counts["tableau_workflow_fact.csv"] = write_csv(
        output_dir / "tableau_workflow_fact.csv",
        (
            {
                "workflow_id": workflow.id,
                "inspection_id": workflow.di_id,
                "inspection_date": inspections_by_id[workflow.di_id].inspection_date if workflow.di_id in inspections_by_id else "",
                "inspection_status": inspections_by_id[workflow.di_id].status if workflow.di_id in inspections_by_id else "",
                "from_role": workflow.from_role,
                "to_role": workflow.to_role,
                "action": workflow.action,
                "comments": workflow.comments,
                "acted_by_user_id": workflow.acted_by,
                "acted_by_username": users_by_id[workflow.acted_by].username if workflow.acted_by in users_by_id else "",
                "acted_by_role": users_by_id[workflow.acted_by].role.name if workflow.acted_by in users_by_id and users_by_id[workflow.acted_by].role else "",
                "acted_at": workflow.acted_at,
            }
            for workflow in db.query(DIWorkflow).order_by(DIWorkflow.id.asc()).yield_per(2000)
        ),
        [
            "workflow_id",
            "inspection_id",
            "inspection_date",
            "inspection_status",
            "from_role",
            "to_role",
            "action",
            "comments",
            "acted_by_user_id",
            "acted_by_username",
            "acted_by_role",
            "acted_at",
        ],
    )

    counts["tableau_alert_fact.csv"] = write_csv(
        output_dir / "tableau_alert_fact.csv",
        (
            {
                "alert_id": alert.id,
                "created_at": alert.created_at,
                "equipment_id": alert.equipment_id,
                "equipment_name": equipment_by_id[alert.equipment_id].name if alert.equipment_id in equipment_by_id else "",
                "equipment_type": equipment_by_id[alert.equipment_id].equipment_type.name if alert.equipment_id in equipment_by_id and equipment_by_id[alert.equipment_id].equipment_type else "",
                "place": equipment_by_id[alert.equipment_id].place.name if alert.equipment_id in equipment_by_id and equipment_by_id[alert.equipment_id].place else "",
                "severity": alert.severity,
                "title": alert.title,
                "message": alert.message,
                "is_active": alert.is_active,
            }
            for alert in db.query(TelemetryAlert).order_by(TelemetryAlert.id.asc()).yield_per(2000)
        ),
        [
            "alert_id",
            "created_at",
            "equipment_id",
            "equipment_name",
            "equipment_type",
            "place",
            "severity",
            "title",
            "message",
            "is_active",
        ],
    )

    return counts


def write_manifest(output_dir: Path, counts: dict[str, int]) -> None:
    manifest_path = output_dir / "export_manifest.json"
    payload = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "files": counts,
    }
    with manifest_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    db = SessionLocal()
    try:
        counts = {}
        counts.update(export_raw_tables(db, output_dir))
        counts.update(export_tableau_tables(db, output_dir))
        write_manifest(output_dir, counts)
    finally:
        db.close()

    print(f"CSV export completed in {output_dir}")
    for name, count in sorted(counts.items()):
        print(f"{name}: {count}")


if __name__ == "__main__":
    main()
