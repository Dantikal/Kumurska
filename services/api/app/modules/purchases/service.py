from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.purchases import repository


async def get_total_amounts_by_ids(
    session: AsyncSession,
    purchase_ids: list[UUID],
    user_id: UUID,
) -> dict[UUID, Decimal]:
    return await repository.get_total_amounts_by_ids(
        session,
        purchase_ids,
        user_id,
    )
