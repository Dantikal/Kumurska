"""Бизнес-логика и транзакции."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.modules.loyalty import service as loyalty_service
from app.modules.purchases import repository
from app.modules.purchases.models import Purchase, PurchaseItem, PurchaseStatus
from app.modules.purchases.schemas import PurchaseCreate, PurchaseRead


async def record_purchase(
    session: AsyncSession,
    data: PurchaseCreate,
) -> Purchase:
    existing_purchase = await repository.get_purchase_by_external_id(
        session,
        data.source,
        data.external_id,
    )

    if existing_purchase is not None:
        return existing_purchase

    purchase = Purchase(
        user_id=data.user_id,
        source=data.source,
        external_id=data.external_id,
        receipt_number=data.receipt_number,
        total_amount=data.total_amount,
        paid_amount=data.paid_amount,
        points_to_redeem=data.points_redeemed,
        purchased_at=data.purchased_at,
        status=PurchaseStatus.PENDING,
    )

    purchase = await repository.create_purchase(session, purchase)

    items = [
        PurchaseItem(
            purchase_id=purchase.id,
            name=item.name,
            quantity=item.quantity,
            unit_price=item.unit_price,
            line_total=item.line_total,
        )
        for item in data.items
    ]

    await repository.create_purchase_items(session, items)

    return purchase


async def get_purchase_details(
    session: AsyncSession,
    purchase_id: UUID,
    user_id: UUID,
) -> PurchaseRead:
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


async def confirm_purchase(
    session: AsyncSession,
    purchase_id: UUID,
) -> Purchase:
    purchase = await repository.get_purchase_for_update(
        session,
        purchase_id,
    )

    if purchase is None:
        raise ApiError(
            404,
            "PURCHASE_NOT_FOUND",
            "Покупка не найдена",
        )

    if purchase.status == PurchaseStatus.CONFIRMED:
        return purchase

    if purchase.status != PurchaseStatus.PENDING:
        raise ApiError(
            400,
            "PURCHASE_CANNOT_BE_CONFIRMED",
            "Эту покупку нельзя подтвердить",
        )

    await loyalty_service.apply_purchase_rewards(
        session=session,
        purchase_id=purchase.id,
        user_id=purchase.user_id,
        paid_amount=purchase.paid_amount,
        points_to_redeem=purchase.points_to_redeem,
        purchased_at=purchase.purchased_at,
    )

    purchase.status = PurchaseStatus.CONFIRMED

    await session.flush()

    return purchase
