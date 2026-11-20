import base64
import binascii
import json
import uuid
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.core.schemas import Page
from app.modules.loyalty import repository
from app.modules.loyalty.models import (
    BonusAccount,
    BonusTransaction,
    TransactionType,
)
from app.modules.loyalty.schemas import (
    BonusAccountRead,
    BonusTransactionRead,
)
from app.modules.purchases import service as purchases_service


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


def _encode_transaction_cursor(transaction: BonusTransaction) -> str:
    payload = {
        "created_at": transaction.created_at.isoformat(),
        "id": str(transaction.id),
    }
    raw_cursor = json.dumps(payload, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw_cursor).decode()


def _decode_transaction_cursor(cursor: str) -> tuple[datetime, UUID]:
    try:
        raw_cursor = base64.urlsafe_b64decode(cursor.encode())
        payload = json.loads(raw_cursor.decode())
        created_at = datetime.fromisoformat(payload["created_at"])
        transaction_id = UUID(payload["id"])
    except (
        binascii.Error,
        UnicodeDecodeError,
        ValueError,
        KeyError,
        TypeError,
        json.JSONDecodeError,
    ):
        raise ApiError(
            422,
            "INVALID_CURSOR",
            "Некорректный курсор пагинации",
        ) from None

    return created_at, transaction_id


async def list_transactions(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    cursor: str | None,
    limit: int,
) -> Page[BonusTransactionRead]:
    cursor_created_at: datetime | None = None
    cursor_id: UUID | None = None

    if cursor is not None:
        cursor_created_at, cursor_id = _decode_transaction_cursor(cursor)

    transactions = await repository.list_transactions(
        session,
        user_id,
        cursor_created_at,
        cursor_id,
        limit + 1,
    )

    has_next_page = len(transactions) > limit
    visible_transactions = transactions[:limit]

    purchase_ids = [
        transaction.purchase_id
        for transaction in visible_transactions
        if transaction.purchase_id is not None
    ]

    purchase_amounts = await purchases_service.get_total_amounts_by_ids(
        session,
        purchase_ids,
        user_id,
    )

    items = [
        BonusTransactionRead(
            id=transaction.id,
            account_id=transaction.account_id,
            purchase_id=transaction.purchase_id,
            purchase_amount=(
                purchase_amounts.get(transaction.purchase_id)
                if transaction.purchase_id is not None
                else None
            ),
            type=transaction.type.value,
            amount=transaction.amount,
            reason=transaction.reason,
            status=transaction.status.value,
            created_at=transaction.created_at,
        )
        for transaction in visible_transactions
    ]

    next_cursor = None
    if has_next_page and visible_transactions:
        next_cursor = _encode_transaction_cursor(visible_transactions[-1])

    return Page(items=items, next_cursor=next_cursor)
