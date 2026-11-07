# app/modules/auth/service.py
"""Регистрация с подтверждением номера по SMS (US-03).

Коды и пароли в открытом виде не логируются, не возвращаются и не сохраняются:
код живёт только в тексте SMS, в базе — HMAC; пароль — только argon2-хеш.
"""

import hashlib
import hmac
import math
import secrets
import uuid
from datetime import UTC, date, datetime, timedelta

from anyio import to_thread
from argon2 import PasswordHasher
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import ApiError
from app.core.phone import mask_phone
from app.integrations.sms import SmsProvider
from app.modules.auth import repository
from app.modules.auth.models import OtpCode, OtpPurpose
from app.modules.auth.schemas import (
    OtpSentResponse,
    RegisterRequest,
    TokenResponse,
)
from app.modules.auth.tokens import issue_tokens
from app.modules.loyalty import service as loyalty_service
from app.modules.users import service as users_service

_password_hasher = PasswordHasher()


# --- ошибки -----------------------------------------------------------------


def _phone_already_registered() -> ApiError:
    return ApiError(409, "PHONE_ALREADY_REGISTERED", "Номер уже зарегистрирован")


def _otp_not_found() -> ApiError:
    return ApiError(404, "OTP_NOT_FOUND", "Код не найден или уже использован")


def _resend_too_early(now: datetime, resend_at: datetime) -> ApiError:
    retry_after = max(1, math.ceil((resend_at - now).total_seconds()))
    return ApiError(
        429,
        "OTP_RESEND_TOO_EARLY",
        "Новый код можно запросить позже",
        {"retry_after": retry_after},
        headers={"Retry-After": str(retry_after)},
    )


# --- коды -------------------------------------------------------------------


def generate_code() -> str:
    length = settings.otp_length
    return f"{secrets.randbelow(10**length):0{length}d}"


def hash_code(otp_id: uuid.UUID, code: str) -> str:
    return hmac.new(
        settings.otp_secret.encode(), f"{otp_id}:{code}".encode(), hashlib.sha256
    ).hexdigest()


def _code_matches(otp: OtpCode, code: str) -> bool:
    return hmac.compare_digest(otp.code_hash, hash_code(otp.id, code))


async def _create_and_send(
    db: AsyncSession,
    sms: SmsProvider,
    *,
    phone: str,
    purpose: OtpPurpose,
    payload: dict | None,
    now: datetime,
) -> OtpSentResponse:
    """Аннулирует прежние коды номера, создаёт новый, отправляет SMS и коммитит."""
    await repository.consume_active_otps(db, phone, purpose, now)

    code = generate_code()
    otp_id = uuid.uuid4()
    repository.add_otp(
        db,
        OtpCode(
            id=otp_id,
            phone=phone,
            purpose=purpose,
            code_hash=hash_code(otp_id, code),
            payload=payload,
            attempts=0,
            expires_at=now + timedelta(seconds=settings.otp_ttl_seconds),
            resend_at=now + timedelta(seconds=settings.otp_resend_seconds),
        ),
    )
    await db.flush()
    # Если отправка упадёт, транзакция откатится и запись не останется висеть.
    await sms.send(phone, f"Kumurska: код подтверждения {code}. Никому его не сообщайте.")
    await db.commit()

    return OtpSentResponse(
        verification_id=otp_id,
        phone_masked=mask_phone(phone),
        expires_in=settings.otp_ttl_seconds,
        resend_in=settings.otp_resend_seconds,
    )


# --- сценарии ---------------------------------------------------------------


async def register(db: AsyncSession, sms: SmsProvider, data: RegisterRequest) -> OtpSentResponse:
    """Сохраняет данные формы во временную запись и отправляет код. Пользователя не создаёт."""
    if await users_service.phone_exists(db, data.phone):
        raise _phone_already_registered()

    now = datetime.now(UTC)
    # Повторная отправка формы не должна обходить таймер повторной отправки.
    active = await repository.get_latest_active_otp(db, data.phone, OtpPurpose.REGISTER)
    if active is not None and active.resend_at > now:
        raise _resend_too_early(now, active.resend_at)

    password_hash = None
    if data.password is not None:
        password_hash = await to_thread.run_sync(_password_hasher.hash, data.password)

    payload = {
        "name": data.name,
        "birth_date": data.birth_date.isoformat(),
        "password_hash": password_hash,
    }
    return await _create_and_send(
        db, sms, phone=data.phone, purpose=OtpPurpose.REGISTER, payload=payload, now=now
    )


async def resend(db: AsyncSession, sms: SmsProvider, verification_id: uuid.UUID) -> OtpSentResponse:
    otp = await repository.get_otp_for_update(db, verification_id, OtpPurpose.REGISTER)
    if otp is None or otp.consumed_at is not None:
        raise _otp_not_found()

    now = datetime.now(UTC)
    if now < otp.resend_at:
        raise _resend_too_early(now, otp.resend_at)

    if await users_service.phone_exists(db, otp.phone):
        otp.consumed_at = now
        await db.commit()
        raise _phone_already_registered()

    return await _create_and_send(
        db, sms, phone=otp.phone, purpose=otp.purpose, payload=otp.payload, now=now
    )


async def verify(db: AsyncSession, verification_id: uuid.UUID, code: str) -> TokenResponse:
    # FOR UPDATE: параллельные попытки с одним verification_id выполняются по очереди.
    otp = await repository.get_otp_for_update(db, verification_id, OtpPurpose.REGISTER)
    if otp is None or otp.consumed_at is not None:
        raise _otp_not_found()

    now = datetime.now(UTC)
    if now >= otp.expires_at:
        raise ApiError(400, "OTP_EXPIRED", "Срок действия кода истёк")
    if otp.attempts >= settings.otp_max_attempts:
        raise ApiError(400, "OTP_ATTEMPTS_EXCEEDED", "Превышено число попыток, запросите новый код")

    if not _code_matches(otp, code):
        otp.attempts += 1
        attempts_left = max(0, settings.otp_max_attempts - otp.attempts)
        await db.commit()
        raise ApiError(400, "OTP_INVALID", "Неверный код", {"attempts_left": attempts_left})

    otp.consumed_at = now
    payload = otp.payload or {}
    try:
        async with db.begin_nested():
            user = await users_service.create_user(
                db,
                phone=otp.phone,
                name=payload["name"],
                birth_date=date.fromisoformat(payload["birth_date"]),
                password_hash=payload.get("password_hash"),
            )
    except IntegrityError:
        # Номер успели занять между отправкой кода и подтверждением.
        await db.commit()  # код всё равно считаем использованным
        raise _phone_already_registered() from None

    await loyalty_service.open_account(db, user.id)
    tokens = await issue_tokens(db, user.id)
    await db.commit()

    return TokenResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_in=tokens.expires_in,
    )
