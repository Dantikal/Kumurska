from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.dependencies import get_current_user
from app.modules.loyalty.models import (
    BonusAccount,
    BonusTransaction,
    LoyaltyLevel,
    TransactionStatus,
    TransactionType,
)
from app.modules.purchases.models import Purchase, PurchaseItem, PurchaseStatus
from app.modules.users.models import User


async def create_user(session: AsyncSession, phone: str) -> User:
    user = User(
        phone=phone,
        name="Тестовый пользователь",
        birth_date=date(2004, 5, 1),
        password_hash=None,
    )
    session.add(user)
    await session.flush()
    return user


async def create_purchase(
    session: AsyncSession,
    user_id: UUID,
) -> Purchase:
    purchase = Purchase(
        user_id=user_id,
        source="test",
        external_id=str(uuid4()),
        receipt_number="004512",
        total_amount=Decimal("2480.00"),
        paid_amount=Decimal("2180.00"),
        purchased_at=datetime(2026, 10, 12, 18, 5, tzinfo=UTC),
        status=PurchaseStatus.CONFIRMED,
    )
    session.add(purchase)
    await session.flush()

    item = PurchaseItem(
        purchase_id=purchase.id,
        name="Тестовый товар",
        quantity=2,
        unit_price=Decimal("1240.00"),
        line_total=Decimal("2480.00"),
    )
    session.add(item)
    await session.flush()

    return purchase


async def create_bonus_data(
    session: AsyncSession,
    user_id: UUID,
    purchase_id: UUID,
) -> BonusAccount:
    level = LoyaltyLevel(
        name="Тестовый уровень",
        cashback_percent=Decimal("5.00"),
        threshold=Decimal("0"),
        effective_from=datetime(2026, 1, 1, tzinfo=UTC),
    )
    session.add(level)
    await session.flush()

    account = BonusAccount(
        user_id=user_id,
        level_id=level.id,
        balance=109,
    )
    session.add(account)
    await session.flush()

    transactions = [
        BonusTransaction(
            account_id=account.id,
            purchase_id=purchase_id,
            type=TransactionType.REDEMPTION,
            amount=300,
            status=TransactionStatus.CONFIRMED,
        ),
        BonusTransaction(
            account_id=account.id,
            purchase_id=purchase_id,
            type=TransactionType.ACCRUAL,
            amount=109,
            status=TransactionStatus.CONFIRMED,
        ),
    ]

    session.add_all(transactions)
    await session.flush()
    return account


@pytest.mark.anyio
async def test_get_purchase_details(api, session_factory):
    async with session_factory() as session:
        user = await create_user(session, "+996700000101")
        purchase = await create_purchase(session, user.id)

        await create_bonus_data(
            session,
            user.id,
            purchase.id,
        )

        await session.commit()

    async def override_get_current_user() -> User:
        return user

    from app.main import app

    app.dependency_overrides[get_current_user] = override_get_current_user

    response = await api.get(f"/api/v1/purchases/{purchase.id}")

    assert response.status_code == 200

    data = response.json()

    assert data["receipt_number"] == "004512"
    assert data["total_amount"] == "2480.00"
    assert data["paid_amount"] == "2180.00"
    assert data["points_redeemed"] == 300
    assert data["cashback_earned"] == 109

    assert data["purchased_at"] == "2026-10-12T18:05:00Z"
    assert data["status"] == "confirmed"

    assert len(data["items"]) == 1

    item = data["items"][0]
    assert item["name"] == "Тестовый товар"
    assert item["quantity"] == 2
    assert item["unit_price"] == "1240.00"
    assert item["line_total"] == "2480.00"


