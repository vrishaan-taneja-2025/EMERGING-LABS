import os
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.core.security import hash_password
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


def _get_or_create_role(db: Session, name: str) -> Role:
    role = db.query(Role).filter(Role.name == name).first()
    if role:
        return role

    role = Role(name=name)
    db.add(role)
    db.flush()
    return role


def ensure_default_auth_data(db: Session) -> None:
    # Keep auth bootstrap idempotent so startup is safe on every restart.
    admin_role = _get_or_create_role(db, "admin")
    _get_or_create_role(db, "user")
    _get_or_create_role(db, "supervisor")
    _get_or_create_role(db, "reviewer")
    _get_or_create_role(db, "manager")

    admin_username = os.getenv("DEFAULT_ADMIN_USERNAME", "admin")
    admin_password = os.getenv("DEFAULT_ADMIN_PASSWORD", "admin123")

    admin_user = db.query(User).filter(User.username == admin_username).first()
    if not admin_user:
        admin_user = User(
            username=admin_username,
            password_hash=hash_password(admin_password),
            role_id=admin_role.id,
            is_active=True,
        )
        db.add(admin_user)

    db.commit()


def _get_or_create_place(db: Session, name: str, description: str) -> Place:
    place = db.query(Place).filter(Place.name == name).first()
    if place:
        return place
    place = Place(name=name, description=description)
    db.add(place)
    db.flush()
    return place


def _get_or_create_equipment_type(db: Session, name: str) -> EquipmentType:
    equipment_type = db.query(EquipmentType).filter(EquipmentType.name == name).first()
    if equipment_type:
        return equipment_type
    equipment_type = EquipmentType(name=name)
    db.add(equipment_type)
    db.flush()
    return equipment_type


def _get_or_create_equipment(
    db: Session,
    *,
    name: str,
    equipment_type_id: int,
    place_id: int,
    status: str,
    serviceability: str = "S",
    remarks: str,
) -> Equipment:
    equipment = db.query(Equipment).filter(Equipment.name == name).first()
    if equipment:
        return equipment
    equipment = Equipment(
        name=name,
        equipment_type_id=equipment_type_id,
        place_id=place_id,
        status=status,
        serviceability=serviceability,
        remarks=remarks,
    )
    db.add(equipment)
    db.flush()
    return equipment


def _get_user_by_role(db: Session, role_name: str) -> User | None:
    return (
        db.query(User)
        .join(Role, Role.id == User.role_id)
        .filter(Role.name == role_name)
        .order_by(User.id.asc())
        .first()
    )


def _get_or_create_user(db: Session, username: str, password: str, role_name: str) -> User:
    user = db.query(User).filter(User.username == username).first()
    if user:
        return user

    role = db.query(Role).filter(Role.name == role_name).first()
    if not role:
        raise ValueError(f"Role {role_name!r} must exist before seeding users")

    user = User(
        username=username,
        password_hash=hash_password(password),
        role_id=role.id,
        is_active=True,
    )
    db.add(user)
    db.flush()
    return user


def _seed_equipment_metadata(
    db: Session,
    equipment: Equipment,
    *,
    pressure: float | None = None,
    temperature: float | None = None,
    humidity: float | None = None,
    voltage: float | None = None,
    frequency: float | None = None,
) -> None:
    existing = (
        db.query(EquipmentMetadata)
        .filter(EquipmentMetadata.equipment_id == equipment.id)
        .first()
    )
    if existing:
        return

    db.add(
        EquipmentMetadata(
            equipment_id=equipment.id,
            pressure=pressure,
            temperature=temperature,
            humidity=humidity,
            voltage=voltage,
            frequency=frequency,
        )
    )


