# tests/test_password_reset.py
"""US-06: восстановление пароля через SMS."""

import uuid
from datetime import timedelta

import httpx
import pytest
from sqlalchemy import select

from app.core.config import settings
from app.integrations.sms import FakeSmsProvider
from app.modules.auth.models import OtpCode, OtpPurpose
from app.modules.users.models import UserStatus
from tests.test_login import PASSWORD, complete_registration, login, set_status
from tests.test_otp import PHONE, error_code, last_code, register, shift_otp, wrong_code
from tests.test_refresh import OTHER_DEVICE, assert_session_expired, login_from, me, refresh

pytestmark = [pytest.mark.anyio, pytest.mark.usefixtures("entry_level")]

NEW_PASSWORD = "n3w-secret-pass"


async def request_reset(api: httpx.AsyncClient, phone: str = PHONE) -> httpx.Response:
    return await api.post("/api/v1/auth/password/reset", json={"phone": phone})


async def resend_reset(api: httpx.AsyncClient, verification_id: str) -> httpx.Response:
    return await api.post(
        "/api/v1/auth/password/reset/resend", json={"verification_id": verification_id}
    )


async def confirm_reset(
    api: httpx.AsyncClient,
    verification_id: str,
    code: str,
    password: str = NEW_PASSWORD,
    confirm: str | None = None,
) -> httpx.Response:
    return await api.post(
        "/api/v1/auth/password/reset/confirm",
        json={
            "verification_id": verification_id,
            "code": code,
            "new_password": password,
            "new_password_confirm": password if confirm is None else confirm,
        },
    )


async def start_reset(api: httpx.AsyncClient, sms: FakeSmsProvider) -> tuple[str, str]:
    """Регистрирует пользователя и запрашивает код восстановления."""
    await complete_registration(api, sms)
    resp = await request_reset(api)
    assert resp.status_code == 200, resp.text
    return resp.json()["verification_id"], last_code(sms)


def error_fields(resp: httpx.Response) -> dict[str, str]:
    fields = resp.json()["error"]["details"]["fields"]
    return {f["field"].split(".")[-1]: f["message"] for f in fields}


# --- шаг 1: номер телефона и SMS -------------------------------------------------


async def test_request_sends_reset_sms(api, sms):
    await complete_registration(api, sms)
    sent_before = len(sms.sent)

    resp = await request_reset(api, phone="0555 123 456")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body) == {"verification_id", "phone_masked", "expires_in", "resend_in"}
    assert body["phone_masked"].endswith("456")
    assert body["resend_in"] == settings.otp_resend_seconds
    assert len(sms.sent) == sent_before + 1
    phone, text = sms.sent[-1]
    assert phone == PHONE
    assert "восстановления пароля" in text


async def test_request_unknown_phone_looks_the_same(api, sms, session_factory):
    resp = await request_reset(api, phone="+996700000000")

    assert resp.status_code == 200, resp.text
    assert set(resp.json()) == {"verification_id", "phone_masked", "expires_in", "resend_in"}
    assert sms.sent == []
    async with session_factory() as s:
        otp = await s.get(OtpCode, uuid.UUID(resp.json()["verification_id"]))
        assert otp is not None and otp.purpose == OtpPurpose.RESET_PASSWORD


@pytest.mark.parametrize("status", [UserStatus.BLOCKED, UserStatus.DELETED])
async def test_request_for_blocked_user_sends_no_sms(api, sms, session_factory, status):
    await complete_registration(api, sms)
    await set_status(session_factory, status)
    sent_before = len(sms.sent)

    resp = await request_reset(api)

    assert resp.status_code == 200
    assert len(sms.sent) == sent_before


async def test_request_invalid_phone(api):
    resp = await request_reset(api, phone="123")

    assert resp.status_code == 422
    assert error_code(resp) == "VALIDATION_ERROR"


async def test_repeated_request_respects_timer(api, sms):
    await start_reset(api, sms)

    resp = await request_reset(api)

    assert resp.status_code == 429
    assert error_code(resp) == "OTP_RESEND_TOO_EARLY"
    assert int(resp.headers["Retry-After"]) > 0


# --- повторная отправка -----------------------------------------------------------


async def test_resend_too_early(api, sms):
    verification_id, _ = await start_reset(api, sms)

    resp = await resend_reset(api, verification_id)

    assert resp.status_code == 429
    assert error_code(resp) == "OTP_RESEND_TOO_EARLY"
    assert resp.json()["error"]["details"]["retry_after"] > 0


async def test_resend_issues_new_code_and_cancels_old(api, sms, session_factory):
    verification_id, old_code = await start_reset(api, sms)
    await shift_otp(session_factory, verification_id, resend_at=timedelta(hours=1))

    resp = await resend_reset(api, verification_id)

    assert resp.status_code == 200, resp.text
    new_id = resp.json()["verification_id"]
    assert new_id != verification_id
    assert error_code(await confirm_reset(api, verification_id, old_code)) == "OTP_NOT_FOUND"
    assert (await confirm_reset(api, new_id, last_code(sms))).status_code == 200


async def test_resend_unknown_id(api):
    resp = await resend_reset(api, str(uuid.uuid4()))

    assert resp.status_code == 404
    assert error_code(resp) == "OTP_NOT_FOUND"


