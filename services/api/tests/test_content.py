from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.errors import ApiError
from app.modules.content import repository, service
from app.modules.content.models import (
    ContentStatus,
    Event,
    LegalDocument,
    LegalDocumentStatus,
    LegalDocumentType,
)


@pytest.mark.anyio
async def test_repository_returns_only_upcoming_published_events(session_factory):
    now = datetime.now(UTC)

    first_event = Event(
        title="Первая будущая мастер-класс",
        starts_at=now + timedelta(days=2),
        ends_at=now + timedelta(days=2, hours=2),
        is_period=False,
        status=ContentStatus.PUBLISHED,
    )

    second_event = Event(
        title="Вторая будущая мастер-класс",
        starts_at=now + timedelta(days=1),
        ends_at=now + timedelta(days=1, hours=2),
        is_period=False,
        status=ContentStatus.PUBLISHED,
    )

    draft_event = Event(
        title="Черновик",
        starts_at=now + timedelta(days=3),
        ends_at=now + timedelta(days=3, hours=2),
        is_period=False,
        status=ContentStatus.DRAFT,
    )

    started_event = Event(
        title="Уже начавшееся мероприятие",
        starts_at=now - timedelta(hours=1),
        ends_at=now + timedelta(hours=2),
        is_period=False,
        status=ContentStatus.PUBLISHED,
    )

    async with session_factory() as session:
        session.add_all(
            [
                first_event,
                second_event,
                draft_event,
                started_event,
            ]
        )
        await session.flush()

        result = await repository.get_upcoming_events(
            session=session,
            now=now,
            limit=20,
        )

        assert [event.id for event in result] == [
            started_event.id,
            second_event.id,
            first_event.id,
        ]


@pytest.mark.anyio
async def test_service_paginates_upcoming_events(session_factory):
    now = datetime.now(UTC)

    events = [
        Event(
            title="Мероприятие через три дня",
            starts_at=now + timedelta(days=3),
            ends_at=now + timedelta(days=3, hours=2),
            is_period=False,
            status=ContentStatus.PUBLISHED,
        ),
        Event(
            title="Мероприятие через один день",
            starts_at=now + timedelta(days=1),
            ends_at=now + timedelta(days=1, hours=2),
            is_period=False,
            status=ContentStatus.PUBLISHED,
        ),
        Event(
            title="Мероприятие через два дня",
            starts_at=now + timedelta(days=2),
            ends_at=now + timedelta(days=2, hours=2),
            is_period=False,
            status=ContentStatus.PUBLISHED,
        ),
    ]

    async with session_factory() as session:
        session.add_all(events)
        await session.flush()

        first_page = await service.list_upcoming_events(
            session=session,
            cursor=None,
            limit=2,
        )

        assert len(first_page.items) == 2
        assert first_page.next_cursor is not None

        second_page = await service.list_upcoming_events(
            session=session,
            cursor=first_page.next_cursor,
            limit=2,
        )

        assert len(second_page.items) == 1
        assert second_page.next_cursor is None

        all_ids = [event.id for event in first_page.items + second_page.items]

        assert len(all_ids) == len(set(all_ids))
        assert len(all_ids) == 3


def test_decode_cursor_rejects_invalid_cursor():
    with pytest.raises(ApiError) as exc_info:
        service.decode_cursor("invalid_cursor")

    assert exc_info.value.status_code == 400


@pytest.mark.anyio
async def test_list_upcoming_events_endpoint(api, session_factory):
    now = datetime.now(UTC)

    events = [
        Event(
            title="Будущий мастер-класс",
            starts_at=now + timedelta(days=2),
            ends_at=now + timedelta(days=2, hours=2),
            is_period=False,
            status=ContentStatus.PUBLISHED,
        ),
        Event(
            title="Черновик мероприятия",
            starts_at=now + timedelta(days=1),
            ends_at=now + timedelta(days=1, hours=2),
            is_period=False,
            status=ContentStatus.DRAFT,
        ),
    ]

    async with session_factory() as session:
        session.add_all(events)
        await session.commit()

    response = await api.get("/api/v1/content/events")

    assert response.status_code == 200

    data = response.json()

    assert len(data["items"]) == 1
    assert data["items"][0]["title"] == "Будущий мастер-класс"
    assert data["next_cursor"] is None


@pytest.mark.anyio
async def test_list_events_returns_400_for_invalid_cursor(api):
    response = await api.get(
        "/api/v1/content/events",
        params={"cursor": "invalid_cursor"},
    )

    assert response.status_code == 400


@pytest.mark.anyio
async def test_cursor_pagination_with_same_start_time(session_factory):
    now = datetime.now(UTC)
    start_time = now + timedelta(days=2)

    first_event = Event(
        title="Первое мероприятие",
        starts_at=start_time,
        ends_at=start_time + timedelta(hours=2),
        is_period=False,
        status=ContentStatus.PUBLISHED,
    )

    second_event = Event(
        title="Второе мероприятие",
        starts_at=start_time,
        ends_at=start_time + timedelta(hours=2),
        is_period=False,
        status=ContentStatus.PUBLISHED,
    )

    async with session_factory() as session:
        session.add_all([first_event, second_event])
        await session.flush()

        first_page = await service.list_upcoming_events(
            session=session,
            cursor=None,
            limit=1,
        )

        assert len(first_page.items) == 1
        assert first_page.next_cursor is not None

        second_page = await service.list_upcoming_events(
            session=session,
            cursor=first_page.next_cursor,
            limit=1,
        )

        assert len(second_page.items) == 1
        assert second_page.next_cursor is None

        returned_ids = {
            first_page.items[0].id,
            second_page.items[0].id,
        }

        assert returned_ids == {first_event.id, second_event.id}


