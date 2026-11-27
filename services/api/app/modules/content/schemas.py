# app/modules/content/schemas.py
from datetime import datetime
from typing import Annotated, Any, Self
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    StringConstraints,
    field_validator,
    model_validator,
)

from app.modules.content.models import ContentStatus


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


class LegalDocumentRead(BaseModel):
    id: UUID
    type: str
    version: int
    title: str
    content: str
    status: str
    published_at: datetime | None

    model_config = {"from_attributes": True}


# --- админка (US-17) -------------------------------------------------------------

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
ImageUrl = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


def _check_period(starts_at: datetime | None, ends_at: datetime | None) -> None:
    if starts_at is not None and ends_at is not None and ends_at <= starts_at:
        raise ValueError("ends_at должен быть позже starts_at")


class _NoNullTitle(BaseModel):
    """В PATCH поле можно не передавать, но нельзя стереть: название обязательно всегда."""

    @field_validator("title", mode="before", check_fields=False)
    @classmethod
    def _title_not_null(cls, value: Any) -> Any:
        if value is None:
            raise ValueError("Название нельзя удалить")
        return value


class PromotionCreate(BaseModel):
    title: Title
    description: str | None = None
    image_url: ImageUrl | None = None
    starts_at: AwareDatetime | None = None
    ends_at: AwareDatetime | None = None

    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def _period(self) -> Self:
        _check_period(self.starts_at, self.ends_at)
        return self


class PromotionUpdate(_NoNullTitle):
    """Передаются только изменяемые поля; null очищает необязательное поле."""

    title: Title | None = None
    description: str | None = None
    image_url: ImageUrl | None = None
    starts_at: AwareDatetime | None = None
    ends_at: AwareDatetime | None = None

    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def _period(self) -> Self:
        _check_period(self.starts_at, self.ends_at)
        return self


class AdminPromotionRead(BaseModel):
    id: UUID
    title: str
    description: str | None
    image_url: str | None
    starts_at: datetime | None
    ends_at: datetime | None
    status: ContentStatus
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class EventCreate(BaseModel):
    title: Title
    image_url: ImageUrl | None = None
    starts_at: AwareDatetime | None = None
    ends_at: AwareDatetime | None = None
    is_period: bool = False

    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def _period(self) -> Self:
        _check_period(self.starts_at, self.ends_at)
        return self


class EventUpdate(_NoNullTitle):
    """Передаются только изменяемые поля; null очищает необязательное поле."""

    title: Title | None = None
    image_url: ImageUrl | None = None
    starts_at: AwareDatetime | None = None
    ends_at: AwareDatetime | None = None
    is_period: bool | None = None

    model_config = {"extra": "forbid"}

    @field_validator("is_period", mode="before")
    @classmethod
    def _is_period_not_null(cls, value: Any) -> Any:
        if value is None:
            raise ValueError("is_period не может быть null")
        return value

    @model_validator(mode="after")
    def _period(self) -> Self:
        _check_period(self.starts_at, self.ends_at)
        return self


class AdminEventRead(BaseModel):
    id: UUID
    title: str
    image_url: str | None
    starts_at: datetime | None
    ends_at: datetime | None
    is_period: bool
    status: ContentStatus
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ImageUploadRead(BaseModel):
    image_url: str
