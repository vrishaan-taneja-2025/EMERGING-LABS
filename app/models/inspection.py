
from sqlalchemy import Column, Integer, Date, String, ForeignKey
from app.db.base import Base

class DailyInspection(Base):
    __tablename__ = "daily_inspections"
    id = Column(Integer, primary_key=True)
    date = Column(Date)
    created_by = Column(Integer, ForeignKey("users.id"))
    status = Column(String)
