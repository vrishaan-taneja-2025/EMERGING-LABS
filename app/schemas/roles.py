from pydantic import BaseModel, Field

class RoleBase(BaseModel):
    name: str = Field(..., min_length=3, max_length=30)

class RoleCreate(RoleBase):
    pass

class RoleUpdate(RoleBase):
    pass