from sqlalchemy import Column, Integer, Date, ForeignKey, String, DateTime, func
from sqlalchemy.orm import relationship
from app.db.base import Base

class DailyInspection(Base):
    __tablename__ = "daily_inspections"

    id = Column(Integer, primary_key=True)
    inspection_date = Column(Date, nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"))
    status = Column(String(20), server_default="submitted")
    created_at = Column(DateTime, server_default=func.now())

    # Relationships
    user = relationship("User", back_populates="daily_inspections")
    equipment_logs = relationship("DIEquipmentLog", back_populates="di", cascade="all, delete-orphan")
    workflow = relationship("DIWorkflow", back_populates="di", cascade="all, delete-orphan")
