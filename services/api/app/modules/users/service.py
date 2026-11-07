# app/modules/users/service.py
import uuid
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.users import repository
from app.modules.users.models import User


async def get_user(session: AsyncSession, user_id: uuid.UUID) -> User | None:
    return await repository.get_by_id(session, user_id)


async def phone_exists(session: AsyncSession, phone: str) -> bool:
    return await repository.get_by_phone(session, phone) is not None


async def create_user(
    session: AsyncSession,
    *,
    phone: str,
    name: str,
    birth_date: date,
    password_hash: str | None,
) -> User:
    """Создаёт пользователя в текущей транзакции, не коммитит.

    При занятом номере flush бросает IntegrityError (UNIQUE phone).
    """
    user = User(phone=phone, name=name, birth_date=birth_date, password_hash=password_hash)
    repository.add(session, user)
    await session.flush()
    return user
