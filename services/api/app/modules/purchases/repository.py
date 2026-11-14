"""Запросы к базе данных."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.loyalty.models import (
    BonusAccount,
    BonusTransaction,
    TransactionStatus,
)
from app.modules.purchases.models import Purchase, PurchaseItem


async def get_purchase(
    session: AsyncSession,
    purchase_id: UUID,
    user_id: UUID,
) -> Purchase | None:
    stmt = select(Purchase).where(
        Purchase.id == purchase_id,
        Purchase.user_id == user_id,
    )

    return (await session.execute(stmt)).scalar_one_or_none()


async def get_purchase_items(
    session: AsyncSession,
    purchase_id: UUID,
) -> list[PurchaseItem]:
    stmt = (
        select(PurchaseItem)
        .where(PurchaseItem.purchase_id == purchase_id)
        .order_by(PurchaseItem.created_at.asc())
    )

    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_purchase_transactions(
    session: AsyncSession,
    purchase_id: UUID,
    user_id: UUID,
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
