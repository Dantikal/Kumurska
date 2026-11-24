from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.modules.auth.dependencies import get_current_user
from app.modules.loyalty import service as loyalty_service
from app.modules.loyalty.models import (
    BonusAccount,
    BonusTransaction,
    LoyaltyLevel,
    TransactionStatus,
    TransactionType,
)
from app.modules.purchases import repository
from app.modules.purchases.models import Purchase, PurchaseItem, PurchaseStatus
from app.modules.purchases.schemas import PurchaseCreate, PurchaseItemCreate
from app.modules.purchases.service import confirm_purchase, record_purchase
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
            amount=-300,
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
                amount=-100,
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
                amount=-70,
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


@pytest.mark.anyio
async def test_confirm_purchase_applies_loyalty_rewards(session_factory):
    async with session_factory() as session:
        user = await create_user(session, "+996700000120")

        level = LoyaltyLevel(
            name="Тестовый уровень",
            cashback_percent=Decimal("5.00"),
            threshold=Decimal("0"),
            effective_from=datetime(2026, 1, 1, tzinfo=UTC),
        )
        session.add(level)
        await session.flush()

        account = BonusAccount(
            user_id=user.id,
            level_id=level.id,
            balance=500,
            accumulated_total=Decimal("0"),
        )
        session.add(account)

        purchase = Purchase(
            user_id=user.id,
            source="test",
            external_id=str(uuid4()),
            receipt_number="004520",
            total_amount=Decimal("2480.00"),
            paid_amount=Decimal("2180.00"),
            points_to_redeem=300,
            purchased_at=datetime(2026, 10, 12, 18, 5, tzinfo=UTC),
            status=PurchaseStatus.PENDING,
        )
        session.add(purchase)
        await session.flush()

        await confirm_purchase(session, purchase.id)

        assert purchase.status == PurchaseStatus.CONFIRMED
        assert account.balance == 309
        assert account.accumulated_total == Decimal("2180.00")

        await session.commit()


@pytest.mark.anyio
async def test_confirm_purchase_twice_does_not_duplicate_rewards(session_factory):
    async with session_factory() as session:
        user = await create_user(session, "+996700000121")

        level = LoyaltyLevel(
            name="Тестовый уровень",
            cashback_percent=Decimal("5.00"),
            threshold=Decimal("0"),
            effective_from=datetime(2026, 1, 1, tzinfo=UTC),
        )
        session.add(level)
        await session.flush()

        account = BonusAccount(
            user_id=user.id,
            level_id=level.id,
            balance=500,
            accumulated_total=Decimal("0"),
        )
        session.add(account)

        purchase = Purchase(
            user_id=user.id,
            source="test",
            external_id=str(uuid4()),
            total_amount=Decimal("2480.00"),
            paid_amount=Decimal("2180.00"),
            points_to_redeem=300,
            purchased_at=datetime(2026, 10, 12, 18, 5, tzinfo=UTC),
            status=PurchaseStatus.PENDING,
        )
        session.add(purchase)
        await session.flush()

        await confirm_purchase(session, purchase.id)
        await confirm_purchase(session, purchase.id)

        assert account.balance == 309
        assert account.accumulated_total == Decimal("2180.00")

        transactions = await loyalty_service.repository.get_purchase_transactions(
            session,
            purchase.id,
            user.id,
        )

        assert len(transactions) == 2

        await session.commit()


@pytest.mark.anyio
async def test_refunded_purchase_cannot_be_confirmed(session_factory):
    async with session_factory() as session:
        user = await create_user(session, "+996700000122")

        level = LoyaltyLevel(
            name="Тестовый уровень",
            cashback_percent=Decimal("5.00"),
            threshold=Decimal("0"),
            effective_from=datetime(2026, 1, 1, tzinfo=UTC),
        )
        session.add(level)
        await session.flush()

        account = BonusAccount(
            user_id=user.id,
            level_id=level.id,
            balance=500,
            accumulated_total=Decimal("0"),
        )
        session.add(account)

        purchase = Purchase(
            user_id=user.id,
            source="test",
            external_id=str(uuid4()),
            total_amount=Decimal("1000.00"),
            paid_amount=Decimal("1000.00"),
            points_to_redeem=0,
            purchased_at=datetime(2026, 10, 12, tzinfo=UTC),
            status=PurchaseStatus.REFUNDED,
        )
        session.add(purchase)
        await session.flush()

        with pytest.raises(ApiError) as exc_info:
            await confirm_purchase(session, purchase.id)

        assert exc_info.value.code == "PURCHASE_CANNOT_BE_CONFIRMED"
        assert account.balance == 500
        assert account.accumulated_total == Decimal("0")

        await session.rollback()


