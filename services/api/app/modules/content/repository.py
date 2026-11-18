"""Запросы к базе данных."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, or_, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.content.models import ContentStatus, Event, Promotion


async def get_active_promotions(
    session: AsyncSession,
    now: datetime,
    limit: int,
    cursor: tuple[datetime, UUID] | None = None,
) -> list[Promotion]:
    query = select(Promotion).where(
        Promotion.status == ContentStatus.PUBLISHED,
        Promotion.starts_at <= now,
        Promotion.ends_at > now,
    )
    if cursor is not None:
        query = query.where(tuple_(Promotion.starts_at, Promotion.id) < cursor)

    query = query.order_by(Promotion.starts_at.desc(), Promotion.id.desc()).limit(limit + 1)
    return list((await session.scalars(query)).all())


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
