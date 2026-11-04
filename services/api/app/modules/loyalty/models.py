# app/modules/loyalty/models.py
import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.models import IdMixin, TimestampMixin, enum_column


class LevelStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class AccountStatus(StrEnum):
    ACTIVE = "active"
    CLOSED = "closed"


class TransactionType(StrEnum):
    ACCRUAL = "accrual"
    REDEMPTION = "redemption"
    REFUND = "refund"
    ADJUSTMENT = "adjustment"


class TransactionStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class LoyaltyLevel(IdMixin, TimestampMixin, Base):
    __tablename__ = "loyalty_levels"
    __table_args__ = (
        CheckConstraint(
            "cashback_percent >= 0 AND cashback_percent <= 100",
            name="cashback_percent_range",
        ),
    )

    name: Mapped[str] = mapped_column(String(100))
    cashback_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    threshold: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[LevelStatus] = mapped_column(
        enum_column(LevelStatus), default=LevelStatus.ACTIVE
    )


class BonusAccount(IdMixin, TimestampMixin, Base):
    __tablename__ = "bonus_accounts"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    level_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("loyalty_levels.id"))
    balance: Mapped[int] = mapped_column(Integer, default=0)
    accumulated_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    level_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[AccountStatus] = mapped_column(
        enum_column(AccountStatus), default=AccountStatus.ACTIVE
    )


class BonusTransaction(IdMixin, Base):
    __tablename__ = "bonus_transactions"

    # журнал неизменяем — только created_at, без updated_at
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bonus_accounts.id"), index=True)
    purchase_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("purchases.id"), nullable=True)
    type: Mapped[TransactionType] = mapped_column(enum_column(TransactionType))
    amount: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[TransactionStatus] = mapped_column(
        enum_column(TransactionStatus), default=TransactionStatus.PENDING
    )
