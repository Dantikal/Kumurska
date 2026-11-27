# app/modules/content/models.py
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.models import IdMixin, TimestampMixin, enum_column


class ContentStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    UNPUBLISHED = "unpublished"


class LegalDocumentType(StrEnum):
    TERMS = "terms"
    PRIVACY = "privacy"


class LegalDocumentStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"


class Promotion(IdMixin, TimestampMixin, Base):
    __tablename__ = "promotions"
    # Черновик можно сохранить без сроков, опубликованная акция — всегда со сроками (US-17)
    __table_args__ = (
        CheckConstraint(
            "status = 'draft' OR (starts_at IS NOT NULL AND ends_at IS NOT NULL)",
            name="published_has_dates",
        ),
    )

    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[ContentStatus] = mapped_column(
        enum_column(ContentStatus), default=ContentStatus.DRAFT
    )


class Event(IdMixin, TimestampMixin, Base):
    __tablename__ = "events"
    __table_args__ = (
        CheckConstraint(
            "status = 'draft' OR starts_at IS NOT NULL",
            name="published_has_starts_at",
        ),
    )

    title: Mapped[str] = mapped_column(String(255))
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_period: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[ContentStatus] = mapped_column(
        enum_column(ContentStatus), default=ContentStatus.DRAFT
    )


class LegalDocument(IdMixin, Base):
    __tablename__ = "legal_documents"
    __table_args__ = (UniqueConstraint("type", "version", name="uq_legal_documents_type_version"),)

    type: Mapped[LegalDocumentType] = mapped_column(enum_column(LegalDocumentType))
    version: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text)
    status: Mapped[LegalDocumentStatus] = mapped_column(
        enum_column(LegalDocumentStatus),
        default=LegalDocumentStatus.DRAFT,
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
