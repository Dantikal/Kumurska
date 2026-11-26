# app/modules/admin/dependencies.py
"""Доступ сотрудников к админским методам.

Вход сотрудников и роли появятся в US-36. До этого get_current_staff — заглушка,
которая никого не пускает: все админские методы отвечают 401. Сигнатура
require_role финальная, менять её в US-36 не нужно, меняется только get_current_staff.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.errors import ApiError

staff_bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Staff:
    id: UUID
    roles: frozenset[str]


async def get_current_staff(
    credentials: HTTPAuthorizationCredentials | None = Depends(staff_bearer_scheme),
) -> Staff | None:
    """Сотрудник по токену. Заглушка до US-36: токенов сотрудников ещё нет."""
    return None


def require_role(role: str) -> Callable[..., Awaitable[Staff]]:
    """Зависимость: пускает только сотрудника с ролью role.

    Нет сотрудника → 401 NOT_AUTHENTICATED, нет роли → 403 FORBIDDEN.
    """

    async def dependency(staff: Staff | None = Depends(get_current_staff)) -> Staff:
        if staff is None:
            raise ApiError(
                401,
                "NOT_AUTHENTICATED",
                "Требуется авторизация",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if role not in staff.roles:
            raise ApiError(403, "FORBIDDEN", "Недостаточно прав")
        return staff

    return dependency
