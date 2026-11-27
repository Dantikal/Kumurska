"""Запросы к базе данных."""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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


async def get_total_amounts_by_ids(
    session: AsyncSession,
    purchase_ids: list[UUID],
    user_id: UUID,
) -> dict[UUID, Decimal]:
    if not purchase_ids:
        return {}

    stmt = select(Purchase.id, Purchase.total_amount).where(
        Purchase.id.in_(purchase_ids),
        Purchase.user_id == user_id,
    )

    result = await session.execute(stmt)
    return {purchase_id: total_amount for purchase_id, total_amount in result.all()}
