# app/modules/loyalty/router.py
from fastapi import APIRouter, Query

from app.core.errors import ApiError
from app.core.schemas import ErrorResponse, Page
from app.modules.loyalty.schemas import (
    BonusAccountRead,
    BonusTransactionRead,
    LoyaltyLevelRead,
)

router = APIRouter(prefix="/loyalty", tags=["loyalty"])


@router.get(
    "/account",
    response_model=BonusAccountRead,
    responses={404: {"model": ErrorResponse}},
)
async def get_account() -> BonusAccountRead:
    raise ApiError(501, "NOT_IMPLEMENTED", "Метод ещё не реализован")


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