# --- шаг 2: код и новый пароль ------------------------------------------------------


async def test_confirm_changes_password(api, sms):
    verification_id, code = await start_reset(api, sms)

    resp = await confirm_reset(api, verification_id, code)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body) == {"access_token", "refresh_token", "token_type", "expires_in"}
    assert (await me(api, body["access_token"])).status_code == 200

    assert (await login(api, password=NEW_PASSWORD)).status_code == 200
    old = await login(api, password=PASSWORD)
    assert old.status_code == 401
    assert error_code(old) == "INVALID_CREDENTIALS"


async def test_confirm_ends_other_sessions(api, sms):
    await complete_registration(api, sms)
    other = (await login_from(api, OTHER_DEVICE)).json()
    resp = await request_reset(api)
    verification_id, code = resp.json()["verification_id"], last_code(sms)

    assert (await confirm_reset(api, verification_id, code)).status_code == 200

    assert_session_expired(await refresh(api, other["refresh_token"], OTHER_DEVICE))
    assert (await me(api, other["access_token"])).status_code == 401


async def test_confirm_sets_password_for_user_without_one(api, sms):
    await complete_registration(api, sms, password=None)
    resp = await request_reset(api)

    confirmed = await confirm_reset(api, resp.json()["verification_id"], last_code(sms))

    assert confirmed.status_code == 200, confirmed.text
    assert (await login(api, password=NEW_PASSWORD)).status_code == 200


async def test_confirm_wrong_code_keeps_password(api, sms):
    verification_id, code = await start_reset(api, sms)

    resp = await confirm_reset(api, verification_id, wrong_code(code))

    assert resp.status_code == 400
    assert error_code(resp) == "OTP_INVALID"
    assert resp.json()["error"]["details"]["attempts_left"] == settings.otp_max_attempts - 1
    assert (await login(api, password=PASSWORD)).status_code == 200
    assert (await login(api, password=NEW_PASSWORD)).status_code == 401


async def test_confirm_attempts_exceeded(api, sms):
    verification_id, code = await start_reset(api, sms)
    for _ in range(settings.otp_max_attempts):
        await confirm_reset(api, verification_id, wrong_code(code))

    resp = await confirm_reset(api, verification_id, code)

    assert resp.status_code == 400
    assert error_code(resp) == "OTP_ATTEMPTS_EXCEEDED"


async def test_confirm_expired_code(api, sms, session_factory):
    verification_id, code = await start_reset(api, sms)
    await shift_otp(session_factory, verification_id, expires_at=timedelta(hours=1))

    resp = await confirm_reset(api, verification_id, code)

    assert resp.status_code == 400
    assert error_code(resp) == "OTP_EXPIRED"


async def test_confirm_code_is_single_use(api, sms):
    verification_id, code = await start_reset(api, sms)
    assert (await confirm_reset(api, verification_id, code)).status_code == 200

    resp = await confirm_reset(api, verification_id, code, password="an0ther-pass")

    assert resp.status_code == 404
    assert error_code(resp) == "OTP_NOT_FOUND"


async def test_registration_code_does_not_reset_password(api, sms):
    body = await register(api)

    resp = await confirm_reset(api, body["verification_id"], last_code(sms))

    assert resp.status_code == 404
    assert error_code(resp) == "OTP_NOT_FOUND"


async def test_confirm_blocked_after_code_sent(api, sms, session_factory):
    verification_id, code = await start_reset(api, sms)
    await set_status(session_factory, UserStatus.BLOCKED)

    resp = await confirm_reset(api, verification_id, code)

    assert resp.status_code == 403
    assert error_code(resp) == "USER_BLOCKED"
    async with session_factory() as s:
        otp = await s.scalar(select(OtpCode).where(OtpCode.id == uuid.UUID(verification_id)))
        assert otp.consumed_at is not None


# --- правила для нового пароля ------------------------------------------------------


@pytest.mark.parametrize(
    ("password", "confirm", "field"),
    [
        (NEW_PASSWORD, "n3w-secret-pasS", "new_password_confirm"),
        ("short1", "short1", "new_password"),
        ("x1" * 65, "x1" * 65, "new_password"),
        ("onlyletters", "onlyletters", "new_password"),
        ("1234567890", "1234567890", "new_password"),
    ],
)
async def test_confirm_rejects_bad_password(api, sms, password, confirm, field):
    verification_id, code = await start_reset(api, sms)

    resp = await confirm_reset(api, verification_id, code, password=password, confirm=confirm)

    assert resp.status_code == 422
    assert error_code(resp) == "VALIDATION_ERROR"
    assert field in error_fields(resp)
    # Код не потрачен: после исправления пароля его можно ввести снова.
    assert (await confirm_reset(api, verification_id, code)).status_code == 200


async def test_register_uses_same_password_rules(api):
    resp = await api.post(
        "/api/v1/auth/register",
        json={
            "name": "Айгерим",
            "phone": PHONE,
            "birth_date": "1995-04-12",
            "password": "onlyletters",
            "accepted_terms": True,
        },
    )

    assert resp.status_code == 422
    assert "password" in error_fields(resp)
