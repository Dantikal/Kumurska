import asyncio
import os
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app import models  # noqa: F401  — регистрирует все таблицы
from app.core.database import Base, get_db
from app.integrations.sms import FakeSmsProvider, get_sms_provider
from app.main import app
from app.modules.loyalty.models import LoyaltyLevel

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://kumurska:kumurska@localhost:5433/kumurska_test",
)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


# --- база данных ----------------------------------------------------------------


def _make_engine() -> AsyncEngine:
    # NullPool: соединения не переживают event loop теста
    return create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)


async def _recreate_schema() -> None:
    engine = _make_engine()
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
    finally:
        await engine.dispose()


@pytest.fixture(scope="session")
def _test_schema() -> None:
    """Пересоздаёт схему в тестовой базе один раз за сессию.

    Локально без PostgreSQL тесты с базой пропускаются, в CI — падают.
    """
    try:
        asyncio.run(_recreate_schema())
    except (OSError, ConnectionError) as exc:
        if os.environ.get("CI"):
            raise
        pytest.skip(f"Нет тестовой базы {TEST_DATABASE_URL}: {exc}")


@pytest.fixture
async def db_engine(_test_schema: None) -> AsyncIterator[AsyncEngine]:
    engine = _make_engine()
    yield engine
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {tables} CASCADE"))
    await engine.dispose()


@pytest.fixture
def session_factory(db_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(db_engine, expire_on_commit=False)


@pytest.fixture
async def entry_level(session_factory: async_sessionmaker[AsyncSession]) -> LoyaltyLevel:
    """Начальный уровень (в реальной базе его создаёт сид-миграция)."""
    async with session_factory() as session:
        level = LoyaltyLevel(
            name="Базовый",
            cashback_percent=Decimal("3.00"),
            threshold=Decimal("0"),
            effective_from=datetime(2026, 1, 1, tzinfo=UTC),
        )
        session.add(level)
        await session.commit()
        return level


@pytest.fixture
def sms() -> FakeSmsProvider:
    return FakeSmsProvider()


@pytest.fixture
async def api(
    session_factory: async_sessionmaker[AsyncSession], sms: FakeSmsProvider
) -> AsyncIterator[httpx.AsyncClient]:
    async def override_get_db() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_sms_provider] = lambda: sms
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _clear_overrides() -> Iterator[None]:
    yield
    app.dependency_overrides.clear()
