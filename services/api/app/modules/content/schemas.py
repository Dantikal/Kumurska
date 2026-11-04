# app/modules/content/schemas.py
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class PromotionRead(BaseModel):
    id: UUID
    title: str
    description: str | None
    image_url: str | None
    starts_at: datetime
    ends_at: datetime
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class EventRead(BaseModel):
    id: UUID
    title: str
    image_url: str | None
    starts_at: datetime
    ends_at: datetime | None
    is_period: bool
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
