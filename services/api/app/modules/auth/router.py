# app/modules/auth/router.py
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.schemas import ErrorResponse
from app.integrations.sms import SmsProvider, get_sms_provider
from app.modules.auth import service
from app.modules.auth.schemas import (
    LoginRequest,
    OtpResendRequest,
    OtpSentResponse,
    OtpVerifyRequest,
    RegisterRequest,
    TokenResponse,
)

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
) -> OtpSentResponse:
    """Принимает форму регистрации и отправляет SMS-код. Пользователь создаётся после verify."""
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
) -> TokenResponse:
    """Вход по номеру телефона и паролю. Выдаёт токены."""
    return await service.login(db, payload.phone, payload.password)


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
) -> TokenResponse:
    """Проверяет код, создаёт пользователя и бонусный счёт, выдаёт токены."""
    return await service.verify(db, payload.verification_id, payload.code)


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
