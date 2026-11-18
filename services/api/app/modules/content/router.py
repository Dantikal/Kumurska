# app/modules/content/router.py
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.errors import ApiError
from app.core.schemas import ErrorResponse, Page
from app.modules.content import service as content_service
from app.modules.content.schemas import EventRead, PromotionRead

router = APIRouter(prefix="/content", tags=["content"])


@router.get(
    "/promotions",
    response_model=Page[PromotionRead],
    responses={422: {"model": ErrorResponse}},
)
async def list_promotions(
    cursor: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
) -> Page[PromotionRead]:
    raise ApiError(501, "NOT_IMPLEMENTED", "Метод ещё не реализован")


@router.get(
    "/promotions/{id}",
    response_model=PromotionRead,
    responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
async def get_promotion(id: UUID) -> PromotionRead:
    raise ApiError(501, "NOT_IMPLEMENTED", "Метод ещё не реализован")


@router.get(
    "/events",
    response_model=Page[EventRead],
    responses={
        400: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
async def list_events(
    cursor: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> Page[EventRead]:
    return await content_service.list_upcoming_events(
        session=db,
        cursor=cursor,
        limit=limit,
    )