@pytest.mark.anyio
async def test_record_purchase_creates_pending_purchase(session_factory):
    async with session_factory() as session:
        user = await create_user(session, "+996700000123")

        data = PurchaseCreate(
            source="test",
            external_id="external-001",
            user_id=user.id,
            items=[
                {
                    "name": "Тестовый товар",
                    "quantity": 2,
                    "unit_price": Decimal("500.00"),
                    "line_total": Decimal("1000.00"),
                }
            ],
            total_amount=Decimal("1000.00"),
            paid_amount=Decimal("1000.00"),
            purchased_at=datetime(2026, 10, 12, tzinfo=UTC),
        )

        purchase = await record_purchase(session, data)

        assert purchase.status == PurchaseStatus.PENDING
        assert purchase.source == "test"
        assert purchase.external_id == "external-001"
        assert purchase.points_to_redeem == 0

        items = await repository.get_purchase_items(session, purchase.id)

        assert len(items) == 1
        assert items[0].name == "Тестовый товар"

        await session.commit()


@pytest.mark.anyio
async def test_record_purchase_does_not_create_duplicate(session_factory):
    async with session_factory() as session:
        user = await create_user(session, "+996700000124")

        data = PurchaseCreate(
            source="test",
            external_id="external-duplicate-001",
            user_id=user.id,
            items=[
                {
                    "name": "Тестовый товар",
                    "quantity": 1,
                    "unit_price": Decimal("1000.00"),
                    "line_total": Decimal("1000.00"),
                }
            ],
            total_amount=Decimal("1000.00"),
            paid_amount=Decimal("1000.00"),
            purchased_at=datetime(2026, 10, 12, tzinfo=UTC),
        )

        first_purchase = await record_purchase(session, data)
        second_purchase = await record_purchase(session, data)

        assert first_purchase.id == second_purchase.id

        items = await repository.get_purchase_items(
            session,
            first_purchase.id,
        )
        assert len(items) == 1

        await session.commit()



@pytest.mark.anyio
async def test_cashback_rounds_down_to_integer(session_factory):
    async with session_factory() as session:
        user = await create_user(session, "+996700000125")

        level = LoyaltyLevel(
            name="Тестовый уровень",
            cashback_percent=Decimal("5.00"),
            threshold=Decimal("0"),
            effective_from=datetime(2026, 1, 1, tzinfo=UTC),
        )
        session.add(level)
        await session.flush()

        account = BonusAccount(
            user_id=user.id,
            level_id=level.id,
            balance=0,
            accumulated_total=Decimal("0"),
        )
        session.add(account)

        purchase = Purchase(
            user_id=user.id,
            source="test",
            external_id=str(uuid4()),
            total_amount=Decimal("200.00"),
            paid_amount=Decimal("199.99"),
            points_to_redeem=0,
            purchased_at=datetime(2026, 10, 12, tzinfo=UTC),
            status=PurchaseStatus.PENDING,
        )
        session.add(purchase)
        await session.flush()

        await confirm_purchase(session, purchase.id)

        assert account.balance == 9
        assert account.accumulated_total == Decimal("199.99")

        transactions = await loyalty_service.repository.get_purchase_transactions(
            session,
            purchase.id,
            user.id,
        )

        assert len(transactions) == 1
        assert transactions[0].type == TransactionType.ACCRUAL
        assert transactions[0].amount == 9

        await session.commit()



