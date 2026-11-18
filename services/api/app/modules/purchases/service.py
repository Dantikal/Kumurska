from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.modules.purchases import repository
from app.modules.purchases.schemas import PurchaseRead


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


async def get_purchase_details(
    session: AsyncSession,
    purchase_id: UUID,
    user_id: UUID,
) -> PurchaseRead:
    from app.modules.loyalty import service as loyalty_service

    purchase = await repository.get_purchase(
        session,
        purchase_id,
        user_id,
    )

    if purchase is None:
        raise ApiError(
            404,
            "PURCHASE_NOT_FOUND",
            "Покупка не найдена",
        )

    items = await repository.get_purchase_items(
        session,
        purchase_id,
    )

    points_redeemed, cashback_earned = await loyalty_service.get_purchase_rewards(
        session,
        purchase_id,
        user_id,
    )

    return PurchaseRead(
        id=purchase.id,
        receipt_number=purchase.receipt_number,
        total_amount=purchase.total_amount,
        paid_amount=purchase.paid_amount,
        points_redeemed=points_redeemed,
        cashback_earned=cashback_earned,
        purchased_at=purchase.purchased_at,
        status=purchase.status.value,
        items=items,
        created_at=purchase.created_at,
        updated_at=purchase.updated_at,
    )
