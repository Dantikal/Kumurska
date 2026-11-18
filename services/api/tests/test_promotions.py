from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from app.modules.content import repository
from app.modules.content.models import ContentStatus, Promotion

URL = "/api/v1/content/promotions"


@pytest.mark.anyio
async def test_visibility_at_start_and_end(session_factory):
    now = datetime(2026, 11, 18, 12, tzinfo=UTC)
    tick = timedelta(microseconds=1)
    cases = [
        ("Starting", ContentStatus.PUBLISHED, now, now + tick),
        ("Ending", ContentStatus.PUBLISHED, now - tick, now),
        ("Later", ContentStatus.PUBLISHED, now + tick, now + 2 * tick),
        ("Draft", ContentStatus.DRAFT, now - tick, now + tick),
        ("Withdrawn", ContentStatus.UNPUBLISHED, now - tick, now + tick),
    ]
    async with session_factory() as session:
        session.add_all(
            Promotion(title=title, status=status, starts_at=start, ends_at=end)
            for title, status, start, end in cases
        )
        await session.flush()
        visible = await repository.get_active_promotions(session, now, limit=20)
        assert [item.title for item in visible] == ["Starting"]


@pytest.mark.anyio
async def test_promotions_endpoint_pages_newest_first(api, session_factory):
    now = datetime.now(UTC)
    async with session_factory() as session:
        for number, days_ago in [(1, 1), (2, 1), (3, 2)]:
            session.add(
                Promotion(
                    id=UUID(int=number),
                    title=f"Offer {number}",
                    description="Weekend discount",
                    image_url="/media/banner.jpg" if number == 2 else None,
                    starts_at=now - timedelta(days=days_ago),
                    ends_at=now + timedelta(days=1),
                    status=ContentStatus.PUBLISHED,
                )
            )
        await session.commit()

    params = {"limit": 1}
    titles = []
    for _ in range(3):
        response = await api.get(URL, params=params)
        assert response.status_code == 200
        page = response.json()
        (item,) = page["items"]
        titles.append(item["title"])
        if len(titles) == 1:
            assert item["image_url"] == "/media/banner.jpg"
            assert item["description"] == "Weekend discount"
        if len(titles) < 3:
            assert page["next_cursor"]
            params["cursor"] = page["next_cursor"]
    assert titles == ["Offer 2", "Offer 1", "Offer 3"]
    assert page["next_cursor"] is None


@pytest.mark.anyio
async def test_empty_promotions_page(api):
    response = await api.get(URL)
    assert response.status_code == 200
    assert response.json() == {"items": [], "next_cursor": None}


@pytest.mark.parametrize(
    ("params", "status", "code"),
    [
        ({"cursor": "broken"}, 400, "INVALID_CURSOR"),
        ({"limit": 0}, 422, "VALIDATION_ERROR"),
        ({"limit": 101}, 422, "VALIDATION_ERROR"),
    ],
)
def test_invalid_promotions_parameters(client, params, status, code):
    response = client.get(URL, params=params)
    assert response.status_code == status
    assert response.json()["error"]["code"] == code
