# app/modules/users/repository.py
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.users.models import User


async def get_by_id(session: AsyncSession, user_id: uuid.UUID) -> User | None:
    return await session.get(User, user_id)


async def get_by_phone(session: AsyncSession, phone: str) -> User | None:
    stmt = select(User).where(User.phone == phone)
    return (await session.execute(stmt)).scalar_one_or_none()


def add(session: AsyncSession, user: User) -> None:
    session.add(user)
