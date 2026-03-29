from __future__ import annotations

import math
import os
import random
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.bootstrap import (
    _get_or_create_equipment,
    _get_or_create_equipment_type,
    _get_or_create_place,
    _get_or_create_user,
)
from app.core.telemetry import build_topic, normalize_component_type
from app.models.daily_inspection import DailyInspection
from app.models.di_equipment_log import DIEquipmentLog
from app.models.di_workflow import DIWorkflow
from app.models.equipment import Equipment
from app.models.metadata import EquipmentMetadata
from app.models.role import Role
from app.models.telemetry_alert import TelemetryAlert
from app.models.telemetry_record import TelemetryRecord
from app.models.user import User


@dataclass(slots=True)
class BulkDemoConfig:
    days: int = 90
    samples_per_day: int = 12
    server_racks_per_hall: int = 8
    battery_banks: int = 8
    ups_units: int = 6
    cooling_units: int = 6
    network_devices: int = 4
    inspections_per_day: int = 2
    random_seed: int = 42


def load_bulk_demo_config_from_env() -> BulkDemoConfig:
    return BulkDemoConfig(
        days=int(os.getenv("TABLEAU_DEMO_DAYS", "90")),
        samples_per_day=int(os.getenv("TABLEAU_DEMO_SAMPLES_PER_DAY", "12")),
        server_racks_per_hall=int(os.getenv("TABLEAU_DEMO_SERVER_RACKS_PER_HALL", "8")),
        battery_banks=int(os.getenv("TABLEAU_DEMO_BATTERY_BANKS", "8")),
        ups_units=int(os.getenv("TABLEAU_DEMO_UPS_UNITS", "6")),
        cooling_units=int(os.getenv("TABLEAU_DEMO_COOLING_UNITS", "6")),
        network_devices=int(os.getenv("TABLEAU_DEMO_NETWORK_DEVICES", "4")),
        inspections_per_day=int(os.getenv("TABLEAU_DEMO_INSPECTIONS_PER_DAY", "2")),
        random_seed=int(os.getenv("TABLEAU_DEMO_RANDOM_SEED", "42")),
    )


def _demo_roles(db: Session) -> dict[str, Role]:
    return {
        role.name: role
        for role in db.query(Role).filter(Role.name.in_(["user", "supervisor", "reviewer", "manager"])).all()
    }


def _demo_users(db: Session) -> dict[str, list[User]]:
    users_by_role: dict[str, list[User]] = {
        "user": [],
        "supervisor": [],
        "reviewer": [],
        "manager": [],
    }

    for idx in range(1, 5):
        users_by_role["user"].append(
            _get_or_create_user(db, f"tableau_operator{idx:02d}", "demo123", "user")
        )

    for idx in range(1, 3):
        users_by_role["supervisor"].append(
            _get_or_create_user(db, f"tableau_supervisor{idx:02d}", "demo123", "supervisor")
        )
        users_by_role["reviewer"].append(
            _get_or_create_user(db, f"tableau_reviewer{idx:02d}", "demo123", "reviewer")
        )

    users_by_role["manager"].append(
        _get_or_create_user(db, "tableau_manager01", "demo123", "manager")
    )

    return users_by_role


