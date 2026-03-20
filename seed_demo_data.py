import app.models  # noqa: F401

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.equipment import Equipment
from app.models.equipment_type import EquipmentType
from app.models.place import Place
from app.models.role import Role
from app.models.user import User


def get_or_create_role(db, name: str):
    role = db.query(Role).filter(Role.name == name).first()
    if not role:
        role = Role(name=name)
        db.add(role)
        db.commit()
        db.refresh(role)
    return role


def get_or_create_user(db, username: str, password: str, role: Role):
    user = db.query(User).filter(User.username == username).first()
    if not user:
        user = User(
            username=username,
            password_hash=hash_password(password),
            role_id=role.id,
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def get_or_create_place(db, name: str, description: str):
    place = db.query(Place).filter(Place.name == name).first()
    if not place:
        place = Place(name=name, description=description)
        db.add(place)
        db.commit()
        db.refresh(place)
    return place


def get_or_create_equipment_type(db, name: str):
    equipment_type = db.query(EquipmentType).filter(EquipmentType.name == name).first()
    if not equipment_type:
        equipment_type = EquipmentType(name=name)
        db.add(equipment_type)
        db.commit()
        db.refresh(equipment_type)
    return equipment_type


def get_or_create_equipment(db, *, name: str, equipment_type_id: int, place_id: int, status: str, remarks: str):
    equipment = db.query(Equipment).filter(Equipment.name == name).first()
    if not equipment:
        equipment = Equipment(
            name=name,
            equipment_type_id=equipment_type_id,
            place_id=place_id,
            status=status,
            serviceability="S",
            remarks=remarks,
        )
        db.add(equipment)
        db.commit()
        db.refresh(equipment)
    return equipment


def main():
    db = SessionLocal()
    try:
        admin_role = get_or_create_role(db, "admin")
        user_role = get_or_create_role(db, "user")
        get_or_create_role(db, "supervisor")
        get_or_create_role(db, "reviewer")
        get_or_create_role(db, "manager")

        get_or_create_user(db, "admin", "admin123", admin_role)
        get_or_create_user(db, "operator", "operator123", user_role)

        place = get_or_create_place(db, "Main Data Hall", "Primary telemetry demo location")
        battery_type = get_or_create_equipment_type(db, "battery")
        server_type = get_or_create_equipment_type(db, "server")

        get_or_create_equipment(
            db,
            name="Battery Bank A",
            equipment_type_id=battery_type.id,
            place_id=place.id,
            status="On",
            remarks="Demo battery for telemetry publishing",
        )
        get_or_create_equipment(
            db,
            name="Server Rack A",
            equipment_type_id=server_type.id,
            place_id=place.id,
            status="On",
            remarks="Demo server for telemetry publishing",
        )
        print("Demo data seeded successfully")
    finally:
        db.close()


if __name__ == "__main__":
    main()
