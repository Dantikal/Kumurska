# app/modules/content/admin_router.py
"""Админские методы акций и событий (US-17). Доступны только роли content_manager."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.schemas import ErrorResponse, Page
from app.integrations.storage import ImageStorage, get_image_storage
from app.modules.admin.dependencies import require_role
from app.modules.content import admin_service
from app.modules.content.models import ContentStatus, Event, Promotion
from app.modules.content.schemas import (
    AdminEventRead,
    AdminPromotionRead,
    EventCreate,
    EventUpdate,
    ImageUploadRead,
    PromotionCreate,
    PromotionUpdate,
)

CONTENT_MANAGER = "content_manager"

router = APIRouter(
    prefix="/admin/content",
    tags=["admin: content"],
    dependencies=[Depends(require_role(CONTENT_MANAGER))],
    responses={
        401: {"model": ErrorResponse, "description": "NOT_AUTHENTICATED"},
        403: {"model": ErrorResponse, "description": "FORBIDDEN: нет роли content_manager"},
        422: {"model": ErrorResponse, "description": "VALIDATION_ERROR"},
    },
)

_LIST_RESPONSES = {400: {"model": ErrorResponse, "description": "INVALID_CURSOR"}}
_TRANSITION_RESPONSES = {
    409: {"model": ErrorResponse, "description": "INVALID_STATUS_TRANSITION"},
    422: {
        "model": ErrorResponse,
        "description": "VALIDATION_ERROR: не заполнены поля, обязательные для публикации",
    },
}
_PROMOTION_404 = {404: {"model": ErrorResponse, "description": "PROMOTION_NOT_FOUND"}}
_EVENT_404 = {404: {"model": ErrorResponse, "description": "EVENT_NOT_FOUND"}}


# --- акции -------------------------------------------------------------------------


@router.get(
    "/promotions",
    response_model=Page[AdminPromotionRead],
    responses=_LIST_RESPONSES,
)
async def admin_list_promotions(
    status: ContentStatus | None = None,
    q: str | None = Query(default=None, min_length=1, max_length=255, description="Поиск"),
    cursor: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> Page[AdminPromotionRead]:
    """Все акции, включая черновики, от новых к старым. q ищет по названию."""
    return await admin_service.list_items(
        db, Promotion, AdminPromotionRead, status=status, q=q, cursor=cursor, limit=limit
    )


@router.post("/promotions", response_model=AdminPromotionRead, status_code=201)
async def admin_create_promotion(
    body: PromotionCreate, db: AsyncSession = Depends(get_db)
) -> Promotion:
    """Создаёт акцию в статусе draft. Сроки можно заполнить позже, до публикации."""
    return await admin_service.create_item(db, Promotion, body)


@router.get("/promotions/{id}", response_model=AdminPromotionRead, responses=_PROMOTION_404)
async def admin_get_promotion(id: UUID, db: AsyncSession = Depends(get_db)) -> Promotion:
    return await admin_service.get_item(db, Promotion, id)


@router.patch("/promotions/{id}", response_model=AdminPromotionRead, responses=_PROMOTION_404)
async def admin_update_promotion(
    id: UUID, body: PromotionUpdate, db: AsyncSession = Depends(get_db)
) -> Promotion:
    """Меняет переданные поля. Изменения опубликованной акции сразу видны клиентам."""
    return await admin_service.update_item(db, Promotion, id, body)


@router.post(
    "/promotions/{id}/publish",
    response_model=AdminPromotionRead,
    responses={**_PROMOTION_404, **_TRANSITION_RESPONSES},
)
async def admin_publish_promotion(id: UUID, db: AsyncSession = Depends(get_db)) -> Promotion:
    """draft или unpublished → published. Нужны title, starts_at и ends_at."""
    return await admin_service.change_status(db, Promotion, id, ContentStatus.PUBLISHED)


@router.post(
    "/promotions/{id}/unpublish",
    response_model=AdminPromotionRead,
    responses={**_PROMOTION_404, **_TRANSITION_RESPONSES},
)
async def admin_unpublish_promotion(id: UUID, db: AsyncSession = Depends(get_db)) -> Promotion:
    """published → unpublished. Акция остаётся в базе, клиенты её больше не видят."""
    return await admin_service.change_status(db, Promotion, id, ContentStatus.UNPUBLISHED)


# --- события -----------------------------------------------------------------------


@router.get("/events", response_model=Page[AdminEventRead], responses=_LIST_RESPONSES)
async def admin_list_events(
    status: ContentStatus | None = None,
    q: str | None = Query(default=None, min_length=1, max_length=255, description="Поиск"),
    cursor: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> Page[AdminEventRead]:
    """Все события, включая черновики, от новых к старым. q ищет по названию."""
    return await admin_service.list_items(
        db, Event, AdminEventRead, status=status, q=q, cursor=cursor, limit=limit
    )


@router.post("/events", response_model=AdminEventRead, status_code=201)
async def admin_create_event(body: EventCreate, db: AsyncSession = Depends(get_db)) -> Event:
    """Создаёт событие в статусе draft. Дату начала можно заполнить позже, до публикации."""
    return await admin_service.create_item(db, Event, body)


@router.get("/events/{id}", response_model=AdminEventRead, responses=_EVENT_404)
async def admin_get_event(id: UUID, db: AsyncSession = Depends(get_db)) -> Event:
    return await admin_service.get_item(db, Event, id)


@router.patch("/events/{id}", response_model=AdminEventRead, responses=_EVENT_404)
async def admin_update_event(
    id: UUID, body: EventUpdate, db: AsyncSession = Depends(get_db)
) -> Event:
    """Меняет переданные поля. Изменения опубликованного события сразу видны клиентам."""
    return await admin_service.update_item(db, Event, id, body)


@router.post(
    "/events/{id}/publish",
    response_model=AdminEventRead,
    responses={**_EVENT_404, **_TRANSITION_RESPONSES},
)
async def admin_publish_event(id: UUID, db: AsyncSession = Depends(get_db)) -> Event:
    """draft или unpublished → published. Нужны title и starts_at."""
    return await admin_service.change_status(db, Event, id, ContentStatus.PUBLISHED)


@router.post(
    "/events/{id}/unpublish",
    response_model=AdminEventRead,
    responses={**_EVENT_404, **_TRANSITION_RESPONSES},
)
async def admin_unpublish_event(id: UUID, db: AsyncSession = Depends(get_db)) -> Event:
    """published → unpublished. Событие остаётся в базе, клиенты его больше не видят."""
    return await admin_service.change_status(db, Event, id, ContentStatus.UNPUBLISHED)


# --- изображения -------------------------------------------------------------------


@router.post(
    "/images",
    response_model=ImageUploadRead,
    status_code=201,
    responses={
        422: {
            "model": ErrorResponse,
            "description": "IMAGE_TOO_LARGE, UNSUPPORTED_IMAGE_TYPE или VALIDATION_ERROR",
        },
        503: {"model": ErrorResponse, "description": "IMAGE_STORAGE_UNAVAILABLE"},
    },
)
async def admin_upload_image(
    file: Annotated[UploadFile, File(description="JPEG, PNG или WebP, не больше 5 МБ")],
    storage: ImageStorage = Depends(get_image_storage),
) -> ImageUploadRead:
    """Загружает изображение и возвращает image_url для акции или события."""
    image_url = await admin_service.upload_image(storage, file)
    return ImageUploadRead(image_url=image_url)
