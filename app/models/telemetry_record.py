from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import relationship

from app.db.base import Base


class TelemetryRecord(Base):
    __tablename__ = "telemetry_records"

    id = Column(Integer, primary_key=True)
    equipment_id = Column(Integer, ForeignKey("equipments.id"), nullable=False, index=True)
    topic = Column(String(100), nullable=False)
    component_type = Column(String(30), nullable=False)
    status = Column(String(10), nullable=False)
    temperature = Column(Float)
    voltage = Column(Float)
    pressure = Column(Float)
    frequency = Column(Float)
    is_anomaly = Column(Boolean, default=False, nullable=False)
    anomaly_message = Column(String(255))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    equipment = relationship("Equipment")
