# app/modules/auth/models.py
import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.models import IdMixin, TimestampMixin, enum_column


class OtpPurpose(StrEnum):
    REGISTER = "register"
    RESET_PASSWORD = "reset_password"
    CHANGE_PHONE = "change_phone"


class OtpCode(IdMixin, TimestampMixin, Base):
    """Одноразовый код. id записи служит verification_id для клиента."""

    __tablename__ = "otp_codes"
    __table_args__ = (Index("ix_otp_codes_phone_purpose", "phone", "purpose"),)

    phone: Mapped[str] = mapped_column(String(20))
    purpose: Mapped[OtpPurpose] = mapped_column(enum_column(OtpPurpose))
    # HMAC-SHA256 от "{id}:{code}", сам код не хранится
    code_hash: Mapped[str] = mapped_column(String(64))
    # данные регистрации; пароль только в виде хеша
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    resend_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RefreshToken(IdMixin, Base):
    """Refresh-токен. Хранится только SHA-256 хеш; ротация и устройства — US-25."""

    __tablename__ = "refresh_tokens"

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
