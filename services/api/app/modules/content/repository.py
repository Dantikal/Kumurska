"""Запросы к базе данных."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, or_, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.content.models import (
    ContentStatus,
    Event,
    LegalDocument,
    LegalDocumentStatus,
    LegalDocumentType,
    Promotion,
)


async def get_upcoming_events(
    session: AsyncSession,
    now: datetime,
    limit: int,
    cursor: tuple[datetime, UUID] | None = None,
) -> list[Event]:
    query = select(Event).where(
        Event.status == ContentStatus.PUBLISHED,
        or_(
            Event.ends_at > now,
            and_(
                Event.ends_at.is_(None),
                Event.starts_at > now,
            ),
        ),
    )

    if cursor is not None:
        cursor_starts_at, cursor_id = cursor

        query = query.where(
            or_(
                Event.starts_at > cursor_starts_at,
                (Event.starts_at == cursor_starts_at) & (Event.id > cursor_id),
            )
        )

    query = query.order_by(
        Event.starts_at.asc(),
        Event.id.asc(),
    ).limit(limit + 1)

    result = await session.scalars(query)

    return list(result.all())


async def get_latest_published_document(
    session: AsyncSession,
    document_type: LegalDocumentType,
) -> LegalDocument | None:
    query = (
        select(LegalDocument)
        .where(
            LegalDocument.type == document_type,
            LegalDocument.status == LegalDocumentStatus.PUBLISHED,
        )
        .order_by(LegalDocument.version.desc())
        .limit(1)
    )

    return await session.scalar(query)


# --- админка (US-17) -------------------------------------------------------------

AdminContent = Promotion | Event


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


async def list_for_admin[T: AdminContent](
    session: AsyncSession,
    model: type[T],
    limit: int,
    status: ContentStatus | None = None,
    q: str | None = None,
    cursor: tuple[datetime, UUID] | None = None,
) -> list[T]:
    """Все записи, включая черновики, от новых к старым. Возвращает limit + 1 запись."""
    query = select(model)
    if status is not None:
        query = query.where(model.status == status)
    if q:
        query = query.where(model.title.ilike(f"%{_escape_like(q)}%", escape="\\"))
    if cursor is not None:
        query = query.where(tuple_(model.created_at, model.id) < cursor)

    query = query.order_by(model.created_at.desc(), model.id.desc()).limit(limit + 1)
    return list((await session.scalars(query)).all())


async def get_for_admin[T: AdminContent](
    session: AsyncSession,
    model: type[T],
    item_id: UUID,
    for_update: bool = False,
) -> T | None:
    query = select(model).where(model.id == item_id)
    if for_update:
        # Параллельные publish/PATCH одной записи выполняются по очереди
        query = query.with_for_update()
    return await session.scalar(query)
