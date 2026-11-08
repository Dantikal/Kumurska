"""Бизнес-логика пользователей."""

import uuid
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.users import repository
from app.modules.users.models import User
from app.modules.users.schemas import UserUpdate


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
    """Создаёт пользователя в текущей транзакции."""
    user = User(
        phone=phone,
        name=name,
        birth_date=birth_date,
        password_hash=password_hash,
    )
    repository.add(session, user)
    await session.flush()
    return user


def get_profile(user: User) -> User:
    """Возвращает профиль пользователя."""
    return user


async def update_profile(
    session: AsyncSession,
    user: User,
    data: UserUpdate,
) -> User:
    """Обновляет данные профиля в текущей транзакции."""
    updated_fields = data.get_updated_fields()

    for field, value in updated_fields.items():
        setattr(user, field, value)

    await session.flush()
    return user
