# app/modules/auth/dependencies.py
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.errors import ApiError
from app.modules.auth.tokens import InvalidTokenError, decode_access_token
from app.modules.users import service as users_service
from app.modules.users.models import User, UserStatus

bearer_scheme = HTTPBearer(auto_error=False)


def _not_authenticated() -> ApiError:
    return ApiError(
        401,
        "NOT_AUTHENTICATED",
        "Требуется авторизация",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    if credentials is None:
        raise _not_authenticated()
    try:
        user_id = decode_access_token(credentials.credentials)
    except InvalidTokenError:
        raise _not_authenticated() from None

    user = await users_service.get_user(db, user_id)
    if user is None:
        raise _not_authenticated()
    if user.status in (UserStatus.BLOCKED, UserStatus.DELETED):
        raise ApiError(403, "USER_BLOCKED", "Доступ к аккаунту ограничен")
    return user
