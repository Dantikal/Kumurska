from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.errors import ApiError
from app.core.schemas import ErrorResponse, Page
from app.modules.auth.dependencies import get_current_user
from app.modules.loyalty import service as loyalty_service
from app.modules.loyalty.schemas import (
    BonusAccountRead,
    BonusTransactionRead,
    LoyaltyLevelRead,
)
from app.modules.users.models import User

router = APIRouter(prefix="/loyalty", tags=["loyalty"])


@router.get(
    "/account",
    response_model=BonusAccountRead,
    responses={404: {"model": ErrorResponse}},
)
async def get_account(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BonusAccountRead:
    return await loyalty_service.get_account(db, current_user.id)


@router.get(
    "/levels",
    response_model=Page[LoyaltyLevelRead],
    responses={422: {"model": ErrorResponse}},
)
async def list_levels(
    cursor: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
) -> Page[LoyaltyLevelRead]:
    raise ApiError(501, "NOT_IMPLEMENTED", "Метод ещё не реализован")


@router.get(
    "/transactions",
    response_model=Page[BonusTransactionRead],
    responses={422: {"model": ErrorResponse}},
)
async def list_transactions(
    cursor: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
) -> Page[BonusTransactionRead]:
    raise ApiError(501, "NOT_IMPLEMENTED", "Метод ещё не реализован")