def _build_demo_equipment(db: Session, config: BulkDemoConfig) -> list[Equipment]:
    hall_names = ["Compute Hall A", "Compute Hall B", "Compute Hall C"]
    halls = [
        _get_or_create_place(db, hall_name, f"Primary compute floor section {hall_name[-1]}")
        for hall_name in hall_names
    ]
    ups_east = _get_or_create_place(db, "UPS Room East", "East power conditioning room")
    ups_west = _get_or_create_place(db, "UPS Room West", "West power conditioning room")
    cooling_1 = _get_or_create_place(db, "Cooling Plant 1", "Primary cooling plant")
    cooling_2 = _get_or_create_place(db, "Cooling Plant 2", "Secondary cooling plant")
    network_core = _get_or_create_place(db, "Network Core", "Core switching and routing area")

    server_type = _get_or_create_equipment_type(db, "server")
    battery_type = _get_or_create_equipment_type(db, "battery")
    ups_type = _get_or_create_equipment_type(db, "ups")
    cooling_type = _get_or_create_equipment_type(db, "cooling")
    network_type = _get_or_create_equipment_type(db, "network")

    equipments: list[Equipment] = []

    for hall_idx, hall in enumerate(halls):
        hall_letter = chr(ord("A") + hall_idx)
        for rack_idx in range(1, config.server_racks_per_hall + 1):
            equipments.append(
                _get_or_create_equipment(
                    db,
                    name=f"Demo Server Rack {hall_letter}{rack_idx:02d}",
                    equipment_type_id=server_type.id,
                    place_id=hall.id,
                    status="On",
                    serviceability="S" if rack_idx % 7 else "U",
                    remarks=f"High-density compute rack in hall {hall_letter}",
                )
            )

    for idx in range(1, config.battery_banks + 1):
        place = ups_east if idx % 2 else ups_west
        equipments.append(
            _get_or_create_equipment(
                db,
                name=f"Demo Battery Bank {idx:02d}",
                equipment_type_id=battery_type.id,
                place_id=place.id,
                status="On",
                serviceability="S",
                remarks="Backup power battery string for critical loads",
            )
        )

    for idx in range(1, config.ups_units + 1):
        place = ups_east if idx % 2 else ups_west
        equipments.append(
            _get_or_create_equipment(
                db,
                name=f"Demo UPS Panel {idx:02d}",
                equipment_type_id=ups_type.id,
                place_id=place.id,
                status="On",
                serviceability="S",
                remarks="UPS distribution panel for rack clusters",
            )
        )

    for idx in range(1, config.cooling_units + 1):
        place = cooling_1 if idx % 2 else cooling_2
        equipments.append(
            _get_or_create_equipment(
                db,
                name=f"Demo Cooling Unit {idx:02d}",
                equipment_type_id=cooling_type.id,
                place_id=place.id,
                status="On" if idx % 3 else "Standby",
                serviceability="S",
                remarks="Cooling unit supporting datacenter air handling",
            )
        )

    for idx in range(1, config.network_devices + 1):
        equipments.append(
            _get_or_create_equipment(
                db,
                name=f"Demo Network Core {idx:02d}",
                equipment_type_id=network_type.id,
                place_id=network_core.id,
                status="On",
                serviceability="S",
                remarks="Core switching fabric for east-west traffic",
            )
        )

    return equipments


def _seed_latest_metadata(db: Session, equipment: Equipment, now: datetime) -> None:
    existing = (
        db.query(EquipmentMetadata)
        .filter(EquipmentMetadata.equipment_id == equipment.id)
        .first()
    )
    if existing:
        return

    component = normalize_component_type(
        equipment.equipment_type.name if equipment.equipment_type else None
    )
    rng = random.Random(f"metadata:{equipment.name}")
    metadata = EquipmentMetadata(
        equipment_id=equipment.id,
        recorded_at=now.replace(tzinfo=None),
        humidity=round(38 + rng.random() * 12, 2),
    )
    if component == "battery":
        metadata.temperature = round(25 + rng.random() * 8, 2)
        metadata.voltage = round(12.2 + rng.random() * 1.6, 2)
    else:
        metadata.temperature = round(20 + rng.random() * 10, 2)
        metadata.voltage = round(224 + rng.random() * 12, 2)
        metadata.frequency = round(49.7 + rng.random() * 0.6, 2)
        metadata.pressure = round(1.1 + rng.random() * 1.0, 2)

    db.add(metadata)


def _bulk_history_exists(db: Session) -> bool:
    cutoff = datetime.now(timezone.utc) - timedelta(days=14)
    return (
        db.query(TelemetryRecord.id)
        .join(Equipment, Equipment.id == TelemetryRecord.equipment_id)
        .filter(Equipment.name.like("Demo %"))
        .filter(TelemetryRecord.created_at < cutoff)
        .first()
        is not None
    )


def _inspection_history_exists(db: Session) -> bool:
    cutoff = date.today() - timedelta(days=14)
    return (
        db.query(DailyInspection.id)
        .join(User, User.id == DailyInspection.created_by)
        .filter(User.username.like("tableau_operator%"))
        .filter(DailyInspection.inspection_date < cutoff)
        .first()
        is not None
    )


def _server_metrics(ts: datetime, rng: random.Random, equipment_name: str) -> tuple[float, float, float, float, bool, str | None]:
    day_fraction = (ts.hour + ts.minute / 60) / 24
    wave = math.sin(day_fraction * math.tau)
    temp = 24.5 + wave * 3.6 + rng.uniform(-1.2, 1.2)
    voltage = 230 + rng.uniform(-5, 5)
    frequency = 50 + rng.uniform(-0.25, 0.25)
    pressure = 1.5 + rng.uniform(-0.35, 0.35)

    anomaly = rng.random() < 0.055
    messages: list[str] = []
    if anomaly:
        temp += rng.choice([-1, 1]) * rng.uniform(8, 14)
        voltage += rng.choice([-1, 1]) * rng.uniform(18, 32)
        frequency += rng.choice([-1, 1]) * rng.uniform(1.0, 2.0)
        pressure += rng.choice([-1, 1]) * rng.uniform(1.0, 1.7)

    if not 18 <= temp <= 32:
        messages.append(f"temperature={temp:.2f}C")
    if not 210 <= voltage <= 240:
        messages.append(f"voltage={voltage:.2f}V")
    if not 49 <= frequency <= 51:
        messages.append(f"frequency={frequency:.2f}Hz")
    if not 0.8 <= pressure <= 2.5:
        messages.append(f"pressure={pressure:.2f}")

    message = None
    if messages:
        message = f"Server anomaly on {equipment_name}: " + ", ".join(messages)

    return (
        round(temp, 2),
        round(voltage, 2),
        round(frequency, 2),
        round(pressure, 2),
        message is not None,
        message,
    )


