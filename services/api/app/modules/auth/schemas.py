# app/modules/auth/schemas.py
from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AfterValidator, BaseModel, Field, StringConstraints, field_validator

from app.core.phone import normalize_phone

Phone = Annotated[str, AfterValidator(normalize_phone)]


class RegisterRequest(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    phone: Phone
    birth_date: date
    # Необязателен, пока не решено, остаётся ли вход по паролю (US-02)
    password: Annotated[str | None, Field(min_length=8, max_length=128)] = None
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


class OtpVerifyRequest(BaseModel):
    verification_id: UUID
    code: Annotated[str, StringConstraints(pattern=r"^\d{1,10}$")]


class OtpResendRequest(BaseModel):
    verification_id: UUID


class OtpSentResponse(BaseModel):
    verification_id: UUID
    phone_masked: str = Field(examples=["+996 *** *** 456"])
    expires_in: int = Field(description="Секунд до истечения кода")
    resend_in: int = Field(description="Секунд до возможности запросить новый код")


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = Field(description="Время жизни access-токена в секундах")
