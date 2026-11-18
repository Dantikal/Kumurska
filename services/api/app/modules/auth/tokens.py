# app/modules/auth/tokens.py
"""Выдача и проверка токенов.

access — JWT (HS256): sub = user_id, sid = id сессии устройства.
refresh — случайная строка, в базе хранится только её SHA-256. Одноразовый:
при обмене выдаётся новый в той же сессии (US-25).
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
from app.modules.auth.models import RefreshToken, Session

JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_TYPE = "access"


class InvalidTokenError(Exception):
    pass


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    refresh_token: str
    expires_in: int


@dataclass(frozen=True)
class AccessClaims:
    user_id: uuid.UUID
    session_id: uuid.UUID


def create_access_token(
    user_id: uuid.UUID, session_id: uuid.UUID, now: datetime | None = None
) -> str:
    now = now or datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "sid": str(session_id),
        "type": ACCESS_TOKEN_TYPE,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_ttl_minutes),
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> AccessClaims:
    """Проверяет подпись и срок; бросает InvalidTokenError.

    Токены без sid (выданы до US-25) считаются неверными.
    """
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[JWT_ALGORITHM],
            options={"require": ["sub", "sid", "exp", "type"]},
        )
        if payload["type"] != ACCESS_TOKEN_TYPE:
            raise InvalidTokenError
        return AccessClaims(user_id=uuid.UUID(payload["sub"]), session_id=uuid.UUID(payload["sid"]))
    except (jwt.PyJWTError, ValueError, TypeError) as exc:
        raise InvalidTokenError from exc


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def issue_session_tokens(session: AsyncSession, auth_session: Session, now: datetime) -> TokenPair:
    """Выдаёт пару токенов в существующей сессии; запись refresh добавляется в транзакцию."""
    refresh_token = secrets.token_urlsafe(48)
    repository.add_refresh_token(
        session,
        RefreshToken(
            user_id=auth_session.user_id,
            session_id=auth_session.id,
            token_hash=hash_refresh_token(refresh_token),
            expires_at=now + timedelta(days=settings.refresh_token_ttl_days),
        ),
    )
    return TokenPair(
        access_token=create_access_token(auth_session.user_id, auth_session.id, now),
        refresh_token=refresh_token,
        expires_in=settings.access_token_ttl_minutes * 60,
    )


async def issue_tokens(session: AsyncSession, user_id: uuid.UUID, device_id: str) -> TokenPair:
    """Новый вход: отзывает прежнюю сессию этого устройства, открывает новую и выдаёт токены.

    Коммит — на вызывающей стороне.
    """
    now = datetime.now(UTC)
    await repository.revoke_device_sessions(session, user_id, device_id, now)
    auth_session = Session(id=uuid.uuid4(), user_id=user_id, device_id=device_id, last_used_at=now)
    repository.add_session(session, auth_session)
    # Сессия должна попасть в базу раньше токена, который на неё ссылается.
    await session.flush()
    return issue_session_tokens(session, auth_session, now)
