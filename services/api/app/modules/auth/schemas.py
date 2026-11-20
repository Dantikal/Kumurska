# app/modules/auth/schemas.py
from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    AfterValidator,
    BaseModel,
    Field,
    StringConstraints,
    ValidationInfo,
    field_validator,
)

from app.core.phone import normalize_phone

Phone = Annotated[str, AfterValidator(normalize_phone)]


def check_password_strength(value: str) -> str:
    """Правила сложности пароля: 8–128 символов (через Field), хотя бы одна буква и одна цифра."""
    if not any(ch.isalpha() for ch in value) or not any(ch.isdigit() for ch in value):
        raise ValueError("Пароль должен содержать хотя бы одну букву и одну цифру")
    return value


NewPassword = Annotated[
    str, Field(min_length=8, max_length=128), AfterValidator(check_password_strength)
]


class RegisterRequest(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    phone: Phone
    birth_date: date
    # Необязателен, пока не решено, остаётся ли вход по паролю (US-02)
    password: NewPassword | None = None
    accepted_terms: bool

    @field_validator("birth_date")
    @classmethod
    def _birth_date_in_past(cls, value: date) -> date:
        if value >= date.today():
            raise ValueError("Дата рождения должна быть в прошлом")
        if value.year < 1900:
            raise ValueError("Некорректная дата рождения")
        return value

    @field_validator("accepted_terms")
    @classmethod
    def _terms_accepted(cls, value: bool) -> bool:
        if not value:
            raise ValueError("Нужно принять условия программы")
        return value


class LoginRequest(BaseModel):
    phone: Phone
    password: Annotated[str, Field(min_length=1, max_length=128)]


class OtpVerifyRequest(BaseModel):
    verification_id: UUID
    code: Annotated[str, StringConstraints(pattern=r"^\d{1,10}$")]


class OtpResendRequest(BaseModel):
    verification_id: UUID


class PasswordResetRequest(BaseModel):
    phone: Phone


class PasswordResetConfirm(BaseModel):
    verification_id: UUID
    code: Annotated[str, StringConstraints(pattern=r"^\d{1,10}$")]
    new_password: NewPassword
    new_password_confirm: str

    @field_validator("new_password_confirm")
    @classmethod
    def _passwords_match(cls, value: str, info: ValidationInfo) -> str:
        # Если new_password не прошёл проверку, его нет в info.data: ошибка уже будет там.
        if "new_password" in info.data and value != info.data["new_password"]:
            raise ValueError("Пароли не совпадают")
        return value


class OtpSentResponse(BaseModel):
    verification_id: UUID
    phone_masked: str = Field(examples=["+996 *** *** 456"])
    expires_in: int = Field(description="Секунд до истечения кода")
    resend_in: int = Field(description="Секунд до возможности запросить новый код")


class RefreshRequest(BaseModel):
    refresh_token: Annotated[str, Field(min_length=1, max_length=256)]


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = Field(description="Время жизни access-токена в секундах")
