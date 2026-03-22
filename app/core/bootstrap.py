import os

from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.equipment import Equipment
from app.models.equipment_type import EquipmentType
from app.models.place import Place
from app.models.role import Role
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
        serviceability="S",
        remarks=remarks,
    )
    db.add(equipment)
    db.flush()
    return equipment


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
        remarks="Auto-seeded telemetry demo battery",
    )
    _get_or_create_equipment(
        db,
        name="Server Rack A",
        equipment_type_id=server_type.id,
        place_id=place.id,
        status="On",
        remarks="Auto-seeded telemetry demo server",
    )
    db.commit()