@pytest.mark.anyio
async def test_get_nonexistent_purchase_returns_404(api, session_factory):
    async with session_factory() as session:
        user = await create_user(session, "+996700000104")
        await session.commit()

    async def override_get_current_user() -> User:
        return user

    from app.main import app

    app.dependency_overrides[get_current_user] = override_get_current_user

    response = await api.get(f"/api/v1/purchases/{uuid4()}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PURCHASE_NOT_FOUND"


@pytest.mark.anyio
async def test_user_cannot_get_another_users_purchase(api, session_factory):
    async with session_factory() as session:
        owner = await create_user(session, "+996700000102")
        another_user = await create_user(session, "+996700000103")
        purchase = await create_purchase(session, owner.id)

        await session.commit()

    async def override_get_current_user() -> User:
        return another_user

    from app.main import app

    app.dependency_overrides[get_current_user] = override_get_current_user

    response = await api.get(f"/api/v1/purchases/{purchase.id}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PURCHASE_NOT_FOUND"


@pytest.mark.anyio
async def test_purchase_without_bonus_transactions_returns_zero(api, session_factory):
    async with session_factory() as session:
        user = await create_user(session, "+996700000105")
        purchase = await create_purchase(session, user.id)
        await session.commit()

    async def override_get_current_user() -> User:
        return user

    from app.main import app

    app.dependency_overrides[get_current_user] = override_get_current_user

    response = await api.get(f"/api/v1/purchases/{purchase.id}")

    assert response.status_code == 200

    data = response.json()

    assert data["points_redeemed"] == 0
    assert data["cashback_earned"] == 0


@pytest.mark.anyio
async def test_purchase_ignores_pending_and_cancelled_transactions(
    api,
    session_factory,
):
    async with session_factory() as session:
        user = await create_user(session, "+996700000106")
        purchase = await create_purchase(session, user.id)

        account = await create_bonus_data(
            session,
            user.id,
            purchase.id,
        )

        transactions = [
            BonusTransaction(
                account_id=account.id,
                purchase_id=purchase.id,
                type=TransactionType.REDEMPTION,
                amount=100,
                status=TransactionStatus.PENDING,
            ),
            BonusTransaction(
                account_id=account.id,
                purchase_id=purchase.id,
                type=TransactionType.ACCRUAL,
                amount=50,
                status=TransactionStatus.CANCELLED,
            ),
        ]

        session.add_all(transactions)
        await session.commit()

    async def override_get_current_user() -> User:
        return user

    from app.main import app

    app.dependency_overrides[get_current_user] = override_get_current_user

    response = await api.get(f"/api/v1/purchases/{purchase.id}")

    assert response.status_code == 200

    data = response.json()

    assert data["points_redeemed"] == 300
    assert data["cashback_earned"] == 109


@pytest.mark.anyio
async def test_purchase_sums_only_redemptions_and_accruals(
    api,
    session_factory,
):
    async with session_factory() as session:
        user = await create_user(session, "+996700000107")
        purchase = await create_purchase(session, user.id)

        account = await create_bonus_data(
            session,
            user.id,
            purchase.id,
        )

        transactions = [
            BonusTransaction(
                account_id=account.id,
                purchase_id=purchase.id,
                type=TransactionType.REDEMPTION,
                amount=70,
                status=TransactionStatus.CONFIRMED,
            ),
            BonusTransaction(
                account_id=account.id,
                purchase_id=purchase.id,
                type=TransactionType.ACCRUAL,
                amount=21,
                status=TransactionStatus.CONFIRMED,
            ),
            BonusTransaction(
                account_id=account.id,
                purchase_id=purchase.id,
                type=TransactionType.REFUND,
                amount=500,
                status=TransactionStatus.CONFIRMED,
            ),
            BonusTransaction(
                account_id=account.id,
                purchase_id=purchase.id,
                type=TransactionType.ADJUSTMENT,
                amount=600,
                status=TransactionStatus.CONFIRMED,
            ),
        ]

        session.add_all(transactions)
        await session.commit()

    async def override_get_current_user() -> User:
        return user

    from app.main import app

    app.dependency_overrides[get_current_user] = override_get_current_user

    response = await api.get(f"/api/v1/purchases/{purchase.id}")

    assert response.status_code == 200

    data = response.json()

    assert data["points_redeemed"] == 370
    assert data["cashback_earned"] == 130


@pytest.mark.anyio
async def test_purchase_without_receipt_number(api, session_factory):
    async with session_factory() as session:
        user = await create_user(session, "+996700000108")
        purchase = await create_purchase(session, user.id)

        purchase.receipt_number = None
        await session.commit()

    async def override_get_current_user() -> User:
        return user

    from app.main import app

    app.dependency_overrides[get_current_user] = override_get_current_user

    response = await api.get(f"/api/v1/purchases/{purchase.id}")

    assert response.status_code == 200

    data = response.json()

    assert data["receipt_number"] is None


@pytest.mark.anyio
async def test_purchase_without_items_returns_empty_list(api, session_factory):
    async with session_factory() as session:
        user = await create_user(session, "+996700000109")

        purchase = Purchase(
            user_id=user.id,
            source="test",
            external_id=str(uuid4()),
            receipt_number="004513",
            total_amount=Decimal("0.00"),
            paid_amount=Decimal("0.00"),
            purchased_at=datetime(2026, 10, 12, 18, 5, tzinfo=UTC),
            status=PurchaseStatus.CONFIRMED,
        )

        session.add(purchase)
        await session.commit()

    async def override_get_current_user() -> User:
        return user

    from app.main import app

    app.dependency_overrides[get_current_user] = override_get_current_user

    response = await api.get(f"/api/v1/purchases/{purchase.id}")

    assert response.status_code == 200

    data = response.json()

    assert data["items"] == []


@pytest.mark.anyio
async def test_get_purchase_requires_authentication(api, session_factory):
    async with session_factory() as session:
        user = await create_user(session, "+996700000110")
        purchase = await create_purchase(session, user.id)
        await session.commit()

    response = await api.get(f"/api/v1/purchases/{purchase.id}")

    assert response.status_code == 401


@pytest.mark.anyio
async def test_get_purchase_with_invalid_uuid_returns_422(api, session_factory):
    async with session_factory() as session:
        user = await create_user(session, "+996700000111")
        await session.commit()

    async def override_get_current_user() -> User:
        return user

    from app.main import app

    app.dependency_overrides[get_current_user] = override_get_current_user

    response = await api.get("/api/v1/purchases/not-a-valid-uuid")

    assert response.status_code == 422


@pytest.mark.anyio
async def test_purchase_ignores_another_users_bonus_transactions(
    api,
    session_factory,
):
    async with session_factory() as session:
        owner = await create_user(session, "+996700000112")
        another_user = await create_user(session, "+996700000113")

        purchase = await create_purchase(session, owner.id)

        await create_bonus_data(
            session,
            owner.id,
            purchase.id,
        )

        another_account = await create_bonus_data(
            session,
            another_user.id,
            purchase.id,
        )

        foreign_transaction = BonusTransaction(
            account_id=another_account.id,
            purchase_id=purchase.id,
            type=TransactionType.ACCRUAL,
            amount=500,
            status=TransactionStatus.CONFIRMED,
        )

        session.add(foreign_transaction)
        await session.commit()

    async def override_get_current_user() -> User:
        return owner

    from app.main import app

    app.dependency_overrides[get_current_user] = override_get_current_user

    response = await api.get(f"/api/v1/purchases/{purchase.id}")

    assert response.status_code == 200

    data = response.json()

    assert data["points_redeemed"] == 300
    assert data["cashback_earned"] == 109
