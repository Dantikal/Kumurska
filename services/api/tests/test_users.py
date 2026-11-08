from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.auth.dependencies import get_current_user
from app.modules.users import repository, service
from app.modules.users.models import User
from app.modules.users.schemas import UserUpdate


def test_user_update_strips_name():
    data = UserUpdate(name="   Айжан   ")

    assert data.name == "Айжан"


def test_user_update_rejects_empty_name():
    with pytest.raises(ValueError):
        UserUpdate(name="   ")


def test_user_update_rejects_future_birth_date():
    with pytest.raises(ValueError):
        UserUpdate(birth_date=date(2030, 5, 15))


def test_user_update_accepts_valid_birth_date():
    data = UserUpdate(birth_date=date(2004, 5, 1))

    assert data.birth_date == date(2004, 5, 1)


def test_user_update_rejects_empty_payload():
    with pytest.raises(ValueError):
        UserUpdate()


def test_user_update_returns_only_provided_fields():
    data = UserUpdate(name="Айжан")

    assert data.get_updated_fields() == {"name": "Айжан"}


@pytest.mark.anyio
async def test_user_service_updates_name():
    user = SimpleNamespace(name="Айжан")
    data = UserUpdate(name="Гулмайрам")

    session = SimpleNamespace(flush=AsyncMock())

    result = await service.update_profile(session, user, data)

    assert result.name == "Гулмайрам"
    session.flush.assert_awaited_once()


@pytest.mark.anyio
async def test_user_service_updates_only_provided_fields():
    user = SimpleNamespace(
        name="Айжан",
        birth_date=date(2004, 5, 1),
    )
    data = UserUpdate(name="Гулмайрам")

    session = SimpleNamespace(flush=AsyncMock())

    result = await service.update_profile(session, user, data)

    assert result.name == "Гулмайрам"
    assert result.birth_date == date(2004, 5, 1)
    session.flush.assert_awaited_once()


@pytest.mark.anyio
async def test_user_repository_get_by_id():
    user_id = uuid4()
    user = SimpleNamespace(id=user_id, name="Айжан")

    session = SimpleNamespace(get=AsyncMock(return_value=user))

    result = await repository.get_by_id(session, user_id)

    assert result == user
    session.get.assert_awaited_once_with(repository.User, user_id)


@pytest.mark.anyio
async def test_user_repository_returns_none_when_not_found():
    user_id = uuid4()

    session = SimpleNamespace(get=AsyncMock(return_value=None))

    result = await repository.get_by_id(session, user_id)

    assert result is None
    session.get.assert_awaited_once_with(repository.User, user_id)


@pytest.mark.anyio
async def test_get_my_profile(api, session_factory):
    async with session_factory() as session:
        user = User(
            phone="+996700000001",
            name="Айжан",
            birth_date=date(2004, 5, 1),
            password_hash=None,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

    async def override_get_current_user() -> User:
        return user

    from app.main import app

    app.dependency_overrides[get_current_user] = override_get_current_user

    response = await api.get("/api/v1/users/me")

    assert response.status_code == 200
    assert response.json()["name"] == "Айжан"
    assert response.json()["phone"] == "+996700000001"
    assert response.json()["birth_date"] == "2004-05-01"


@pytest.mark.anyio
async def test_update_my_profile(api, session_factory):
    async with session_factory() as session:
        user = User(
            phone="+996700000002",
            name="Айжан",
            birth_date=date(2004, 5, 1),
            password_hash=None,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

    async def override_get_current_user(
        db: AsyncSession = Depends(get_db),
    ) -> User:
        return await db.get(User, user.id)

    from app.main import app

    app.dependency_overrides[get_current_user] = override_get_current_user

    response = await api.patch(
        "/api/v1/users/me",
        json={"name": "Гулмайрам"},
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Гулмайрам"
    assert response.json()["phone"] == "+996700000002"

    async with session_factory() as session:
        updated_user = await session.get(User, user.id)

    assert updated_user.name == "Гулмайрам"
