# app/core/models.py
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, func
from sqlalchemy.orm import Mapped, mapped_column


def enum_column(enum_cls, **kwargs):
    """Enum с хранением значений (active/blocked/...), а не имён (ACTIVE/...)."""
    return Enum(
        enum_cls,
        native_enum=False,
        values_callable=lambda e: [item.value for item in e],
        **kwargs,
    )


class IdMixin:
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
