from sqlalchemy import Column, Integer, String, Float, ForeignKey,DateTime, func
from app.db.base import Base
from sqlalchemy.orm import relationship


class EquipmentMetadata(Base):
    __tablename__ = "equipment_metadata"
    id = Column(Integer, primary_key=True)
    equipment_id = Column(Integer, ForeignKey("equipments.id"))
    pressure = Column(Float)
    temperature = Column(Float)
    humidity = Column(Float)
    frequency = Column(Float)
    voltage = Column(Float)
    recorded_at = Column(DateTime, server_default=func.now())

    equipment = relationship("Equipment", back_populates="metadata_entries")