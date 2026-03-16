
from sqlalchemy import Column, Integer, String
from app.db.base import Base
from sqlalchemy.orm import relationship
class Place(Base):
    __tablename__ = "places"
    id = Column(Integer, primary_key=True)
    name = Column(String)
    description = Column(String)
    equipments = relationship("Equipment", back_populates="place")
