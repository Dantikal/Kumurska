# tests/test_login.py
import httpx
import pytest
from sqlalchemy import func, select, update

from app.integrations.sms import FakeSmsProvider
from app.modules.auth.models import RefreshToken
from app.modules.users.models import User, UserStatus
from tests.test_otp import FORM, PHONE, error_code, last_code, register, verify

pytestmark = [pytest.mark.anyio, pytest.mark.usefixtures("entry_level")]

PASSWORD = FORM["password"]


async def login(api: httpx.AsyncClient, phone: str = PHONE, password: str = PASSWORD):
    return await api.post("/api/v1/auth/login", json={"phone": phone, "password": password})


async def complete_registration(api: httpx.AsyncClient, sms: FakeSmsProvider, **overrides) -> None:
    body = await register(api, **overrides)
    resp = await verify(api, body["verification_id"], last_code(sms))
    assert resp.status_code == 200, resp.text


async def set_status(session_factory, status: UserStatus) -> None:
    async with session_factory() as s:
        await s.execute(update(User).where(User.phone == PHONE).values(status=status))
        await s.commit()


async def test_login_returns_working_tokens(api, sms, session_factory):
    await complete_registration(api, sms)

    resp = await login(api)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body) == {"access_token", "refresh_token", "token_type", "expires_in"}
    assert body["token_type"] == "bearer"

    profile = await api.get(
        "/api/v1/users/me", headers={"Authorization": f"Bearer {body['access_token']}"}
    )
    assert profile.status_code == 200, profile.text

    async with session_factory() as s:
        # Один токен выдан при подтверждении кода, второй при входе.
        assert await s.scalar(select(func.count()).select_from(RefreshToken)) == 2


@pytest.mark.parametrize("phone", ["+996555123456", "996555123456", "0555 123 456", "555123456"])
async def test_login_accepts_phone_formats(api, sms, phone):
    await complete_registration(api, sms)

    assert (await login(api, phone=phone)).status_code == 200


async def test_login_wrong_password(api, sms):
    await complete_registration(api, sms)

    resp = await login(api, password="wrong-pass")

    assert resp.status_code == 401
    assert error_code(resp) == "INVALID_CREDENTIALS"


async def test_login_issues_no_token_on_failure(api, sms, session_factory):
    await complete_registration(api, sms)

    await login(api, password="wrong-pass")

    async with session_factory() as s:
        assert await s.scalar(select(func.count()).select_from(RefreshToken)) == 1


async def test_login_unknown_phone_looks_like_wrong_password(api, sms):
    await complete_registration(api, sms)

    unknown = await login(api, phone="+996700000000")
    wrong = await login(api, password="wrong-pass")

    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json() == wrong.json()


async def test_login_user_without_password(api, sms):
    await complete_registration(api, sms, password=None)

    resp = await login(api)

    assert resp.status_code == 401
    assert error_code(resp) == "INVALID_CREDENTIALS"


async def test_login_before_otp_confirmation(api):
    await register(api)

    resp = await login(api)

    assert resp.status_code == 401
    assert error_code(resp) == "INVALID_CREDENTIALS"


@pytest.mark.parametrize("status", [UserStatus.BLOCKED, UserStatus.DELETED])
async def test_login_blocked_user(api, sms, session_factory, status):
    await complete_registration(api, sms)
    await set_status(session_factory, status)

    resp = await login(api)

    assert resp.status_code == 403
    assert error_code(resp) == "USER_BLOCKED"


async def test_login_blocked_status_hidden_without_password(api, sms, session_factory):
    await complete_registration(api, sms)
    await set_status(session_factory, UserStatus.BLOCKED)

    resp = await login(api, password="wrong-pass")

    assert resp.status_code == 401
    assert error_code(resp) == "INVALID_CREDENTIALS"


@pytest.mark.parametrize(
    "payload",
    [
        {"phone": "123", "password": PASSWORD},
        {"phone": PHONE, "password": ""},
        {"phone": PHONE, "password": "x" * 129},
        {"phone": PHONE},
    ],
)
async def test_login_validation(api, payload):
    resp = await api.post("/api/v1/auth/login", json=payload)

    assert resp.status_code == 422
    assert error_code(resp) == "VALIDATION_ERROR"