@pytest.mark.anyio
async def test_cashback_uses_level_version_valid_on_purchase_date(session_factory):
    async with session_factory() as session:
        user = await create_user(session, "+996700000126")

        old_level = LoyaltyLevel(
            name="Старый уровень",
            cashback_percent=Decimal("3.00"),
            threshold=Decimal("0"),
            effective_from=datetime(2026, 1, 1, tzinfo=UTC),
        )
        new_level = LoyaltyLevel(
            name="Обновлённый уровень",
            cashback_percent=Decimal("7.00"),
            threshold=Decimal("0"),
            effective_from=datetime(2026, 11, 1, tzinfo=UTC),
        )
        session.add_all([old_level, new_level])
        await session.flush()

        account = BonusAccount(
            user_id=user.id,
            level_id=new_level.id,
            balance=0,
            accumulated_total=Decimal("0"),
        )
        session.add(account)

        purchase = Purchase(
            user_id=user.id,
            source="test",
            external_id=str(uuid4()),
            total_amount=Decimal("1000.00"),
            paid_amount=Decimal("1000.00"),
            points_to_redeem=0,
            purchased_at=datetime(2026, 10, 12, tzinfo=UTC),
            status=PurchaseStatus.PENDING,
        )
        session.add(purchase)
        await session.flush()

        await confirm_purchase(session, purchase.id)

        assert account.balance == 30

        transactions = await loyalty_service.repository.get_purchase_transactions(
            session,
            purchase.id,
            user.id,
        )

        assert len(transactions) == 1
        assert transactions[0].amount == 30

        await session.commit()



@pytest.mark.anyio
async def test_purchase_with_redemption_and_zero_cashback(session_factory):
    async with session_factory() as session:
        user = await create_user(session, "+996700000127")

        level = LoyaltyLevel(
            name="Тестовый уровень",
            cashback_percent=Decimal("0.00"),
            threshold=Decimal("0"),
            effective_from=datetime(2026, 1, 1, tzinfo=UTC),
        )
        session.add(level)
        await session.flush()

        account = BonusAccount(
            user_id=user.id,
            level_id=level.id,
            balance=500,
            accumulated_total=Decimal("0"),
        )
        session.add(account)

        purchase = Purchase(
            user_id=user.id,
            source="test",
            external_id=str(uuid4()),
            total_amount=Decimal("1000.00"),
            paid_amount=Decimal("700.00"),
            points_to_redeem=300,
            purchased_at=datetime(2026, 10, 12, tzinfo=UTC),
            status=PurchaseStatus.PENDING,
        )
        session.add(purchase)
        await session.flush()

        await confirm_purchase(session, purchase.id)

        assert purchase.status == PurchaseStatus.CONFIRMED
        assert account.balance == 200
        assert account.accumulated_total == Decimal("700.00")

        transactions = await loyalty_service.repository.get_purchase_transactions(
            session,
            purchase.id,
            user.id,
        )

        assert len(transactions) == 1
        assert transactions[0].type == TransactionType.REDEMPTION
        assert transactions[0].amount == -300

        await session.commit()



@pytest.mark.anyio
async def test_confirm_purchase_without_bonus_account(session_factory):
    async with session_factory() as session:
        user = await create_user(session, "+996700000128")

        purchase = Purchase(
            user_id=user.id,
            source="test",
            external_id=str(uuid4()),
            total_amount=Decimal("1000.00"),
            paid_amount=Decimal("1000.00"),
            points_to_redeem=0,
            purchased_at=datetime(2026, 10, 12, tzinfo=UTC),
            status=PurchaseStatus.PENDING,
        )
        session.add(purchase)
        await session.flush()

        with pytest.raises(ApiError) as exc_info:
            await confirm_purchase(session, purchase.id)

        assert exc_info.value.code == "BONUS_ACCOUNT_NOT_FOUND"
        assert purchase.status == PurchaseStatus.PENDING

        await session.rollback()



