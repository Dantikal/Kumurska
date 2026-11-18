# tests/test_refresh.py
"""Сессии устройств, обновление токенов и выход (US-25)."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import httpx
import jwt
import pytest
from sqlalchemy import select, update

from app.core.config import settings
from app.modules.auth import service
from app.modules.auth.models import RefreshToken, Session
from app.modules.auth.tokens import JWT_ALGORITHM, hash_refresh_token
from app.modules.users.models import User, UserStatus
from tests.conftest import DEVICE_ID
from tests.test_login import complete_registration, login, set_status
from tests.test_otp import FORM, PHONE, error_code, last_code, register

pytestmark = [pytest.mark.anyio, pytest.mark.usefixtures("entry_level")]

OTHER_DEVICE = "0d7c9a52-3b6e-4e8f-8a41-5c2f9e7b1d33"


async def signed_in(api: httpx.AsyncClient, sms, device_id: str = DEVICE_ID) -> dict:
    await complete_registration(api, sms)
    resp = await login(api) if device_id == DEVICE_ID else await login_from(api, device_id)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def login_from(api: httpx.AsyncClient, device_id: str) -> httpx.Response:
    return await api.post(
        "/api/v1/auth/login",
        json={"phone": PHONE, "password": FORM["password"]},
        headers={"X-Device-Id": device_id},
    )


async def refresh(api: httpx.AsyncClient, token: str, device_id: str = DEVICE_ID) -> httpx.Response:
    return await api.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": token},
        headers={"X-Device-Id": device_id},
    )


async def me(api: httpx.AsyncClient, access: str) -> httpx.Response:
    return await api.get("/api/v1/users/me", headers={"Authorization": f"Bearer {access}"})


async def logout(api: httpx.AsyncClient, access: str) -> httpx.Response:
    return await api.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {access}"})


def assert_session_expired(resp: httpx.Response) -> None:
    assert resp.status_code == 401, resp.text
    assert error_code(resp) == "SESSION_EXPIRED"


def sid(access: str) -> uuid.UUID:
    payload = jwt.decode(access, settings.jwt_secret, algorithms=[JWT_ALGORITHM])
    return uuid.UUID(payload["sid"])


# --- refresh ----------------------------------------------------------------------


async def test_refresh_issues_new_pair_and_old_stops_working(api, sms, session_factory):
    tokens = await signed_in(api, sms)

    resp = await refresh(api, tokens["refresh_token"])

    assert resp.status_code == 200, resp.text
    new = resp.json()
    assert set(new) == {"access_token", "refresh_token", "token_type", "expires_in"}
    assert new["refresh_token"] != tokens["refresh_token"]
    assert sid(new["access_token"]) == sid(tokens["access_token"])
    assert (await me(api, new["access_token"])).status_code == 200

    async with session_factory() as s:
        old = await s.scalar(
            select(RefreshToken).where(
                RefreshToken.token_hash == hash_refresh_token(tokens["refresh_token"])
            )
        )
        auth_session = await s.get(Session, sid(tokens["access_token"]))
    assert old.used_at is not None
    assert auth_session.last_used_at >= old.used_at

    assert_session_expired(await refresh(api, tokens["refresh_token"]))


async def test_reused_refresh_revokes_whole_session(api, sms, session_factory):
    tokens = await signed_in(api, sms)
    new = (await refresh(api, tokens["refresh_token"])).json()

    # Старый токен предъявлен повторно — признак кражи.
    assert_session_expired(await refresh(api, tokens["refresh_token"]))

    assert_session_expired(await refresh(api, new["refresh_token"]))
    assert_session_expired(await me(api, new["access_token"]))
    async with session_factory() as s:
        assert (await s.get(Session, sid(new["access_token"]))).revoked_at is not None


async def test_expired_refresh(api, sms, session_factory):
    tokens = await signed_in(api, sms)
    async with session_factory() as s:
        await s.execute(
            update(RefreshToken)
            .where(RefreshToken.token_hash == hash_refresh_token(tokens["refresh_token"]))
            .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )
        await s.commit()

    assert_session_expired(await refresh(api, tokens["refresh_token"]))


async def test_refresh_ttl_is_30_days(api, sms, session_factory):
    tokens = await signed_in(api, sms)
    async with session_factory() as s:
        token = await s.scalar(
            select(RefreshToken).where(
                RefreshToken.token_hash == hash_refresh_token(tokens["refresh_token"])
            )
        )
    assert token.expires_at - token.created_at == pytest.approx(
        timedelta(days=settings.refresh_token_ttl_days), abs=timedelta(seconds=5)
    )


async def test_refresh_from_other_device(api, sms):
    tokens = await signed_in(api, sms)

    assert_session_expired(await refresh(api, tokens["refresh_token"], OTHER_DEVICE))

    # Чужое устройство не сжигает токен владельца.
    assert (await refresh(api, tokens["refresh_token"])).status_code == 200


@pytest.mark.parametrize("token", ["unknown-token", "x"])
async def test_refresh_unknown_token(api, sms, token):
    await signed_in(api, sms)

    assert_session_expired(await refresh(api, token))


@pytest.mark.parametrize("status", [UserStatus.BLOCKED, UserStatus.DELETED])
async def test_refresh_blocked_user(api, sms, session_factory, status):
    tokens = await signed_in(api, sms)
    await set_status(session_factory, status)

    resp = await refresh(api, tokens["refresh_token"])

    assert resp.status_code == 403
    assert error_code(resp) == "USER_BLOCKED"


async def test_parallel_refresh_only_one_succeeds(api, sms):
    tokens = await signed_in(api, sms)

    responses = await asyncio.gather(
        refresh(api, tokens["refresh_token"]), refresh(api, tokens["refresh_token"])
    )

    assert sorted(r.status_code for r in responses) == [200, 401]
    failed = next(r for r in responses if r.status_code == 401)
    assert error_code(failed) == "SESSION_EXPIRED"


# --- logout -----------------------------------------------------------------------


async def test_logout_revokes_session_immediately(api, sms):
    tokens = await signed_in(api, sms)
    assert (await me(api, tokens["access_token"])).status_code == 200

    resp = await logout(api, tokens["access_token"])

    assert resp.status_code == 204
    assert resp.content == b""
    assert_session_expired(await me(api, tokens["access_token"]))
    assert_session_expired(await refresh(api, tokens["refresh_token"]))


async def test_logout_is_idempotent(api, sms):
    tokens = await signed_in(api, sms)

    assert (await logout(api, tokens["access_token"])).status_code == 204
    assert (await logout(api, tokens["access_token"])).status_code == 204


async def test_logout_keeps_other_devices(api, sms):
    tokens = await signed_in(api, sms)
    other = (await login_from(api, OTHER_DEVICE)).json()

    await logout(api, tokens["access_token"])

    assert (await me(api, other["access_token"])).status_code == 200
    assert (await refresh(api, other["refresh_token"], OTHER_DEVICE)).status_code == 200


@pytest.mark.parametrize("auth", [None, "Bearer garbage"])
async def test_logout_requires_access_token(api, auth):
    headers = {"Authorization": auth} if auth else {}
    resp = await api.post("/api/v1/auth/logout", headers=headers)

    assert resp.status_code == 401
    assert error_code(resp) == "NOT_AUTHENTICATED"


# --- сессии устройств -------------------------------------------------------------


async def test_new_login_same_device_revokes_previous_session(api, sms):
    first = await signed_in(api, sms)

    second = (await login(api)).json()

    assert sid(second["access_token"]) != sid(first["access_token"])
    assert_session_expired(await me(api, first["access_token"]))
    assert_session_expired(await refresh(api, first["refresh_token"]))
    assert (await me(api, second["access_token"])).status_code == 200


async def test_new_login_other_device_keeps_session(api, sms):
    first = await signed_in(api, sms)

    resp = await login_from(api, OTHER_DEVICE)

    assert resp.status_code == 200
    assert (await me(api, first["access_token"])).status_code == 200
    assert (await refresh(api, first["refresh_token"])).status_code == 200


async def test_verify_opens_session_for_device(api, sms, session_factory):
    body = await register(api)
    resp = await api.post(
        "/api/v1/auth/otp/verify",
        json={"verification_id": body["verification_id"], "code": last_code(sms)},
        headers={"X-Device-Id": OTHER_DEVICE},
    )
    assert resp.status_code == 200, resp.text

    async with session_factory() as s:
        auth_session = await s.get(Session, sid(resp.json()["access_token"]))
    assert auth_session.device_id == OTHER_DEVICE
    assert auth_session.revoked_at is None


async def test_revoke_all_user_sessions(api, sms, session_factory):
    first = await signed_in(api, sms)
    other = (await login_from(api, OTHER_DEVICE)).json()

    async with session_factory() as s:
        user = await s.scalar(select(User).where(User.phone == PHONE))
        await service.revoke_all_user_sessions(s, user.id)
        await s.commit()
        sessions = (await s.scalars(select(Session).where(Session.user_id == user.id))).all()

    # verify + login с этого устройства + login с другого
    assert len(sessions) == 3
    assert all(x.revoked_at is not None for x in sessions)
    for tokens, device in ((first, DEVICE_ID), (other, OTHER_DEVICE)):
        assert_session_expired(await me(api, tokens["access_token"]))
        assert_session_expired(await refresh(api, tokens["refresh_token"], device))


async def test_access_token_without_sid_rejected(api, sms):
    await signed_in(api, sms)
    now = datetime.now(UTC)
    legacy = jwt.encode(
        {"sub": str(uuid.uuid4()), "type": "access", "iat": now, "exp": now + timedelta(minutes=5)},
        settings.jwt_secret,
        algorithm=JWT_ALGORITHM,
    )

    resp = await me(api, legacy)

    assert resp.status_code == 401
    assert error_code(resp) == "NOT_AUTHENTICATED"


# --- X-Device-Id ------------------------------------------------------------------


@pytest.mark.parametrize("device_header", [None, "", "not-a-uuid"])
@pytest.mark.parametrize(
    "path,payload",
    [
        ("/api/v1/auth/register", FORM),
        ("/api/v1/auth/otp/verify", {"verification_id": str(uuid.uuid4()), "code": "1234"}),
        ("/api/v1/auth/login", {"phone": PHONE, "password": FORM["password"]}),
        ("/api/v1/auth/refresh", {"refresh_token": "whatever"}),
    ],
)
async def test_device_id_required(api, path, payload, device_header):
    del api.headers["X-Device-Id"]
    headers = {} if device_header is None else {"X-Device-Id": device_header}

    resp = await api.post(path, json=payload, headers=headers)

    assert resp.status_code == 422, resp.text
    assert error_code(resp) == "VALIDATION_ERROR"
