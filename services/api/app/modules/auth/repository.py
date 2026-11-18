# app/modules/auth/repository.py
import uuid
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import OtpCode, OtpPurpose, RefreshToken, Session


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


def add_session(session: AsyncSession, auth_session: Session) -> None:
    session.add(auth_session)


async def get_session(session: AsyncSession, session_id: uuid.UUID) -> Session | None:
    return await session.get(Session, session_id, populate_existing=True)


async def get_refresh_token_for_update(
    session: AsyncSession, token_hash: str
) -> RefreshToken | None:
    """Загружает токен с блокировкой строки: обмен одного токена идёт строго по очереди."""
    stmt = (
        select(RefreshToken)
        .where(RefreshToken.token_hash == token_hash)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def revoke_session(session: AsyncSession, session_id: uuid.UUID, now: datetime) -> None:
    await session.execute(
        update(Session)
        .where(Session.id == session_id, Session.revoked_at.is_(None))
        .values(revoked_at=now)
    )


async def revoke_device_sessions(
    session: AsyncSession, user_id: uuid.UUID, device_id: str, now: datetime
) -> None:
    await session.execute(
        update(Session)
        .where(
            Session.user_id == user_id,
            Session.device_id == device_id,
            Session.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )


async def revoke_user_sessions(session: AsyncSession, user_id: uuid.UUID, now: datetime) -> None:
    await session.execute(
        update(Session)
        .where(Session.user_id == user_id, Session.revoked_at.is_(None))
        .values(revoked_at=now)
    )
