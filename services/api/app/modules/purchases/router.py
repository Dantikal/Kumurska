"""Маршруты покупок."""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.schemas import ErrorResponse
from app.modules.auth.dependencies import get_current_user
from app.modules.purchases import service as purchases_service
from app.modules.purchases.schemas import PurchaseRead
from app.modules.users.models import User

router = APIRouter(prefix="/purchases", tags=["purchases"])


@router.get(
    "/{id}",
    response_model=PurchaseRead,
    responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
async def get_purchase(
    id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PurchaseRead:
    return await purchases_service.get_purchase_details(
        db,
        id,
        current_user.id,
    )
