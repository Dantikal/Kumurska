"""Бизнес-логика и транзакции."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.modules.loyalty.models import TransactionType
from app.modules.purchases import repository
from app.modules.purchases.schemas import PurchaseRead


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

    transactions = await repository.get_purchase_transactions(
        session,
        purchase_id,
        user_id,
    )

    points_redeemed = sum(
        transaction.amount
        for transaction in transactions
        if transaction.type == TransactionType.REDEMPTION
    )

    cashback_earned = sum(
        transaction.amount
        for transaction in transactions
        if transaction.type == TransactionType.ACCRUAL
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
