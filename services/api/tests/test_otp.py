# tests/test_otp.py
import asyncio
import re
import uuid
from datetime import date, timedelta

import httpx
import pytest
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.core.errors import ApiError
from app.integrations.sms import FakeSmsProvider
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import OtpCode, RefreshToken
from app.modules.auth.tokens import hash_refresh_token
from app.modules.loyalty.models import BonusAccount
from app.modules.users.models import User, UserStatus

pytestmark = [pytest.mark.anyio, pytest.mark.usefixtures("entry_level")]

PHONE = "+996555123456"
FORM = {
    "name": "Айгерим",
    "phone": "0555 123 456",
    "birth_date": "1995-04-12",
    "password": "s3cret-pass",
    "accepted_terms": True,
}

Sessions = async_sessionmaker[AsyncSession]


def last_code(sms: FakeSmsProvider) -> str:
    _, text = sms.sent[-1]
    match = re.search(rf"\b(\d{{{settings.otp_length}}})\b", text)
    assert match, text
    return match.group(1)


def wrong_code(code: str) -> str:
    return f"{(int(code) + 1) % 10**settings.otp_length:0{settings.otp_length}d}"


async def register(api: httpx.AsyncClient, **overrides) -> dict:
    resp = await api.post("/api/v1/auth/register", json={**FORM, **overrides})
    assert resp.status_code == 201, resp.text
    return resp.json()


async def verify(api: httpx.AsyncClient, verification_id: str, code: str) -> httpx.Response:
    return await api.post(
        "/api/v1/auth/otp/verify", json={"verification_id": verification_id, "code": code}
    )


async def shift_otp(sessions: Sessions, verification_id: str, **delta: timedelta) -> None:
    """Сдвигает expires_at / resend_at в прошлое, чтобы не ждать таймеры."""
    values = {column: getattr(OtpCode, column) - shift for column, shift in delta.items()}
    async with sessions() as s:
        await s.execute(
            update(OtpCode).where(OtpCode.id == uuid.UUID(verification_id)).values(**values)
        )
        await s.commit()


def error_code(resp: httpx.Response) -> str:
    return resp.json()["error"]["code"]


# --- register ---------------------------------------------------------------------


async def test_register_sends_sms(api, sms, session_factory):
    body = await register(api)

    assert set(body) == {"verification_id", "phone_masked", "expires_in", "resend_in"}
    uuid.UUID(body["verification_id"])
    assert body["phone_masked"] == "+996 *** *** 456"
    assert body["expires_in"] == settings.otp_ttl_seconds
    assert body["resend_in"] == settings.otp_resend_seconds

    assert len(sms.sent) == 1
    phone, _ = sms.sent[0]
    assert phone == PHONE  # номер нормализован
    code = last_code(sms)

    async with session_factory() as s:
        otp = await s.get(OtpCode, uuid.UUID(body["verification_id"]))
        assert await s.scalar(select(func.count()).select_from(User)) == 0
    # ни код, ни пароль не хранятся в открытом виде
    assert otp.code_hash != code and len(otp.code_hash) == 64
    assert "s3cret-pass" not in str(otp.payload)
    assert otp.payload["password_hash"].startswith("$argon2")


async def test_register_without_password(api, sms, session_factory):
    body = await register(api, password=None)
    async with session_factory() as s:
        otp = await s.get(OtpCode, uuid.UUID(body["verification_id"]))
    assert otp.payload["password_hash"] is None


@pytest.mark.parametrize(
    "overrides",
    [
        {"phone": "+7 999 123 45 67"},
        {"phone": "12345"},
        {"accepted_terms": False},
        {"birth_date": "2999-01-01"},
        {"name": "   "},
        {"password": "short"},
    ],
)
async def test_register_validation(api, sms, overrides):
    resp = await api.post("/api/v1/auth/register", json={**FORM, **overrides})
    assert resp.status_code == 422
    assert error_code(resp) == "VALIDATION_ERROR"
    assert sms.sent == []


async def test_register_resubmit_respects_resend_timer(api, sms):
    await register(api)
    resp = await api.post("/api/v1/auth/register", json=FORM)
    assert resp.status_code == 429
    assert error_code(resp) == "OTP_RESEND_TOO_EARLY"
    assert len(sms.sent) == 1


# --- verify -----------------------------------------------------------------------


