from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from app.db.base import Base
from sqlalchemy.sql import func

class DIWorkflow(Base):
    __tablename__ = "di_workflow"

    id = Column(Integer, primary_key=True)
    di_id = Column(Integer, ForeignKey("daily_inspections.id"))
    from_role = Column(String(30))
    to_role = Column(String(30))
    action = Column(String(50))
    comments = Column(String(255))
    acted_by = Column(Integer, ForeignKey("users.id"))
    acted_at = Column(DateTime, server_default=func.now())

    # Relationships
    di = relationship("DailyInspection", back_populates="workflow")
