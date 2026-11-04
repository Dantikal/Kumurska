# app/modules/users/schemas.py
from datetime import date
from uuid import UUID

from pydantic import BaseModel


class UserRead(BaseModel):
    id: UUID
    phone: str
    name: str
    birth_date: date
    status: str

    model_config = {"from_attributes": True}


class UserUpdate(BaseModel):
    name: str | None = None
    birth_date: date | None = None
