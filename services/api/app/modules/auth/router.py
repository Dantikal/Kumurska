# app/modules/auth/router.py
from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.schemas import ErrorResponse
from app.integrations.sms import SmsProvider, get_sms_provider
from app.modules.auth import service
from app.modules.auth.dependencies import get_access_claims, get_device_id
from app.modules.auth.schemas import (
    LoginRequest,
    OtpResendRequest,
    OtpSentResponse,
    OtpVerifyRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
)
from app.modules.auth.tokens import AccessClaims

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    response_model=OtpSentResponse,
    responses={
        409: {"model": ErrorResponse, "description": "PHONE_ALREADY_REGISTERED"},
        422: {"model": ErrorResponse, "description": "VALIDATION_ERROR"},
        429: {"model": ErrorResponse, "description": "OTP_RESEND_TOO_EARLY"},
    },
)
async def register(
    payload: RegisterRequest,
    db: AsyncSession = Depends(get_db),
    sms: SmsProvider = Depends(get_sms_provider),
    _device_id: str = Depends(get_device_id),
) -> OtpSentResponse:
    """Принимает форму регистрации и отправляет SMS-код. Пользователь создаётся после verify.

    Заголовок X-Device-Id обязателен для единообразия с verify, где открывается сессия.
    """
    return await service.register(db, sms, payload)


@router.post(
    "/login",
    response_model=TokenResponse,
    responses={
        401: {"model": ErrorResponse, "description": "INVALID_CREDENTIALS"},
        403: {"model": ErrorResponse, "description": "USER_BLOCKED"},
        422: {"model": ErrorResponse, "description": "VALIDATION_ERROR"},
    },
)
async def login(
    payload: LoginRequest,
    db: AsyncSession = Depends(get_db),
    device_id: str = Depends(get_device_id),
) -> TokenResponse:
    """Вход по номеру телефона и паролю. Открывает сессию устройства и выдаёт токены.

    Прежняя сессия этого же устройства (X-Device-Id) отзывается.
    """
    return await service.login(db, payload.phone, payload.password, device_id)


@router.post(
    "/otp/verify",
    response_model=TokenResponse,
    responses={
        400: {
            "model": ErrorResponse,
            "description": (
                "OTP_INVALID (details.attempts_left), OTP_EXPIRED, OTP_ATTEMPTS_EXCEEDED"
            ),
        },
        404: {"model": ErrorResponse, "description": "OTP_NOT_FOUND"},
        409: {"model": ErrorResponse, "description": "PHONE_ALREADY_REGISTERED"},
        422: {"model": ErrorResponse, "description": "VALIDATION_ERROR"},
    },
)
async def verify_otp(
    payload: OtpVerifyRequest,
    db: AsyncSession = Depends(get_db),
    device_id: str = Depends(get_device_id),
) -> TokenResponse:
    """Проверяет код, создаёт пользователя и бонусный счёт, открывает сессию и выдаёт токены."""
    return await service.verify(db, payload.verification_id, payload.code, device_id)


@router.post(
    "/otp/resend",
    response_model=OtpSentResponse,
    responses={
        404: {"model": ErrorResponse, "description": "OTP_NOT_FOUND"},
        409: {"model": ErrorResponse, "description": "PHONE_ALREADY_REGISTERED"},
        422: {"model": ErrorResponse, "description": "VALIDATION_ERROR"},
        429: {
            "model": ErrorResponse,
            "description": "OTP_RESEND_TOO_EARLY (заголовок Retry-After, details.retry_after)",
        },
    },
)
async def resend_otp(
    payload: OtpResendRequest,
    db: AsyncSession = Depends(get_db),
    sms: SmsProvider = Depends(get_sms_provider),
) -> OtpSentResponse:
    """Отправляет новый код. Старый аннулируется, клиент использует новый verification_id."""
    return await service.resend(db, sms, payload.verification_id)


@router.post(
    "/refresh",
    response_model=TokenResponse,
    responses={
        401: {
            "model": ErrorResponse,
            "description": (
                "SESSION_EXPIRED: токен неверный, истёк, уже использован, выдан другому "
                "устройству или сессия отозвана. Клиент очищает сессию и показывает вход."
            ),
        },
        403: {"model": ErrorResponse, "description": "USER_BLOCKED"},
        422: {"model": ErrorResponse, "description": "VALIDATION_ERROR"},
    },
)
async def refresh(
    payload: RefreshRequest,
    db: AsyncSession = Depends(get_db),
    device_id: str = Depends(get_device_id),
) -> TokenResponse:
    """Обменивает refresh-токен на новую пару. Старый refresh больше не действует.

    Повторное предъявление уже обменянного refresh отзывает всю сессию.
    Клиент должен выполнять не больше одного refresh одновременно.
    """
    return await service.refresh(db, payload.refresh_token, device_id)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses={
        401: {"model": ErrorResponse, "description": "NOT_AUTHENTICATED"},
    },
)
async def logout(
    claims: AccessClaims = Depends(get_access_claims),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Завершает текущую сессию (sid из access-токена). Повторный вызов тоже возвращает 204.

    После выхода access-токен этой сессии сразу перестаёт приниматься, refresh — тоже.
    """
    await service.logout(db, claims.user_id, claims.session_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
