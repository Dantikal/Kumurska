# app/modules/loyalty/service.py
import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.modules.loyalty import repository
from app.modules.loyalty.models import BonusAccount
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
