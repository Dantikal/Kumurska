# app/modules/auth/repository.py
import uuid
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import OtpCode, OtpPurpose, RefreshToken


async def get_otp_for_update(
    session: AsyncSession, otp_id: uuid.UUID, purpose: OtpPurpose
) -> OtpCode | None:
    """Загружает код с блокировкой строки до конца транзакции."""
    stmt = (
        select(OtpCode)
        .where(OtpCode.id == otp_id, OtpCode.purpose == purpose)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_latest_active_otp(
    session: AsyncSession, phone: str, purpose: OtpPurpose
) -> OtpCode | None:
    stmt = (
        select(OtpCode)
        .where(
            OtpCode.phone == phone,
            OtpCode.purpose == purpose,
            OtpCode.consumed_at.is_(None),
        )
        .order_by(OtpCode.created_at.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def consume_active_otps(
    session: AsyncSession, phone: str, purpose: OtpPurpose, now: datetime
) -> None:
    """Аннулирует все неиспользованные коды номера для этой цели."""
    await session.execute(
        update(OtpCode)
        .where(
            OtpCode.phone == phone,
            OtpCode.purpose == purpose,
            OtpCode.consumed_at.is_(None),
        )
        .values(consumed_at=now)
    )


def add_otp(session: AsyncSession, otp: OtpCode) -> None:
    session.add(otp)


def add_refresh_token(session: AsyncSession, token: RefreshToken) -> None:
    session.add(token)
