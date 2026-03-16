from pydantic import BaseModel, Field
from typing import Optional

class EquipmentBase(BaseModel):
    name: str
    place_id: int
    equipment_type_id: Optional[int] = None
    status: str = Field(..., pattern="^(On|Off)$")        # On/Off
    serviceability: str = Field(..., pattern="^(S|US)$")  # S / US
    remarks: Optional[str] = None

    # Metadata (optional)
    pressure: Optional[float] = None
    temperature: Optional[float] = None
    voltage: Optional[float] = None
    frequency: Optional[float] = None

class EquipmentCreate(EquipmentBase):
    pass

class EquipmentUpdate(EquipmentBase):
    pass