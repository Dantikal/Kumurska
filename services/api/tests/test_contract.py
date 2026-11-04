# tests/test_contract.py
from fastapi.testclient import TestClient

from app import models  # noqa: F401  — регистрирует все таблицы
from app.core.database import Base
from app.main import app

client = TestClient(app)


def test_all_methods_present():
    paths = app.openapi()["paths"]
    expected = {
        "/api/v1/users/me": {"get", "patch"},
        "/api/v1/loyalty/account": {"get"},
        "/api/v1/loyalty/levels": {"get"},
        "/api/v1/loyalty/transactions": {"get"},
        "/api/v1/purchases/{id}": {"get"},
        "/api/v1/content/promotions": {"get"},
        "/api/v1/content/promotions/{id}": {"get"},
        "/api/v1/content/events": {"get"},
    }
    for path, methods in expected.items():
        assert path in paths, f"Нет пути {path}"
        for m in methods:
            assert m in paths[path], f"Нет метода {m} {path}"


def test_stub_returns_501():
    resp = client.get("/api/v1/users/me")
    assert resp.status_code == 501
    assert resp.json()["error"]["code"] == "NOT_IMPLEMENTED"


def test_all_tables_registered():
    expected = {
        "users",
        "loyalty_levels",
        "bonus_accounts",
        "bonus_transactions",
        "purchases",
        "purchase_items",
        "promotions",
        "events",
    }
    assert expected.issubset(set(Base.metadata.tables.keys()))
