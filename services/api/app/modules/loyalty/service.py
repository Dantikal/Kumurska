# app/modules/loyalty/service.py
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.modules.loyalty import repository
from app.modules.loyalty.models import (
    BonusAccount,
    BonusTransaction,
    TransactionStatus,
    TransactionType,
)
from app.modules.loyalty.schemas import BonusAccountRead


async def open_account(session: AsyncSession, user_id: uuid.UUID) -> BonusAccount:
    """Открывает бонусный счёт на начальном уровне в текущей транзакции, не коммитит."""
    level = await repository.get_entry_level(session, datetime.now(UTC))
    if level is None:
        raise ApiError(500, "LOYALTY_LEVEL_NOT_CONFIGURED", "Не настроен начальный уровень")
    account = BonusAccount(user_id=user_id, level_id=level.id, balance=0, accumulated_total=0)
    repository.add_account(session, account)
    await session.flush()
    return account


async def get_purchase_rewards(
    session: AsyncSession,
    purchase_id: uuid.UUID,
    user_id: uuid.UUID,
) -> tuple[int, int]:
    """Возвращает количество списанных баллов и начисленный кешбэк по покупке."""
    transactions = await repository.get_purchase_transactions(
        session,
        purchase_id,
        user_id,
    )

    points_redeemed = abs(
        sum(
            transaction.amount
            for transaction in transactions
            if transaction.type == TransactionType.REDEMPTION
        )
    )

    cashback_earned = sum(
        transaction.amount
        for transaction in transactions
        if transaction.type == TransactionType.ACCRUAL
    )

    return points_redeemed, cashback_earned


async def get_account(
    session: AsyncSession,
    user_id: uuid.UUID,
) -> BonusAccountRead:
    row = await repository.get_account_with_level(session, user_id)

    if row is None:
        raise ApiError(
            404,
            "BONUS_ACCOUNT_NOT_FOUND",
            "Бонусный счёт не найден",
        )

    account, level = row

    return BonusAccountRead(
        id=account.id,
        user_id=account.user_id,
        level_id=account.level_id,
        level_name=level.name,
        cashback_percent=level.cashback_percent,
        balance=account.balance,
        accumulated_total=account.accumulated_total,
        level_expires_at=account.level_expires_at,
        status=account.status.value,
        created_at=account.created_at,
        updated_at=account.updated_at,
    )


async def apply_purchase_rewards(
    session: AsyncSession,
    purchase_id: uuid.UUID,
    user_id: uuid.UUID,
    paid_amount: Decimal,
    points_to_redeem: int,
    purchased_at: datetime,
) -> tuple[int, int]:
    """Начисляет кешбэк и списывает баллы за подтверждённую покупку."""

    account_data = await repository.get_account_for_update(
        session,
        user_id,
    )

    if account_data is None:
        raise ApiError(
            404,
            "BONUS_ACCOUNT_NOT_FOUND",
            "Бонусный счёт не найден",
        )

    account, current_level = account_data

    level = await repository.get_level_for_purchase(
        session,
        current_level.threshold,
        purchased_at,
    )

    if level is None:
        raise ApiError(
            500,
            "LOYALTY_LEVEL_NOT_FOUND",
            "Не найден уровень лояльности на дату покупки",
        )

    cashback_earned = int(
        paid_amount * level.cashback_percent / Decimal("100")
    )

    if points_to_redeem > 0:
        redemption = BonusTransaction(
            account_id=account.id,
            purchase_id=purchase_id,
            type=TransactionType.REDEMPTION,
            amount=-points_to_redeem,
            status=TransactionStatus.CONFIRMED,
        )
        session.add(redemption)

    if cashback_earned > 0:
        accrual = BonusTransaction(
            account_id=account.id,
            purchase_id=purchase_id,
            type=TransactionType.ACCRUAL,
            amount=cashback_earned,
            status=TransactionStatus.CONFIRMED,
        )
        session.add(accrual)

    account.balance += cashback_earned - points_to_redeem
    account.accumulated_total += paid_amount

    await session.flush()

    return points_to_redeem, cashback_earned
