# app/modules/auth/tokens.py
"""Выдача и проверка токенов.

access — JWT (HS256), sub = user_id.
refresh — случайная строка, в базе хранится только её SHA-256.
Ротация и привязка к устройству — US-25.
"""

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.modules.auth import repository
from app.modules.auth.models import RefreshToken

JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_TYPE = "access"


class InvalidTokenError(Exception):
    pass


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    refresh_token: str
    expires_in: int


def create_access_token(user_id: uuid.UUID, now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "type": ACCESS_TOKEN_TYPE,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_ttl_minutes),
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> uuid.UUID:
    """Возвращает user_id или бросает InvalidTokenError."""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[JWT_ALGORITHM],
            options={"require": ["sub", "exp", "type"]},
        )
        if payload["type"] != ACCESS_TOKEN_TYPE:
            raise InvalidTokenError
        return uuid.UUID(payload["sub"])
    except (jwt.PyJWTError, ValueError) as exc:
        raise InvalidTokenError from exc


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def issue_tokens(session: AsyncSession, user_id: uuid.UUID) -> TokenPair:
    """Создаёт пару токенов; запись refresh-токена добавляется в текущую транзакцию."""
    now = datetime.now(UTC)
    refresh_token = secrets.token_urlsafe(48)
    repository.add_refresh_token(
        session,
        RefreshToken(
            user_id=user_id,
            token_hash=hash_refresh_token(refresh_token),
            expires_at=now + timedelta(days=settings.refresh_token_ttl_days),
        ),
    )
    return TokenPair(
        access_token=create_access_token(user_id, now),
        refresh_token=refresh_token,
        expires_in=settings.access_token_ttl_minutes * 60,
    )