async def test_verify_creates_user_account_and_tokens(api, sms, session_factory, entry_level):
    body = await register(api)
    resp = await verify(api, body["verification_id"], last_code(sms))

    assert resp.status_code == 200, resp.text
    tokens = resp.json()
    assert tokens["token_type"] == "bearer"
    assert tokens["expires_in"] == settings.access_token_ttl_minutes * 60
    assert tokens["access_token"] and tokens["refresh_token"]

    async with session_factory() as s:
        user = (await s.execute(select(User).where(User.phone == PHONE))).scalar_one()
        account = (
            await s.execute(select(BonusAccount).where(BonusAccount.user_id == user.id))
        ).scalar_one()
        refresh = (
            await s.execute(select(RefreshToken).where(RefreshToken.user_id == user.id))
        ).scalar_one()
        otp = await s.get(OtpCode, uuid.UUID(body["verification_id"]))

    assert user.name == FORM["name"]
    assert user.birth_date == date(1995, 4, 12)
    assert user.status == UserStatus.ACTIVE
    assert user.password_hash and user.password_hash.startswith("$argon2")
    assert account.level_id == entry_level.id
    assert account.balance == 0
    # refresh-токен хранится только как хеш
    assert refresh.token_hash == hash_refresh_token(tokens["refresh_token"])
    assert refresh.token_hash != tokens["refresh_token"]
    assert otp.consumed_at is not None


async def test_verify_wrong_code_decrements_attempts(api, sms, session_factory):
    body = await register(api)
    bad = wrong_code(last_code(sms))

    first = await verify(api, body["verification_id"], bad)
    second = await verify(api, body["verification_id"], bad)

    assert first.status_code == second.status_code == 400
    assert error_code(first) == "OTP_INVALID"
    assert first.json()["error"]["details"]["attempts_left"] == settings.otp_max_attempts - 1
    assert second.json()["error"]["details"]["attempts_left"] == settings.otp_max_attempts - 2
    async with session_factory() as s:
        assert await s.scalar(select(func.count()).select_from(User)) == 0


async def test_attempts_exceeded_even_with_correct_code(api, sms):
    body = await register(api)
    code = last_code(sms)
    for _ in range(settings.otp_max_attempts):
        resp = await verify(api, body["verification_id"], wrong_code(code))
        assert error_code(resp) == "OTP_INVALID"
    assert resp.json()["error"]["details"]["attempts_left"] == 0

    resp = await verify(api, body["verification_id"], code)
    assert resp.status_code == 400
    assert error_code(resp) == "OTP_ATTEMPTS_EXCEEDED"


async def test_verify_expired_code(api, sms, session_factory):
    body = await register(api)
    await shift_otp(
        session_factory,
        body["verification_id"],
        expires_at=timedelta(seconds=settings.otp_ttl_seconds + 1),
    )

    resp = await verify(api, body["verification_id"], last_code(sms))
    assert resp.status_code == 400
    assert error_code(resp) == "OTP_EXPIRED"


async def test_code_cannot_be_reused(api, sms):
    body = await register(api)
    code = last_code(sms)
    assert (await verify(api, body["verification_id"], code)).status_code == 200

    resp = await verify(api, body["verification_id"], code)
    assert resp.status_code == 404
    assert error_code(resp) == "OTP_NOT_FOUND"


async def test_parallel_verify_only_one_succeeds(api, sms, session_factory):
    """SELECT ... FOR UPDATE: две одновременные попытки не проходят обе."""
    body = await register(api)
    code = last_code(sms)

    results = await asyncio.gather(
        verify(api, body["verification_id"], code),
        verify(api, body["verification_id"], code),
    )

    assert sorted(r.status_code for r in results) == [200, 404]
    async with session_factory() as s:
        assert await s.scalar(select(func.count()).select_from(User)) == 1
        assert await s.scalar(select(func.count()).select_from(BonusAccount)) == 1


async def test_verify_unknown_id(api):
    resp = await verify(api, str(uuid.uuid4()), "1234")
    assert resp.status_code == 404
    assert error_code(resp) == "OTP_NOT_FOUND"


# --- resend -----------------------------------------------------------------------


async def test_resend_too_early(api, sms):
    body = await register(api)
    resp = await api.post(
        "/api/v1/auth/otp/resend", json={"verification_id": body["verification_id"]}
    )

    assert resp.status_code == 429
    assert error_code(resp) == "OTP_RESEND_TOO_EARLY"
    retry_after = resp.json()["error"]["details"]["retry_after"]
    assert 0 < retry_after <= settings.otp_resend_seconds
    assert resp.headers["Retry-After"] == str(retry_after)
    assert len(sms.sent) == 1


