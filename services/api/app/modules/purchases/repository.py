from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.purchases.models import Purchase


async def get_total_amounts_by_ids(
    session: AsyncSession,
    purchase_ids: list[UUID],
    user_id: UUID,
) -> dict[UUID, object]:
    if not purchase_ids:
        return {}

    stmt = select(Purchase.id, Purchase.total_amount).where(
        Purchase.id.in_(purchase_ids),
        Purchase.user_id == user_id,
    )

    result = await session.execute(stmt)
    return {purchase_id: total_amount for purchase_id, total_amount in result.all()}