def _seed_demo_daily_inspections(db: Session, equipments: list[Equipment]) -> None:
    if db.query(DailyInspection).first():
        return

    operator = db.query(User).filter(User.username == "operator").first() or _get_user_by_role(db, "user")
    supervisor = db.query(User).filter(User.username == "supervisor1").first() or _get_user_by_role(db, "supervisor")
    reviewer = db.query(User).filter(User.username == "reviewer1").first() or _get_user_by_role(db, "reviewer")
    manager = db.query(User).filter(User.username == "manager1").first() or _get_user_by_role(db, "manager")

    if not operator:
        return

    today = date.today()

    inspection_specs = [
        {
            "inspection_date": today - timedelta(days=2),
            "status": "completed",
            "logs": [
                ("Battery Bank A", "S", "Voltage stable and terminals cleaned"),
                ("Server Rack A", "S", "Airflow normal and load balanced"),
                ("UPS Panel 1", "S", "Output healthy during routine check"),
            ],
            "workflow": [
                ("supervisor", "reviewer", "approved", "All critical readings within range", supervisor),
                ("reviewer", "manager", "approved", "Inspection data validated", reviewer),
                ("manager", "completed", "approved", "Closed for operations", manager),
            ],
        },
        {
            "inspection_date": today - timedelta(days=1),
            "status": "supervisor_approved",
            "logs": [
                ("Battery Bank B", "S", "Battery strings balanced"),
                ("Cooling Unit 1", "U", "Cooling delta slightly elevated, observe next shift"),
                ("Server Rack B", "S", "No alarm indicators present"),
            ],
            "workflow": [
                ("supervisor", "reviewer", "approved", "Forwarded with cooling observation", supervisor),
            ],
        },
        {
            "inspection_date": today,
            "status": "submitted",
            "logs": [
                ("Server Rack A", "S", "Morning inspection completed"),
                ("Cooling Unit 2", "S", "Fans clear and responding"),
                ("UPS Panel 1", "S", "Input and bypass indicators normal"),
            ],
            "workflow": [],
        },
    ]

    equipment_by_name = {equipment.name: equipment for equipment in equipments}

    for spec in inspection_specs:
        inspection = DailyInspection(
            inspection_date=spec["inspection_date"],
            created_by=operator.id,
            status=spec["status"],
        )
        db.add(inspection)
        db.flush()

        for equipment_name, serviceability, remarks in spec["logs"]:
            equipment = equipment_by_name.get(equipment_name)
            if not equipment:
                continue
            db.add(
                DIEquipmentLog(
                    di_id=inspection.id,
                    equipment_id=equipment.id,
                    serviceability=serviceability,
                    remarks=remarks,
                )
            )

        for from_role, to_role, action, comments, actor in spec["workflow"]:
            if actor is None:
                continue
            db.add(
                DIWorkflow(
                    di_id=inspection.id,
                    from_role=from_role,
                    to_role=to_role,
                    action=action,
                    comments=comments,
                    acted_by=actor.id,
                )
            )


def _seed_demo_telemetry(db: Session, equipments: list[Equipment]) -> None:
    if db.query(TelemetryRecord).first():
        return

    telemetry_specs = {
        "Battery Bank A": {
            "component_type": "battery",
            "status": "On",
            "temperature": 27.4,
            "voltage": 12.9,
            "pressure": None,
            "frequency": None,
            "is_anomaly": False,
            "anomaly_message": None,
        },
        "Battery Bank B": {
            "component_type": "battery",
            "status": "On",
            "temperature": 45.6,
            "voltage": 15.4,
            "pressure": None,
            "frequency": None,
            "is_anomaly": True,
            "anomaly_message": "Battery anomaly: voltage=15.40V, temperature=45.60C",
        },
        "Server Rack A": {
            "component_type": "server",
            "status": "On",
            "temperature": 24.3,
            "voltage": 229.6,
            "pressure": 1.5,
            "frequency": 50.0,
            "is_anomaly": False,
            "anomaly_message": None,
        },
        "Server Rack B": {
            "component_type": "server",
            "status": "On",
            "temperature": 34.8,
            "voltage": 246.2,
            "pressure": 2.8,
            "frequency": 48.5,
            "is_anomaly": True,
            "anomaly_message": "Server anomaly: temperature=34.80C, voltage=246.20V, frequency=48.50Hz, pressure=2.80",
        },
        "UPS Panel 1": {
            "component_type": "server",
            "status": "On",
            "temperature": 26.1,
            "voltage": 231.0,
            "pressure": 1.2,
            "frequency": 50.1,
            "is_anomaly": False,
            "anomaly_message": None,
        },
        "Cooling Unit 1": {
            "component_type": "server",
            "status": "On",
            "temperature": 31.8,
            "voltage": 228.4,
            "pressure": 2.0,
            "frequency": 49.9,
            "is_anomaly": False,
            "anomaly_message": None,
        },
    }

    for equipment in equipments:
        spec = telemetry_specs.get(equipment.name)
        if not spec:
            continue

        topic_component = "battery" if spec["component_type"] == "battery" else "server"
        db.add(
            TelemetryRecord(
                equipment_id=equipment.id,
                topic=f"telemetry/{topic_component}/{equipment.id}",
                component_type=spec["component_type"],
                status=spec["status"],
                temperature=spec["temperature"],
                voltage=spec["voltage"],
                pressure=spec["pressure"],
                frequency=spec["frequency"],
                is_anomaly=spec["is_anomaly"],
                anomaly_message=spec["anomaly_message"],
            )
        )

        if spec["is_anomaly"]:
            existing_alert = (
                db.query(TelemetryAlert)
                .filter(TelemetryAlert.equipment_id == equipment.id, TelemetryAlert.is_active.is_(True))
                .first()
            )
            if not existing_alert:
                db.add(
                    TelemetryAlert(
                        equipment_id=equipment.id,
                        severity="critical",
                        title=f"Telemetry anomaly on {equipment.name}",
                        message=spec["anomaly_message"],
                        is_active=True,
                    )
                )


