from datetime import date
from decimal import Decimal

import pytest

from app.main import app
from app.modules.auth.dependencies import get_current_user
from app.modules.loyalty.models import BonusAccount
from app.modules.users.models import User


@pytest.mark.anyio
async def test_get_my_loyalty_account(api, session_factory, entry_level):
    async with session_factory() as session:
        user = User(
            phone="+996700000010",
            name="Test Loyalty User",
            birth_date=date(1995, 1, 1),
            password_hash=None,
        )
        session.add(user)
        await session.flush()

        account = BonusAccount(
            user_id=user.id,
            level_id=entry_level.id,
            balance=1240,
            accumulated_total=Decimal("2480.00"),
        )
        session.add(account)
        await session.commit()
        await session.refresh(user)

    async def override_get_current_user() -> User:
        return user

    app.dependency_overrides[get_current_user] = override_get_current_user

    try:
        response = await api.get("/api/v1/loyalty/account")

        assert response.status_code == 200

        data = response.json()
        assert data["user_id"] == str(user.id)
        assert data["level_id"] == str(entry_level.id)
        assert data["level_name"] == entry_level.name
        assert data["cashback_percent"] == str(entry_level.cashback_percent)
        assert data["balance"] == 1240
        assert data["status"] == "active"
    finally:
        app.dependency_overrides.pop(get_current_user, None)
