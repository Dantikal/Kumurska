# app/modules/loyalty/repository.py
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.loyalty.models import BonusAccount, LevelStatus, LoyaltyLevel


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
