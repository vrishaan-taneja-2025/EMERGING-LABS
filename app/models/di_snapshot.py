from sqlalchemy import Column, Integer, Date, JSON, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.db.base import Base

class DISnapshot(Base):
    __tablename__ = "di_snapshots"

    id = Column(Integer, primary_key=True)
    di_id = Column(Integer, ForeignKey("daily_inspections.id"))
    snapshot_date = Column(Date, nullable=False)
    data = Column(JSON, nullable=False)   # equipment + metadata snapshot
    created_at = Column(DateTime, server_default=func.now())