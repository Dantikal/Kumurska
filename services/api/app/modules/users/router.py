# app/modules/users/router.py
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.schemas import ErrorResponse
from app.modules.auth.dependencies import get_current_user
from app.modules.users import service as users_service
from app.modules.users.models import User
from app.modules.users.schemas import UserRead, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])


@router.get(
    "/me",
    response_model=UserRead,
    responses={404: {"model": ErrorResponse}},
)
async def get_me(
    current_user: User = Depends(get_current_user),
) -> UserRead:
    return users_service.get_profile(current_user)


@router.patch(
    "/me",
    response_model=UserRead,
    responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
async def update_me(
    payload: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UserRead:
    updated_user = await users_service.update_profile(
        db,
        current_user,
        payload,
    )

    await db.commit()

    return updated_user
