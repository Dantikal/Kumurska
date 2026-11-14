"""Бизнес-логика и транзакции."""

import base64
import binascii
import json
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.core.schemas import Page
from app.modules.content import repository
from app.modules.content.models import Event
from app.modules.content.schemas import EventRead


def encode_cursor(event: Event) -> str:
    cursor_data = {
        "starts_at": event.starts_at.isoformat(),
        "id": str(event.id),
    }

    cursor_json = json.dumps(cursor_data)

    return base64.urlsafe_b64encode(cursor_json.encode()).decode()


def decode_cursor(
    cursor: str,
) -> tuple[datetime, UUID]:
    try:
        decoded_bytes = base64.b64decode(
            cursor,
            altchars=b"-_",
            validate=True,
        )
        decoded_json = decoded_bytes.decode()
        cursor_data = json.loads(decoded_json)
        if not isinstance(cursor_data, dict):
            raise ValueError("Cursor must contain a JSON object")

        starts_at = datetime.fromisoformat(cursor_data["starts_at"])
        event_id = UUID(cursor_data["id"])

        if starts_at.utcoffset() is None:
            raise ValueError("Cursor datetime must include timezone")

        return starts_at, event_id

    except (ValueError, TypeError, KeyError, binascii.Error):
        raise ApiError(
            400,
            "INVALID_CURSOR",
            "Некорректный курсор пагинации",
        ) from None


async def list_upcoming_events(
    session: AsyncSession,
    cursor: str | None,
    limit: int,
) -> Page[EventRead]:
    now = datetime.now(UTC)

    decoded_cursor = decode_cursor(cursor) if cursor is not None else None

    events = await repository.get_upcoming_events(
        session=session,
        now=now,
        limit=limit,
        cursor=decoded_cursor,
    )

    has_next_page = len(events) > limit
    items = events[:limit]

    next_cursor = encode_cursor(items[-1]) if has_next_page else None

    return Page[EventRead](
        items=items,
        next_cursor=next_cursor,
    )
