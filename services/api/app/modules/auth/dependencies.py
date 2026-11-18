# app/modules/auth/dependencies.py
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.errors import ApiError
from app.modules.auth import repository
from app.modules.auth.service import session_expired
from app.modules.auth.tokens import AccessClaims, InvalidTokenError, decode_access_token
from app.modules.users import service as users_service
from app.modules.users.models import User, UserStatus

bearer_scheme = HTTPBearer(auto_error=False)


async def get_device_id(
    x_device_id: Annotated[
        UUID,
        Header(
            alias="X-Device-Id",
            description="UUID устройства: приложение генерирует его один раз и хранит локально",
        ),
    ],
) -> str:
    """Обязательный заголовок X-Device-Id. Нет или не UUID → 422 VALIDATION_ERROR."""
    return str(x_device_id)


def _not_authenticated() -> ApiError:
    return ApiError(
        401,
        "NOT_AUTHENTICATED",
        "Требуется авторизация",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_access_claims(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> AccessClaims:
    """Проверяет только подпись и срок access-токена, без обращения к базе."""
    if credentials is None:
        raise _not_authenticated()
    try:
        return decode_access_token(credentials.credentials)
    except InvalidTokenError:
        raise _not_authenticated() from None


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    claims = await get_access_claims(credentials)

    # Отозванная сессия отсекается сразу, не дожидаясь истечения access-токена.
    auth_session = await repository.get_session(db, claims.session_id)
    if (
        auth_session is None
        or auth_session.revoked_at is not None
        or auth_session.user_id != claims.user_id
    ):
        raise session_expired()

    user = await users_service.get_user(db, claims.user_id)
    if user is None:
        raise _not_authenticated()
    if user.status in (UserStatus.BLOCKED, UserStatus.DELETED):
        raise ApiError(403, "USER_BLOCKED", "Доступ к аккаунту ограничен")
    return user