def ensure_demo_data(db: Session) -> None:
    if os.getenv("ENABLE_DEMO_DATA", "true").strip().lower() in {"0", "false", "no"}:
        return

    _get_or_create_user(db, "operator", "operator123", "user")
    _get_or_create_user(db, "supervisor1", "supervisor123", "supervisor")
    _get_or_create_user(db, "reviewer1", "reviewer123", "reviewer")
    _get_or_create_user(db, "manager1", "manager123", "manager")

    main_hall = _get_or_create_place(db, "Main Data Hall", "Primary compute hall for demo workloads")
    ups_room = _get_or_create_place(db, "UPS Room", "Power conditioning and battery backup area")
    cooling_bay = _get_or_create_place(db, "Cooling Bay", "Environmental control and CRAC servicing zone")

    battery_type = _get_or_create_equipment_type(db, "battery")
    server_type = _get_or_create_equipment_type(db, "server")
    ups_type = _get_or_create_equipment_type(db, "ups")
    cooling_type = _get_or_create_equipment_type(db, "cooling")

    equipments = [
        _get_or_create_equipment(
            db,
            name="Battery Bank A",
            equipment_type_id=battery_type.id,
            place_id=ups_room.id,
            status="On",
            serviceability="S",
            remarks="Primary backup battery string for Row A",
        ),
        _get_or_create_equipment(
            db,
            name="Battery Bank B",
            equipment_type_id=battery_type.id,
            place_id=ups_room.id,
            status="On",
            serviceability="S",
            remarks="Secondary battery string under observation",
        ),
        _get_or_create_equipment(
            db,
            name="Server Rack A",
            equipment_type_id=server_type.id,
            place_id=main_hall.id,
            status="On",
            serviceability="S",
            remarks="Customer cluster rack with normal operating load",
        ),
        _get_or_create_equipment(
            db,
            name="Server Rack B",
            equipment_type_id=server_type.id,
            place_id=main_hall.id,
            status="On",
            serviceability="U",
            remarks="Intermittent thermal deviation observed in recent checks",
        ),
        _get_or_create_equipment(
            db,
            name="UPS Panel 1",
            equipment_type_id=ups_type.id,
            place_id=ups_room.id,
            status="On",
            serviceability="S",
            remarks="Feeds compute hall power distribution",
        ),
        _get_or_create_equipment(
            db,
            name="Cooling Unit 1",
            equipment_type_id=cooling_type.id,
            place_id=cooling_bay.id,
            status="On",
            serviceability="S",
            remarks="Primary CRAC unit for the main hall",
        ),
        _get_or_create_equipment(
            db,
            name="Cooling Unit 2",
            equipment_type_id=cooling_type.id,
            place_id=cooling_bay.id,
            status="Standby",
            serviceability="S",
            remarks="Standby unit available for peak cooling demand",
        ),
    ]

    metadata_specs = {
        "Battery Bank A": {"temperature": 27.4, "voltage": 12.9, "humidity": 44.0},
        "Battery Bank B": {"temperature": 30.8, "voltage": 13.3, "humidity": 46.0},
        "Server Rack A": {"temperature": 24.3, "voltage": 229.6, "pressure": 1.5, "frequency": 50.0, "humidity": 43.0},
        "Server Rack B": {"temperature": 29.7, "voltage": 233.1, "pressure": 1.8, "frequency": 49.9, "humidity": 47.0},
        "UPS Panel 1": {"temperature": 26.1, "voltage": 231.0, "frequency": 50.1, "humidity": 42.0},
        "Cooling Unit 1": {"temperature": 20.5, "pressure": 2.0, "frequency": 49.9, "humidity": 39.0},
        "Cooling Unit 2": {"temperature": 19.8, "pressure": 1.7, "frequency": 50.0, "humidity": 38.0},
    }

    for equipment in equipments:
        _seed_equipment_metadata(db, equipment, **metadata_specs.get(equipment.name, {}))

    _seed_demo_daily_inspections(db, equipments)
    _seed_demo_telemetry(db, equipments)
    db.commit()


def ensure_default_telemetry_entities(db: Session) -> None:
    place = _get_or_create_place(db, "Main Data Hall", "Default telemetry demo location")
    battery_type = _get_or_create_equipment_type(db, "battery")
    server_type = _get_or_create_equipment_type(db, "server")

    _get_or_create_equipment(
        db,
        name="Battery Bank A",
        equipment_type_id=battery_type.id,
        place_id=place.id,
        status="On",
        serviceability="S",
        remarks="Auto-seeded telemetry demo battery",
    )
    _get_or_create_equipment(
        db,
        name="Server Rack A",
        equipment_type_id=server_type.id,
        place_id=place.id,
        status="On",
        serviceability="S",
        remarks="Auto-seeded telemetry demo server",
    )
    db.commit()
