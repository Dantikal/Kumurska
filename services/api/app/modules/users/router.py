# app/modules/users/router.py
from fastapi import APIRouter

from app.core.errors import ApiError
from app.core.schemas import ErrorResponse
from app.modules.users.schemas import UserRead, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])


@router.get(
    "/me",
    response_model=UserRead,
    responses={404: {"model": ErrorResponse}},
)
async def get_me() -> UserRead:
    raise ApiError(501, "NOT_IMPLEMENTED", "Метод ещё не реализован")


@router.patch(
    "/me",
    response_model=UserRead,
    responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
async def update_me(payload: UserUpdate) -> UserRead:
    raise ApiError(501, "NOT_IMPLEMENTED", "Метод ещё не реализован")