@pytest.mark.anyio
async def test_failed_rewards_do_not_confirm_purchase(
    session_factory,
    monkeypatch,
):
    async with session_factory() as session:
        user = await create_user(session, "+996700000129")

        level = LoyaltyLevel(
            name="Тестовый уровень",
            cashback_percent=Decimal("5.00"),
            threshold=Decimal("0"),
            effective_from=datetime(2026, 1, 1, tzinfo=UTC),
        )
        session.add(level)
        await session.flush()

        account = BonusAccount(
            user_id=user.id,
            level_id=level.id,
            balance=500,
            accumulated_total=Decimal("0"),
        )
        session.add(account)

        purchase = Purchase(
            user_id=user.id,
            source="test",
            external_id=str(uuid4()),
            total_amount=Decimal("1000.00"),
            paid_amount=Decimal("1000.00"),
            points_to_redeem=100,
            purchased_at=datetime(2026, 10, 12, tzinfo=UTC),
            status=PurchaseStatus.PENDING,
        )
        session.add(purchase)
        await session.flush()

        async def fail_rewards(**kwargs):
            raise ApiError(
                500,
                "REWARDS_FAILED",
                "Ошибка обработки бонусов",
            )

        monkeypatch.setattr(
            loyalty_service,
            "apply_purchase_rewards",
            fail_rewards,
        )

        with pytest.raises(ApiError) as exc_info:
            await confirm_purchase(session, purchase.id)

        assert exc_info.value.code == "REWARDS_FAILED"
        assert purchase.status == PurchaseStatus.PENDING
        assert account.balance == 500
        assert account.accumulated_total == Decimal("0")

        await session.rollback()



@pytest.mark.anyio
async def test_database_rollback_after_rewards_failure(
    session_factory,
    monkeypatch,
):
    async with session_factory() as session:
        user = await create_user(session, "+996700000130")

        level = LoyaltyLevel(
            name="Тестовый уровень",
            cashback_percent=Decimal("5.00"),
            threshold=Decimal("0"),
            effective_from=datetime(2026, 1, 1, tzinfo=UTC),
        )
        session.add(level)
        await session.flush()

        account = BonusAccount(
            user_id=user.id,
            level_id=level.id,
            balance=500,
            accumulated_total=Decimal("0"),
        )
        session.add(account)

        purchase = Purchase(
            user_id=user.id,
            source="test",
            external_id=str(uuid4()),
            total_amount=Decimal("1000.00"),
            paid_amount=Decimal("1000.00"),
            points_to_redeem=100,
            purchased_at=datetime(2026, 10, 12, tzinfo=UTC),
            status=PurchaseStatus.PENDING,
        )
        session.add(purchase)
        await session.flush()

        purchase_id = purchase.id
        user_id = user.id

        await session.commit()

        original_apply = loyalty_service.apply_purchase_rewards

        async def fail_after_rewards(**kwargs):
            await original_apply(**kwargs)
            raise ApiError(
                500,
                "REWARDS_FAILED",
                "Ошибка после обработки бонусов",
            )

        monkeypatch.setattr(
            loyalty_service,
            "apply_purchase_rewards",
            fail_after_rewards,
        )

        with pytest.raises(ApiError):
            await confirm_purchase(session, purchase_id)

        await session.rollback()

        saved_purchase = await repository.get_purchase(
            session,
            purchase_id,
            user_id,
        )
        saved_account = await loyalty_service.repository.get_account_with_level(
            session,
            user_id,
        )
        transactions = await loyalty_service.repository.get_purchase_transactions(
            session,
            purchase_id,
            user_id,
        )

        assert saved_purchase.status == PurchaseStatus.PENDING
        assert saved_account[0].balance == 500
        assert saved_account[0].accumulated_total == Decimal("0")
        assert transactions == []

        await session.commit()



@pytest.mark.anyio
async def test_record_purchase_saves_points_to_redeem(session_factory):
    async with session_factory() as session:
        user = await create_user(session, "+996700000131")

        data = PurchaseCreate(
            source="test",
            external_id=str(uuid4()),
            user_id=user.id,
            items=[
                PurchaseItemCreate(
                    name="Тестовый товар",
                    quantity=1,
                    unit_price=Decimal("1000.00"),
                    line_total=Decimal("1000.00"),
                )
            ],
            total_amount=Decimal("1000.00"),
            paid_amount=Decimal("700.00"),
            points_redeemed=300,
            purchased_at=datetime(2026, 10, 12, tzinfo=UTC),
        )

        purchase = await record_purchase(session, data)

        assert purchase.points_to_redeem == 300

        await session.commit()
