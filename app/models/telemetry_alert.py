from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import relationship

from app.db.base import Base


class TelemetryAlert(Base):
    __tablename__ = "telemetry_alerts"

    id = Column(Integer, primary_key=True)
    equipment_id = Column(Integer, ForeignKey("equipments.id"), nullable=False, index=True)
    severity = Column(String(20), nullable=False, default="high")
    title = Column(String(120), nullable=False)
    message = Column(String(255), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    equipment = relationship("Equipment")