def _battery_metrics(ts: datetime, rng: random.Random, equipment_name: str) -> tuple[float, float, bool, str | None]:
    day_fraction = (ts.hour + ts.minute / 60) / 24
    wave = math.cos(day_fraction * math.tau)
    temp = 27 + wave * 2.4 + rng.uniform(-0.8, 0.8)
    voltage = 12.9 + rng.uniform(-0.35, 0.35)

    anomaly = rng.random() < 0.07
    messages: list[str] = []
    if anomaly:
        temp += rng.choice([-1, 1]) * rng.uniform(10, 16)
        voltage += rng.choice([-1, 1]) * rng.uniform(1.6, 2.8)

    if not 18 <= temp <= 42:
        messages.append(f"temperature={temp:.2f}C")
    if not 11.8 <= voltage <= 14.8:
        messages.append(f"voltage={voltage:.2f}V")

    message = None
    if messages:
        message = f"Battery anomaly on {equipment_name}: " + ", ".join(messages)

    return round(temp, 2), round(voltage, 2), message is not None, message


def _telemetry_status(equipment: Equipment, ts: datetime, rng: random.Random) -> str:
    base_status = (equipment.status or "On").lower()
    if base_status == "standby":
        return "On" if 8 <= ts.hour < 20 and rng.random() > 0.2 else "Off"
    return "On" if rng.random() > 0.03 else "Off"