@pytest.mark.anyio
async def test_repository_returns_latest_published_document(session_factory):
    documents = [
        LegalDocument(
            type=LegalDocumentType.TERMS,
            version=1,
            title="Условия версии 1",
            content="Старые условия",
            status=LegalDocumentStatus.PUBLISHED,
        ),
        LegalDocument(
            type=LegalDocumentType.TERMS,
            version=2,
            title="Условия версии 2",
            content="Новые условия",
            status=LegalDocumentStatus.PUBLISHED,
        ),
        LegalDocument(
            type=LegalDocumentType.TERMS,
            version=3,
            title="Черновик версии 3",
            content="Ещё не опубликовано",
            status=LegalDocumentStatus.DRAFT,
        ),
    ]

    async with session_factory() as session:
        session.add_all(documents)
        await session.flush()

        result = await repository.get_latest_published_document(
            session=session,
            document_type=LegalDocumentType.TERMS,
        )

        assert result is not None
        assert result.version == 2
        assert result.title == "Условия версии 2"


@pytest.mark.anyio
async def test_repository_returns_none_when_only_draft_exists(session_factory):
    draft = LegalDocument(
        type=LegalDocumentType.PRIVACY,
        version=1,
        title="Черновик политики конфиденциальности",
        content="Временный текст",
        status=LegalDocumentStatus.DRAFT,
    )

    async with session_factory() as session:
        session.add(draft)
        await session.flush()

        result = await repository.get_latest_published_document(
            session=session,
            document_type=LegalDocumentType.PRIVACY,
        )

        assert result is None


@pytest.mark.anyio
async def test_service_raises_404_when_no_published_document(session_factory):
    async with session_factory() as session:
        with pytest.raises(ApiError) as exc_info:
            await service.get_legal_document(
                session=session,
                document_type=LegalDocumentType.TERMS,
            )

    assert exc_info.value.status_code == 404
    assert exc_info.value.code == "DOCUMENT_NOT_FOUND"


@pytest.mark.anyio
async def test_get_latest_published_legal_document_endpoint(api, session_factory):
    documents = [
        LegalDocument(
            type=LegalDocumentType.TERMS,
            version=1,
            title="Условия версии 1",
            content="Старые условия",
            status=LegalDocumentStatus.PUBLISHED,
        ),
        LegalDocument(
            type=LegalDocumentType.TERMS,
            version=2,
            title="Условия версии 2",
            content="Новые условия",
            status=LegalDocumentStatus.PUBLISHED,
        ),
        LegalDocument(
            type=LegalDocumentType.TERMS,
            version=3,
            title="Черновик версии 3",
            content="Неопубликованные условия",
            status=LegalDocumentStatus.DRAFT,
        ),
    ]

    async with session_factory() as session:
        session.add_all(documents)
        await session.commit()

    response = await api.get("/api/v1/content/documents/terms")

    assert response.status_code == 200

    data = response.json()

    assert data["type"] == "terms"
    assert data["version"] == 2
    assert data["title"] == "Условия версии 2"
    assert data["content"] == "Новые условия"
    assert data["status"] == "published"


@pytest.mark.anyio
async def test_get_latest_published_privacy_document_endpoint(api, session_factory):
    document = LegalDocument(
        type=LegalDocumentType.PRIVACY,
        version=1,
        title="Политика конфиденциальности",
        content="Текст политики конфиденциальности",
        status=LegalDocumentStatus.PUBLISHED,
    )

    async with session_factory() as session:
        session.add(document)
        await session.commit()

    response = await api.get("/api/v1/content/documents/privacy")

    assert response.status_code == 200

    data = response.json()

    assert data["type"] == "privacy"
    assert data["version"] == 1
    assert data["title"] == "Политика конфиденциальности"
    assert data["content"] == "Текст политики конфиденциальности"


@pytest.mark.anyio
async def test_get_legal_document_returns_404_when_not_found(api):
    response = await api.get("/api/v1/content/documents/terms")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "DOCUMENT_NOT_FOUND"


@pytest.mark.anyio
async def test_get_legal_document_returns_422_for_invalid_type(api):
    response = await api.get("/api/v1/content/documents/invalid")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.anyio
async def test_legal_document_requires_unique_type_and_version(session_factory):
    first_document = LegalDocument(
        type=LegalDocumentType.TERMS,
        version=1,
        title="Условия версии 1",
        content="Первый документ",
        status=LegalDocumentStatus.PUBLISHED,
    )

    duplicate_document = LegalDocument(
        type=LegalDocumentType.TERMS,
        version=1,
        title="Дубликат условий версии 1",
        content="Второй документ",
        status=LegalDocumentStatus.PUBLISHED,
    )

    async with session_factory() as session:
        session.add(first_document)
        await session.flush()

        session.add(duplicate_document)

        with pytest.raises(IntegrityError):
            await session.flush()

        await session.rollback()
