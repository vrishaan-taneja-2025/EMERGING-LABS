
from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship
from app.db.base import Base

class EquipmentType(Base):
    __tablename__ = "equipment_types"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)

    # Relationship with Equipment
    equipments = relationship("Equipment", back_populates="equipment_type")