def _seed_bulk_telemetry(
    db: Session,
    equipments: list[Equipment],
    config: BulkDemoConfig,
    now_utc: datetime,
) -> int:
    if _bulk_history_exists(db):
        return 0

    step_minutes = max(1, int((24 * 60) / max(config.samples_per_day, 1)))
    start_ts = now_utc - timedelta(days=config.days)
    records: list[TelemetryRecord] = []
    latest_anomalies: dict[int, tuple[datetime, str]] = {}

    for equipment in equipments:
        component_type = normalize_component_type(
            equipment.equipment_type.name if equipment.equipment_type else None
        )
        ts = start_ts
        while ts <= now_utc:
            rng = random.Random(f"{config.random_seed}:{equipment.name}:{ts.isoformat()}")
            status = _telemetry_status(equipment, ts, rng)

            if component_type == "battery":
                temp, voltage, is_anomaly, message = _battery_metrics(ts, rng, equipment.name)
                record = TelemetryRecord(
                    equipment_id=equipment.id,
                    topic=build_topic(component_type, equipment.id),
                    component_type=component_type,
                    status=status,
                    temperature=temp,
                    voltage=voltage,
                    pressure=None,
                    frequency=None,
                    is_anomaly=is_anomaly,
                    anomaly_message=message,
                    created_at=ts,
                )
            else:
                temp, voltage, frequency, pressure, is_anomaly, message = _server_metrics(ts, rng, equipment.name)
                record = TelemetryRecord(
                    equipment_id=equipment.id,
                    topic=build_topic(component_type, equipment.id),
                    component_type=component_type,
                    status=status,
                    temperature=temp,
                    voltage=voltage,
                    pressure=pressure,
                    frequency=frequency,
                    is_anomaly=is_anomaly,
                    anomaly_message=message,
                    created_at=ts,
                )

            records.append(record)
            if is_anomaly and message:
                latest_anomalies[equipment.id] = (ts, message)

            if len(records) >= 2000:
                db.add_all(records)
                db.flush()
                records.clear()

            ts += timedelta(minutes=step_minutes)

    if records:
        db.add_all(records)
        db.flush()

    alerts_to_add: list[TelemetryAlert] = []
    for equipment in equipments:
        latest = latest_anomalies.get(equipment.id)
        if not latest:
            continue
        created_at, message = latest
        alerts_to_add.append(
            TelemetryAlert(
                equipment_id=equipment.id,
                severity="critical",
                title=f"Telemetry anomaly on {equipment.name}",
                message=message,
                is_active=True,
                created_at=created_at,
            )
        )

    if alerts_to_add:
        db.add_all(alerts_to_add)

    return len(equipments) * ((config.days * 24 * 60) // step_minutes + 1)


def _inspection_status(day_offset: int, shift_idx: int, rng: random.Random) -> str:
    if day_offset == 0 and shift_idx == 0:
        return "submitted"
    if day_offset == 0 and shift_idx == 1:
        return "supervisor_approved"
    if day_offset == 1 and shift_idx == 0:
        return "reviewer_approved"
    roll = rng.random()
    if roll < 0.08:
        return "rejected"
    return "completed"


def _inspection_times(inspection_day: date, inspections_per_day: int) -> list[datetime]:
    if inspections_per_day <= 1:
        return [datetime.combine(inspection_day, time(hour=9, minute=0))]
    if inspections_per_day == 2:
        return [
            datetime.combine(inspection_day, time(hour=8, minute=30)),
            datetime.combine(inspection_day, time(hour=20, minute=30)),
        ]

    slots: list[datetime] = []
    for idx in range(inspections_per_day):
        hour = (24 // inspections_per_day) * idx
        slots.append(datetime.combine(inspection_day, time(hour=hour, minute=30)))
    return slots


def _seed_bulk_inspections(
    db: Session,
    equipments: list[Equipment],
    users_by_role: dict[str, list[User]],
    config: BulkDemoConfig,
) -> int:
    if _inspection_history_exists(db):
        return 0

    created = 0
    operators = users_by_role["user"]
    supervisors = users_by_role["supervisor"]
    reviewers = users_by_role["reviewer"]
    managers = users_by_role["manager"]

    for day_offset in range(config.days, -1, -1):
        inspection_day = date.today() - timedelta(days=day_offset)
        for shift_idx, created_at in enumerate(_inspection_times(inspection_day, config.inspections_per_day)):
            rng = random.Random(f"inspection:{config.random_seed}:{inspection_day.isoformat()}:{shift_idx}")
            operator = operators[(day_offset + shift_idx) % len(operators)]
            status = _inspection_status(day_offset, shift_idx, rng)
            inspection = DailyInspection(
                inspection_date=inspection_day,
                created_by=operator.id,
                status=status,
                created_at=created_at,
            )
            db.add(inspection)
            db.flush()

            for equipment in equipments:
                equipment_rng = random.Random(
                    f"log:{config.random_seed}:{inspection_day.isoformat()}:{shift_idx}:{equipment.name}"
                )
                serviceability = "U" if equipment_rng.random() < 0.08 else "S"
                remark_templates = {
                    "S": [
                        "Routine inspection passed",
                        "Operating within expected limits",
                        "No actionable issues identified",
                    ],
                    "U": [
                        "Observed variance requiring monitoring",
                        "Flagged for maintenance review",
                        "Condition outside preferred threshold",
                    ],
                }
                db.add(
                    DIEquipmentLog(
                        di_id=inspection.id,
                        equipment_id=equipment.id,
                        serviceability=serviceability,
                        remarks=equipment_rng.choice(remark_templates[serviceability]),
                    )
                )

            if status in {"supervisor_approved", "reviewer_approved", "completed", "rejected"}:
                supervisor = supervisors[(day_offset + shift_idx) % len(supervisors)]
                db.add(
                    DIWorkflow(
                        di_id=inspection.id,
                        from_role="supervisor",
                        to_role="reviewer" if status != "rejected" else "creator",
                        action="rejected" if status == "rejected" else "approved",
                        comments="Supervisor reviewed inspection package",
                        acted_by=supervisor.id,
                        acted_at=created_at + timedelta(hours=1),
                    )
                )

            if status in {"reviewer_approved", "completed"}:
                reviewer = reviewers[(day_offset + shift_idx) % len(reviewers)]
                db.add(
                    DIWorkflow(
                        di_id=inspection.id,
                        from_role="reviewer",
                        to_role="manager",
                        action="approved",
                        comments="Reviewer validated findings and measurements",
                        acted_by=reviewer.id,
                        acted_at=created_at + timedelta(hours=2),
                    )
                )

            if status == "completed":
                manager = managers[0]
                db.add(
                    DIWorkflow(
                        di_id=inspection.id,
                        from_role="manager",
                        to_role="completed",
                        action="approved",
                        comments="Manager closed the inspection successfully",
                        acted_by=manager.id,
                        acted_at=created_at + timedelta(hours=3),
                    )
                )

            created += 1

            if created % 20 == 0:
                db.flush()

    return created


def seed_bulk_demo_data(db: Session, config: BulkDemoConfig | None = None) -> dict[str, int]:
    config = config or load_bulk_demo_config_from_env()
    now_utc = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)

    users_by_role = _demo_users(db)
    equipments = _build_demo_equipment(db, config)
    for equipment in equipments:
        _seed_latest_metadata(db, equipment, now_utc)

    inspections_created = _seed_bulk_inspections(db, equipments, users_by_role, config)
    telemetry_created = _seed_bulk_telemetry(db, equipments, config, now_utc)
    db.commit()

    return {
        "days": config.days,
        "samples_per_day": config.samples_per_day,
        "equipments": len(equipments),
        "inspections_created": inspections_created,
        "telemetry_rows_created": telemetry_created,
    }
