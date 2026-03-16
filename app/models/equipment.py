#model/equipment.py
from sqlalchemy import Column, Integer, String, Float, ForeignKey,DateTime, func
from app.db.base import Base
from sqlalchemy.orm import relationship

class Equipment(Base):
    __tablename__ = "equipments"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    equipment_type_id = Column(Integer, ForeignKey("equipment_types.id"))
    place_id = Column(Integer, ForeignKey("places.id"))
    status = Column(String)
    serviceability = Column(String)
    remarks = Column(String)
    created_at = Column(DateTime, server_default=func.now())

    # Relationships
    equipment_type = relationship("EquipmentType", back_populates="equipments")
    place = relationship("Place", back_populates="equipments")
    metadata_entries = relationship("EquipmentMetadata", back_populates="equipment", cascade="all, delete-orphan")