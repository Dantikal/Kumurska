# app/modules/loyalty/service.py
import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.modules.loyalty import repository
from app.modules.loyalty.models import BonusAccount


async def open_account(session: AsyncSession, user_id: uuid.UUID) -> BonusAccount:
    """Открывает бонусный счёт на начальном уровне в текущей транзакции, не коммитит."""
    level = await repository.get_entry_level(session, datetime.now(UTC))
    if level is None:
        raise ApiError(500, "LOYALTY_LEVEL_NOT_CONFIGURED", "Не настроен начальный уровень")
    account = BonusAccount(user_id=user_id, level_id=level.id, balance=0, accumulated_total=0)
    repository.add_account(session, account)
    await session.flush()
    return account
