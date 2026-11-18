"""Запросы к базе данных."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.content.models import ContentStatus, Event


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
