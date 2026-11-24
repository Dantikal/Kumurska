# app/modules/loyalty/repository.py
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.loyalty.models import (
    AccountStatus,
    BonusAccount,
    BonusTransaction,
    LevelStatus,
    LoyaltyLevel,
    TransactionStatus,
)


async def get_entry_level(session: AsyncSession, now: datetime) -> LoyaltyLevel | None:
    """Действующий уровень с минимальным порогом — с него начинает новый клиент."""
    stmt = (
        select(LoyaltyLevel)
        .where(LoyaltyLevel.status == LevelStatus.ACTIVE, LoyaltyLevel.effective_from <= now)
        .order_by(LoyaltyLevel.threshold.asc(), LoyaltyLevel.effective_from.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


def add_account(session: AsyncSession, account: BonusAccount) -> None:
    session.add(account)


async def get_purchase_transactions(
    session: AsyncSession,
    purchase_id: uuid.UUID,
    user_id: uuid.UUID,
) -> list[BonusTransaction]:
    stmt = (
        select(BonusTransaction)
        .join(BonusAccount, BonusTransaction.account_id == BonusAccount.id)
        .where(
            BonusTransaction.purchase_id == purchase_id,
            BonusAccount.user_id == user_id,
            BonusTransaction.status == TransactionStatus.CONFIRMED,
        )
        .order_by(BonusTransaction.created_at.asc())
    )

    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_account_with_level(
    session: AsyncSession,
    user_id: uuid.UUID,
) -> tuple[BonusAccount, LoyaltyLevel] | None:
    stmt = (
        select(BonusAccount, LoyaltyLevel)
        .join(LoyaltyLevel, LoyaltyLevel.id == BonusAccount.level_id)
        .where(
            BonusAccount.user_id == user_id,
            BonusAccount.status == AccountStatus.ACTIVE,
        )
    )

    result = await session.execute(stmt)
    return result.one_or_none()


async def get_account_for_update(
    session: AsyncSession,
    user_id: uuid.UUID,
) -> tuple[BonusAccount, LoyaltyLevel] | None:
    stmt = (
        select(BonusAccount, LoyaltyLevel)
        .join(LoyaltyLevel, LoyaltyLevel.id == BonusAccount.level_id)
        .where(
            BonusAccount.user_id == user_id,
            BonusAccount.status == AccountStatus.ACTIVE,
        )
        .with_for_update(of=BonusAccount)
    )

    result = await session.execute(stmt)
    return result.one_or_none()


async def get_level_for_purchase(
    session: AsyncSession,
    threshold,
    purchased_at: datetime,
) -> LoyaltyLevel | None:
    stmt = (
        select(LoyaltyLevel)
        .where(
            LoyaltyLevel.threshold == threshold,
            LoyaltyLevel.effective_from <= purchased_at,
        )
        .order_by(LoyaltyLevel.effective_from.desc())
        .limit(1)
    )

    return (await session.execute(stmt)).scalar_one_or_none()
