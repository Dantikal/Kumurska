from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.core.errors import ApiError, register_error_handlers


class Payload(BaseModel):
    code: str


def make_client() -> TestClient:
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/api-error")
    async def api_error() -> None:
        raise ApiError(400, "OTP_INVALID", "Неверный код", {"attempts_left": 3})

    @app.post("/validated")
    async def validated(_: Payload) -> None:
        return None

    return TestClient(app)


def test_api_error_format() -> None:
    response = make_client().get("/api-error")

    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "code": "OTP_INVALID",
            "message": "Неверный код",
            "details": {"attempts_left": 3},
        }
    }


def test_validation_error_format() -> None:
    response = make_client().post("/validated", json={})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_not_found_format() -> None:
    response = make_client().get("/missing")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "HTTP_404"
