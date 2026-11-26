"""Управление акциями и событиями из админки (US-17)."""

import base64
import binascii
import json
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from fastapi import UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.core.schemas import Page
from app.integrations.storage import ImageStorage, StorageError
from app.modules.content import repository
from app.modules.content.models import ContentStatus, Event, Promotion
from app.modules.content.repository import AdminContent

ALLOWED_TRANSITIONS = frozenset(
    {
        (ContentStatus.DRAFT, ContentStatus.PUBLISHED),
        (ContentStatus.PUBLISHED, ContentStatus.UNPUBLISHED),
        (ContentStatus.UNPUBLISHED, ContentStatus.PUBLISHED),
    }
)

# Без этих полей запись нельзя опубликовать
REQUIRED_FOR_PUBLISH: dict[type[AdminContent], tuple[str, ...]] = {
    Promotion: ("title", "starts_at", "ends_at"),
    Event: ("title", "starts_at"),
}

_NOT_FOUND: dict[type[AdminContent], tuple[str, str]] = {
    Promotion: ("PROMOTION_NOT_FOUND", "Акция не найдена"),
    Event: ("EVENT_NOT_FOUND", "Событие не найдено"),
}

MAX_IMAGE_BYTES = 5 * 1024 * 1024


def _validation_error(fields: list[dict[str, str]]) -> ApiError:
    """Тот же формат, что у ошибок валидации запроса."""
    return ApiError(422, "VALIDATION_ERROR", "Некорректные данные", {"fields": fields})


# --- курсор: (created_at, id) ------------------------------------------------------


def encode_admin_cursor(item: AdminContent) -> str:
    data = json.dumps({"created_at": item.created_at.isoformat(), "id": str(item.id)})
    return base64.urlsafe_b64encode(data.encode()).decode()


def decode_admin_cursor(cursor: str) -> tuple[datetime, UUID]:
    try:
        data = json.loads(base64.b64decode(cursor, altchars=b"-_", validate=True).decode())
        if not isinstance(data, dict) or not isinstance(data.get("id"), str):
            raise ValueError("Cursor must contain created_at and id")
        created_at = datetime.fromisoformat(data["created_at"])
        if created_at.utcoffset() is None:
            raise ValueError("Cursor datetime must include timezone")
        return created_at, UUID(data["id"])
    except (ValueError, TypeError, KeyError, binascii.Error):
        raise ApiError(400, "INVALID_CURSOR", "Некорректный курсор пагинации") from None


# --- акции и события ---------------------------------------------------------------


async def list_items[R: BaseModel](
    session: AsyncSession,
    model: type[AdminContent],
    read_schema: type[R],
    *,
    status: ContentStatus | None,
    q: str | None,
    cursor: str | None,
    limit: int,
) -> Page[R]:
    decoded = decode_admin_cursor(cursor) if cursor is not None else None
    rows = await repository.list_for_admin(
        session, model, limit=limit, status=status, q=q, cursor=decoded
    )
    items = rows[:limit]
    return Page[read_schema](
        items=[read_schema.model_validate(item) for item in items],
        next_cursor=encode_admin_cursor(items[-1]) if len(rows) > limit else None,
    )


async def _get_or_404[T: AdminContent](
    session: AsyncSession, model: type[T], item_id: UUID, for_update: bool = False
) -> T:
    item = await repository.get_for_admin(session, model, item_id, for_update=for_update)
    if item is None:
        code, message = _NOT_FOUND[model]
        raise ApiError(404, code, message)
    return item


async def get_item[T: AdminContent](session: AsyncSession, model: type[T], item_id: UUID) -> T:
    return await _get_or_404(session, model, item_id)


async def create_item[T: AdminContent](session: AsyncSession, model: type[T], data: BaseModel) -> T:
    """Новая запись всегда создаётся черновиком."""
    item = model(**data.model_dump(), status=ContentStatus.DRAFT)
    session.add(item)
    await session.commit()
    await session.refresh(item)
    return item


def _check_period(item: AdminContent) -> None:
    if item.starts_at is not None and item.ends_at is not None and item.ends_at <= item.starts_at:
        raise _validation_error(
            [{"field": "ends_at", "message": "ends_at должен быть позже starts_at"}]
        )


def _check_required_for_publish(item: AdminContent) -> None:
    missing = [
        field
        for field in REQUIRED_FOR_PUBLISH[type(item)]
        if getattr(item, field) is None or getattr(item, field) == ""
    ]
    if missing:
        raise _validation_error(
            [{"field": field, "message": "Обязательно для публикации"} for field in missing]
        )


async def update_item[T: AdminContent](
    session: AsyncSession, model: type[T], item_id: UUID, data: BaseModel
) -> T:
    """Меняет только переданные поля. Изменения опубликованной записи сразу видны клиентам."""
    item = await _get_or_404(session, model, item_id, for_update=True)
    changes: dict[str, Any] = data.model_dump(include=data.model_fields_set)
    for field, value in changes.items():
        setattr(item, field, value)

    _check_period(item)
    # Опубликованная или снятая запись должна оставаться пригодной для публикации
    if item.status != ContentStatus.DRAFT:
        _check_required_for_publish(item)

    await session.commit()
    await session.refresh(item)
    return item


async def change_status[T: AdminContent](
    session: AsyncSession, model: type[T], item_id: UUID, target: ContentStatus
) -> T:
    item = await _get_or_404(session, model, item_id, for_update=True)
    if (item.status, target) not in ALLOWED_TRANSITIONS:
        raise ApiError(
            409,
            "INVALID_STATUS_TRANSITION",
            "Недопустимая смена статуса",
            {"from": item.status.value, "to": target.value},
        )
    if target == ContentStatus.PUBLISHED:
        _check_required_for_publish(item)
        _check_period(item)

    item.status = target
    await session.commit()
    await session.refresh(item)
    return item


# --- изображения -------------------------------------------------------------------


def detect_image_type(data: bytes) -> tuple[str, str] | None:
    """Тип по содержимому файла, а не по заголовкам клиента: (content_type, расширение)."""
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", "jpg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", "png"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp", "webp"
    return None


async def upload_image(storage: ImageStorage, file: UploadFile) -> str:
    data = await file.read(MAX_IMAGE_BYTES + 1)
    if len(data) > MAX_IMAGE_BYTES:
        raise ApiError(
            422,
            "IMAGE_TOO_LARGE",
            "Изображение больше 5 МБ",
            {"max_bytes": MAX_IMAGE_BYTES},
        )

    detected = detect_image_type(data)
    if detected is None:
        raise ApiError(
            422,
            "UNSUPPORTED_IMAGE_TYPE",
            "Поддерживаются только JPEG, PNG и WebP",
            {"allowed": ["image/jpeg", "image/png", "image/webp"]},
        )
    content_type, extension = detected

    # Имя от клиента не используется
    key = f"content/{uuid4().hex}.{extension}"
    try:
        return await storage.put(key, data, content_type)
    except StorageError:
        raise ApiError(
            503,
            "IMAGE_STORAGE_UNAVAILABLE",
            "Хранилище изображений недоступно, попробуйте позже",
        ) from None