async def test_old_code_invalid_after_resend(api, sms, session_factory):
    body = await register(api)
    old_code = last_code(sms)
    await shift_otp(
        session_factory,
        body["verification_id"],
        resend_at=timedelta(seconds=settings.otp_resend_seconds + 1),
    )

    resp = await api.post(
        "/api/v1/auth/otp/resend", json={"verification_id": body["verification_id"]}
    )
    assert resp.status_code == 200, resp.text
    new = resp.json()
    assert new["verification_id"] != body["verification_id"]
    assert new["phone_masked"] == body["phone_masked"]
    assert len(sms.sent) == 2
    new_code = last_code(sms)

    old = await verify(api, body["verification_id"], old_code)
    assert old.status_code == 404
    assert error_code(old) == "OTP_NOT_FOUND"

    # по новому verification_id старый код тоже не подходит (если коды не совпали)
    if new_code != old_code:
        stale = await verify(api, new["verification_id"], old_code)
        assert error_code(stale) == "OTP_INVALID"

    assert (await verify(api, new["verification_id"], new_code)).status_code == 200


async def test_resend_after_attempts_exceeded(api, sms, session_factory):
    body = await register(api)
    code = last_code(sms)
    for _ in range(settings.otp_max_attempts):
        await verify(api, body["verification_id"], wrong_code(code))
    await shift_otp(
        session_factory,
        body["verification_id"],
        resend_at=timedelta(seconds=settings.otp_resend_seconds + 1),
    )

    resp = await api.post(
        "/api/v1/auth/otp/resend", json={"verification_id": body["verification_id"]}
    )
    assert resp.status_code == 200
    ok = await verify(api, resp.json()["verification_id"], last_code(sms))
    assert ok.status_code == 200


# --- занятый номер ----------------------------------------------------------------


async def test_register_phone_already_registered(api, sms):
    body = await register(api)
    assert (await verify(api, body["verification_id"], last_code(sms))).status_code == 200

    resp = await api.post("/api/v1/auth/register", json={**FORM, "phone": "+996 555 123 456"})
    assert resp.status_code == 409
    assert error_code(resp) == "PHONE_ALREADY_REGISTERED"


async def test_verify_phone_taken_meanwhile(api, sms, session_factory):
    """Номер заняли между отправкой кода и подтверждением — срабатывает UNIQUE(phone)."""
    body = await register(api)
    code = last_code(sms)
    async with session_factory() as s:
        s.add(User(phone=PHONE, name="Другой", birth_date=date(1990, 1, 1)))
        await s.commit()

    resp = await verify(api, body["verification_id"], code)
    assert resp.status_code == 409
    assert error_code(resp) == "PHONE_ALREADY_REGISTERED"

    async with session_factory() as s:
        otp = await s.get(OtpCode, uuid.UUID(body["verification_id"]))
        assert await s.scalar(select(func.count()).select_from(BonusAccount)) == 0
    assert otp.consumed_at is not None


# --- get_current_user ---------------------------------------------------------------


async def _tokens(api: httpx.AsyncClient, sms: FakeSmsProvider) -> dict:
    body = await register(api)
    resp = await verify(api, body["verification_id"], last_code(sms))
    return resp.json()


def _bearer(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


async def test_access_token_passes_get_current_user(api, sms, session_factory):
    tokens = await _tokens(api, sms)
    async with session_factory() as s:
        user = await get_current_user(_bearer(tokens["access_token"]), s)
    assert user.phone == PHONE


@pytest.mark.parametrize("token", [None, "garbage", "refresh"])
async def test_get_current_user_rejects_bad_token(api, sms, session_factory, token):
    tokens = await _tokens(api, sms)
    credentials = None
    if token == "garbage":
        credentials = _bearer("not-a-jwt")
    elif token == "refresh":
        credentials = _bearer(tokens["refresh_token"])

    async with session_factory() as s:
        with pytest.raises(ApiError) as exc:
            await get_current_user(credentials, s)
    assert exc.value.status_code == 401
    assert exc.value.code == "NOT_AUTHENTICATED"


@pytest.mark.parametrize("status", [UserStatus.BLOCKED, UserStatus.DELETED])
async def test_get_current_user_blocked(api, sms, session_factory, status):
    tokens = await _tokens(api, sms)
    async with session_factory() as s:
        await s.execute(update(User).where(User.phone == PHONE).values(status=status))
        await s.commit()
        with pytest.raises(ApiError) as exc:
            await get_current_user(_bearer(tokens["access_token"]), s)
    assert exc.value.status_code == 403
    assert exc.value.code == "USER_BLOCKED"
