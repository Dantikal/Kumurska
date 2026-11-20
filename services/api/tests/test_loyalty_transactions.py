from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.main import app
from app.modules.auth.dependencies import get_current_user
from app.modules.loyalty.models import (
    BonusAccount,
    BonusTransaction,
    TransactionStatus,
    TransactionType,
)
from app.modules.purchases.models import Purchase, PurchaseStatus
from app.modules.users.models import User


@pytest.mark.anyio
async def test_list_my_bonus_transactions_with_pagination(
    api,
    session_factory,
    entry_level,
):
    async with session_factory() as session:
        user = User(
            phone="+996700000020",
            name="Transactions User",
            birth_date=datetime(1995, 1, 1).date(),
            password_hash=None,
        )
        session.add(user)
        await session.flush()

        account = BonusAccount(
            user_id=user.id,
            level_id=entry_level.id,
            balance=150,
            accumulated_total=Decimal("3000.00"),
        )
        session.add(account)
        await session.flush()

        older_purchase = Purchase(
            user_id=user.id,
            source="test",
            external_id="purchase-old-001",
            receipt_number="000001",
            total_amount=Decimal("1000.00"),
            paid_amount=Decimal("1000.00"),
            purchased_at=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
            status=PurchaseStatus.CONFIRMED,
        )
        newer_purchase = Purchase(
            user_id=user.id,
            source="test",
            external_id="purchase-new-001",
            receipt_number="000002",
            total_amount=Decimal("2000.00"),
            paid_amount=Decimal("1800.00"),
            purchased_at=datetime(2026, 1, 2, 12, 0, tzinfo=UTC),
            status=PurchaseStatus.CONFIRMED,
        )
        session.add_all([older_purchase, newer_purchase])
        await session.flush()

        older_transaction = BonusTransaction(
            account_id=account.id,
            purchase_id=older_purchase.id,
            type=TransactionType.ACCRUAL,
            amount=50,
            reason="Old cashback",
            status=TransactionStatus.CONFIRMED,
            created_at=datetime(2026, 1, 1, 13, 0, tzinfo=UTC),
        )
        newer_transaction = BonusTransaction(
            account_id=account.id,
            purchase_id=newer_purchase.id,
            type=TransactionType.REDEMPTION,
            amount=-100,
            reason="Points redemption",
            status=TransactionStatus.CONFIRMED,
            created_at=datetime(2026, 1, 2, 13, 0, tzinfo=UTC),
        )
        session.add_all([older_transaction, newer_transaction])
        await session.commit()

    async def override_get_current_user() -> User:
        return user

    app.dependency_overrides[get_current_user] = override_get_current_user

    try:
        first_response = await api.get(
            "/api/v1/loyalty/transactions",
            params={"limit": 1},
        )

        assert first_response.status_code == 200
        first_page = first_response.json()
        assert len(first_page["items"]) == 1
        assert first_page["items"][0]["amount"] == -100
        assert first_page["items"][0]["type"] == "redemption"
        assert first_page["items"][0]["purchase_amount"] == "2000.00"
        assert first_page["next_cursor"] is not None

        second_response = await api.get(
            "/api/v1/loyalty/transactions",
            params={
                "limit": 1,
                "cursor": first_page["next_cursor"],
            },
        )

        assert second_response.status_code == 200
        second_page = second_response.json()
        assert len(second_page["items"]) == 1
        assert second_page["items"][0]["amount"] == 50
        assert second_page["items"][0]["type"] == "accrual"
        assert second_page["items"][0]["purchase_amount"] == "1000.00"
        assert second_page["next_cursor"] is None
    finally:
        app.dependency_overrides.pop(get_current_user, None)
