from sqlalchemy import Column, Integer, ForeignKey, String
from sqlalchemy.orm import relationship
from app.db.base import Base

class DIEquipmentLog(Base):
    __tablename__ = "di_equipment_logs"

    id = Column(Integer, primary_key=True)
    di_id = Column(Integer, ForeignKey("daily_inspections.id"))
    equipment_id = Column(Integer, ForeignKey("equipments.id"))
    serviceability = Column(String(5))
    remarks = Column(String(255))

    # Relationships
    di = relationship("DailyInspection", back_populates="equipment_logs")