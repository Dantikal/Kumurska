# app/modules/purchases/router.py
from uuid import UUID

from fastapi import APIRouter

from app.core.errors import ApiError
from app.core.schemas import ErrorResponse
from app.modules.purchases.schemas import PurchaseRead

router = APIRouter(prefix="/purchases", tags=["purchases"])


@router.get(
    "/{id}",
    response_model=PurchaseRead,
    responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
async def get_purchase(id: UUID) -> PurchaseRead:
    raise ApiError(501, "NOT_IMPLEMENTED", "Метод ещё не реализован")
