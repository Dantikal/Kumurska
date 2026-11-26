"""Админские методы акций и событий (US-17)."""

import re
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.integrations.storage import FakeImageStorage, StorageError, get_image_storage
from app.main import app
from app.modules.admin.dependencies import Staff, get_current_staff
from app.modules.content import admin_service, repository

ADMIN = "/api/v1/admin/content"
NOW = datetime.now(UTC)
STARTS = (NOW - timedelta(days=1)).isoformat()
ENDS = (NOW + timedelta(days=7)).isoformat()

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
WEBP = b"RIFF\x24\x00\x00\x00WEBPVP8 " + b"\x00" * 64
GIF = b"GIF89a" + b"\x00" * 64


def _as_staff(*roles: str) -> None:
    staff = Staff(id=uuid4(), roles=frozenset(roles))
    app.dependency_overrides[get_current_staff] = lambda: staff


@pytest.fixture
def storage() -> FakeImageStorage:
    return FakeImageStorage()


@pytest.fixture
async def admin(api, storage):
    """Клиент от имени сотрудника с ролью content_manager."""
    _as_staff("content_manager")
    app.dependency_overrides[get_image_storage] = lambda: storage
    return api


async def _create(admin, kind: str, **fields) -> dict:
    body = {"title": "Скидка 20%", **fields}
    response = await admin.post(f"{ADMIN}/{kind}", json=body)
    assert response.status_code == 201, response.text
    return response.json()


async def _action(admin, kind: str, item_id: str, action: str):
    return await admin.post(f"{ADMIN}/{kind}/{item_id}/{action}")


# --- доступ ------------------------------------------------------------------------

SOME_ID = str(uuid4())
ALL_METHODS = [
    ("get", f"{ADMIN}/promotions"),
    ("post", f"{ADMIN}/promotions"),
    ("get", f"{ADMIN}/promotions/{SOME_ID}"),
    ("patch", f"{ADMIN}/promotions/{SOME_ID}"),
    ("post", f"{ADMIN}/promotions/{SOME_ID}/publish"),
    ("post", f"{ADMIN}/promotions/{SOME_ID}/unpublish"),
    ("get", f"{ADMIN}/events"),
    ("post", f"{ADMIN}/events"),
    ("get", f"{ADMIN}/events/{SOME_ID}"),
    ("patch", f"{ADMIN}/events/{SOME_ID}"),
    ("post", f"{ADMIN}/events/{SOME_ID}/publish"),
    ("post", f"{ADMIN}/events/{SOME_ID}/unpublish"),
    ("post", f"{ADMIN}/images"),
]


def test_every_admin_content_route_is_covered():
    """Новый метод без проверки доступа не пройдёт незамеченным."""
    expected = {(m, re.sub(SOME_ID, "{id}", p)) for m, p in ALL_METHODS}
    actual = {
        (method, path)
        for path, item in app.openapi()["paths"].items()
        if path.startswith(ADMIN)
        for method in item
    }
    assert actual == expected


@pytest.mark.parametrize(("method", "path"), ALL_METHODS)
def test_without_content_manager_role_returns_403(client, method, path):
    _as_staff("cashier")
    # Тело пустое: проверка роли срабатывает раньше валидации запроса
    response = client.request(method, path)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


@pytest.mark.parametrize(("method", "path"), ALL_METHODS)
def test_without_staff_returns_401(client, method, path):
    # Заглушка до US-36: сотрудника нет ни у одного запроса
    response = client.request(method, path)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "NOT_AUTHENTICATED"


# --- создание и видимость ----------------------------------------------------------

needs_us08 = pytest.mark.skipif(
    not hasattr(repository, "get_active_promotions"),
    reason="Клиентская выборка акций появится в US-08 (PR #9)",
)


async def _client_promotion_ids(session_factory) -> set:
    async with session_factory() as session:
        rows = await repository.get_active_promotions(session, datetime.now(UTC), limit=100)
        return {str(row.id) for row in rows}


@pytest.mark.anyio
async def test_promotion_is_created_as_draft(admin):
    response = await admin.post(
        f"{ADMIN}/promotions",
        json={"title": "  Чёрная пятница  ", "starts_at": STARTS, "ends_at": ENDS},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "draft"
    assert data["title"] == "Чёрная пятница"

    response = await admin.get(f"{ADMIN}/promotions/{data['id']}")
    assert response.status_code == 200
    assert response.json() == data


@pytest.mark.anyio
async def test_status_cannot_be_set_on_create(admin):
    response = await admin.post(f"{ADMIN}/promotions", json={"title": "X", "status": "published"})
    assert response.status_code == 422


@pytest.mark.anyio
async def test_draft_can_be_saved_without_dates(admin):
    promotion = await _create(admin, "promotions")
    event = await _create(admin, "events")
    assert promotion["starts_at"] is None and promotion["ends_at"] is None
    assert event["starts_at"] is None


@needs_us08
@pytest.mark.anyio
async def test_promotion_visible_to_clients_only_while_published(admin, session_factory):
    promotion = await _create(admin, "promotions", starts_at=STARTS, ends_at=ENDS)
    assert promotion["id"] not in await _client_promotion_ids(session_factory)

    assert (await _action(admin, "promotions", promotion["id"], "publish")).status_code == 200
    assert promotion["id"] in await _client_promotion_ids(session_factory)

    assert (await _action(admin, "promotions", promotion["id"], "unpublish")).status_code == 200
    assert promotion["id"] not in await _client_promotion_ids(session_factory)

    assert (await _action(admin, "promotions", promotion["id"], "publish")).status_code == 200
    assert promotion["id"] in await _client_promotion_ids(session_factory)


@pytest.mark.anyio
async def test_event_visible_to_clients_only_while_published(admin):
    starts = (NOW + timedelta(days=2)).isoformat()
    event = await _create(admin, "events", starts_at=starts)

    async def client_ids() -> set:
        response = await admin.get("/api/v1/content/events")
        assert response.status_code == 200
        return {item["id"] for item in response.json()["items"]}

    assert event["id"] not in await client_ids()

    published = await _action(admin, "events", event["id"], "publish")
    assert published.status_code == 200
    assert published.json()["status"] == "published"
    assert event["id"] in await client_ids()

    unpublished = await _action(admin, "events", event["id"], "unpublish")
    assert unpublished.json()["status"] == "unpublished"
    assert event["id"] not in await client_ids()

    # Снятое с публикации остаётся в админке
    response = await admin.get(f"{ADMIN}/events/{event['id']}")
    assert response.json()["status"] == "unpublished"


@pytest.mark.anyio
async def test_edit_of_published_event_is_visible_to_clients(admin):
    event = await _create(admin, "events", starts_at=(NOW + timedelta(days=2)).isoformat())
    await _action(admin, "events", event["id"], "publish")

    response = await admin.patch(f"{ADMIN}/events/{event['id']}", json={"title": "Новое название"})
    assert response.status_code == 200
    assert response.json()["status"] == "published"

    items = (await admin.get("/api/v1/content/events")).json()["items"]
    assert [item["title"] for item in items] == ["Новое название"]


# --- переходы статусов -------------------------------------------------------------


@pytest.mark.parametrize("kind", ["promotions", "events"])
@pytest.mark.anyio
async def test_forbidden_transitions_return_409(admin, kind):
    item = await _create(admin, kind, starts_at=STARTS, ends_at=ENDS)

    async def expect_409(action: str, current: str) -> None:
        response = await _action(admin, kind, item["id"], action)
        assert response.status_code == 409
        error = response.json()["error"]
        assert error["code"] == "INVALID_STATUS_TRANSITION"
        assert error["details"]["from"] == current

    await expect_409("unpublish", "draft")
    await _action(admin, kind, item["id"], "publish")
    await expect_409("publish", "published")
    await _action(admin, kind, item["id"], "unpublish")
    await expect_409("unpublish", "unpublished")


@pytest.mark.parametrize("kind", ["promotions", "events"])
@pytest.mark.anyio
async def test_unknown_id_returns_404(admin, kind):
    code = "PROMOTION_NOT_FOUND" if kind == "promotions" else "EVENT_NOT_FOUND"
    for response in [
        await admin.get(f"{ADMIN}/{kind}/{uuid4()}"),
        await admin.patch(f"{ADMIN}/{kind}/{uuid4()}", json={"title": "X"}),
        await _action(admin, kind, str(uuid4()), "publish"),
    ]:
        assert response.status_code == 404
        assert response.json()["error"]["code"] == code


# --- обязательные поля и даты ------------------------------------------------------


@pytest.mark.parametrize(
    ("kind", "fields", "missing"),
    [
        ("promotions", {}, ["starts_at", "ends_at"]),
        ("promotions", {"starts_at": STARTS}, ["ends_at"]),
        ("promotions", {"ends_at": ENDS}, ["starts_at"]),
        ("events", {}, ["starts_at"]),
    ],
)
@pytest.mark.anyio
async def test_publish_without_required_fields_returns_422(admin, kind, fields, missing):
    item = await _create(admin, kind, **fields)
    response = await _action(admin, kind, item["id"], "publish")
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert [f["field"] for f in error["details"]["fields"]] == missing

    # Статус не изменился
    assert (await admin.get(f"{ADMIN}/{kind}/{item['id']}")).json()["status"] == "draft"


@pytest.mark.anyio
async def test_draft_becomes_publishable_after_patch(admin):
    promotion = await _create(admin, "promotions")
    response = await admin.patch(
        f"{ADMIN}/promotions/{promotion['id']}", json={"starts_at": STARTS, "ends_at": ENDS}
    )
    assert response.status_code == 200
    response = await _action(admin, "promotions", promotion["id"], "publish")
    assert response.status_code == 200
    assert response.json()["status"] == "published"


@pytest.mark.parametrize("kind", ["promotions", "events"])
@pytest.mark.anyio
async def test_ends_at_must_be_after_starts_at_on_create(admin, kind):
    response = await admin.post(
        f"{ADMIN}/{kind}", json={"title": "X", "starts_at": ENDS, "ends_at": STARTS}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    response = await admin.post(
        f"{ADMIN}/{kind}", json={"title": "X", "starts_at": STARTS, "ends_at": STARTS}
    )
    assert response.status_code == 422


@pytest.mark.anyio
async def test_ends_at_checked_against_stored_starts_at_on_patch(admin):
    promotion = await _create(admin, "promotions", starts_at=STARTS, ends_at=ENDS)
    response = await admin.patch(
        f"{ADMIN}/promotions/{promotion['id']}",
        json={"ends_at": (NOW - timedelta(days=2)).isoformat()},
    )
    assert response.status_code == 422
    assert response.json()["error"]["details"]["fields"][0]["field"] == "ends_at"

    stored = (await admin.get(f"{ADMIN}/promotions/{promotion['id']}")).json()
    assert stored["ends_at"] == promotion["ends_at"]


@pytest.mark.anyio
async def test_dates_without_timezone_are_rejected(admin):
    response = await admin.post(
        f"{ADMIN}/promotions", json={"title": "X", "starts_at": "2026-12-01T10:00:00"}
    )
    assert response.status_code == 422


@pytest.mark.parametrize("state", ["published", "unpublished"])
@pytest.mark.anyio
async def test_required_fields_cannot_be_cleared_after_publish(admin, state):
    promotion = await _create(admin, "promotions", starts_at=STARTS, ends_at=ENDS)
    await _action(admin, "promotions", promotion["id"], "publish")
    if state == "unpublished":
        await _action(admin, "promotions", promotion["id"], "unpublish")

    response = await admin.patch(f"{ADMIN}/promotions/{promotion['id']}", json={"ends_at": None})
    assert response.status_code == 422
    assert response.json()["error"]["details"]["fields"][0]["field"] == "ends_at"


@pytest.mark.anyio
async def test_patch_changes_only_passed_fields(admin):
    promotion = await _create(
        admin, "promotions", description="Описание", starts_at=STARTS, ends_at=ENDS
    )
    response = await admin.patch(
        f"{ADMIN}/promotions/{promotion['id']}", json={"description": None}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["description"] is None
    assert data["title"] == promotion["title"]
    assert data["starts_at"] == promotion["starts_at"]


@pytest.mark.parametrize("body", [{"title": None}, {"title": "   "}, {"status": "published"}])
@pytest.mark.anyio
async def test_invalid_patch_returns_422(admin, body):
    promotion = await _create(admin, "promotions")
    response = await admin.patch(f"{ADMIN}/promotions/{promotion['id']}", json=body)
    assert response.status_code == 422


# --- список: фильтр, поиск, пагинация ----------------------------------------------


@pytest.mark.anyio
async def test_list_includes_drafts_and_filters_by_status(admin):
    draft = await _create(admin, "promotions", title="Черновик")
    published = await _create(
        admin, "promotions", title="Опубликована", starts_at=STARTS, ends_at=ENDS
    )
    withdrawn = await _create(admin, "promotions", title="Снята", starts_at=STARTS, ends_at=ENDS)
    await _action(admin, "promotions", published["id"], "publish")
    await _action(admin, "promotions", withdrawn["id"], "publish")
    await _action(admin, "promotions", withdrawn["id"], "unpublish")

    async def titles(**params) -> list[str]:
        response = await admin.get(f"{ADMIN}/promotions", params=params)
        assert response.status_code == 200
        return [item["title"] for item in response.json()["items"]]

    assert await titles() == ["Снята", "Опубликована", "Черновик"]
    assert await titles(status="draft") == [draft["title"]]
    assert await titles(status="published") == ["Опубликована"]
    assert await titles(status="unpublished") == ["Снята"]

    response = await admin.get(f"{ADMIN}/promotions", params={"status": "archived"})
    assert response.status_code == 422


@pytest.mark.anyio
async def test_search_by_title(admin):
    for title in ["Скидка на помады", "СКИДКА на тушь", "Подарок за покупку", "Скидка 100%"]:
        await _create(admin, "events", title=title)

    async def titles(**params) -> set[str]:
        response = await admin.get(f"{ADMIN}/events", params=params)
        assert response.status_code == 200
        return {item["title"] for item in response.json()["items"]}

    assert await titles(q="скидка") == {"Скидка на помады", "СКИДКА на тушь", "Скидка 100%"}
    assert await titles(q="подарок") == {"Подарок за покупку"}
    # % и _ ищутся как обычные символы
    assert await titles(q="%") == {"Скидка 100%"}
    assert await titles(q="_") == set()
    assert await titles(q="скидка", status="published") == set()


@pytest.mark.anyio
async def test_list_pagination(admin):
    for number in range(5):
        await _create(admin, "promotions", title=f"Акция {number}")

    seen: list[str] = []
    params: dict = {"limit": 2}
    for _ in range(3):
        page = (await admin.get(f"{ADMIN}/promotions", params=params)).json()
        seen += [item["title"] for item in page["items"]]
        params["cursor"] = page["next_cursor"]
    assert seen == [f"Акция {n}" for n in range(4, -1, -1)]
    assert page["next_cursor"] is None

    response = await admin.get(f"{ADMIN}/promotions", params={"cursor": "broken"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_CURSOR"


# --- изображения -------------------------------------------------------------------


@pytest.mark.parametrize(("content", "extension"), [(JPEG, "jpg"), (PNG, "png"), (WEBP, "webp")])
@pytest.mark.anyio
async def test_upload_image(admin, storage, content, extension):
    response = await admin.post(
        f"{ADMIN}/images",
        files={"file": ("../../etc/passwd.exe", content, "application/octet-stream")},
    )
    assert response.status_code == 201
    image_url = response.json()["image_url"]

    # Имя генерирует сервер, имя от клиента не используется
    (key,) = storage.files
    assert re.fullmatch(rf"content/[0-9a-f]{{32}}\.{extension}", key)
    assert image_url == f"{storage.public_url}/{key}"
    assert storage.files[key] == (content, f"image/{'jpeg' if extension == 'jpg' else extension}")


@pytest.mark.parametrize(
    "upload",
    [
        ("banner.gif", GIF, "image/gif"),
        # Заголовки клиента не помогают: проверяется содержимое
        ("banner.jpg", b"<svg xmlns='http://www.w3.org/2000/svg'/>", "image/jpeg"),
        ("empty.png", b"", "image/png"),
    ],
)
@pytest.mark.anyio
async def test_upload_unsupported_type_returns_422(admin, storage, upload):
    response = await admin.post(f"{ADMIN}/images", files={"file": upload})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "UNSUPPORTED_IMAGE_TYPE"
    assert storage.files == {}


@pytest.mark.anyio
async def test_upload_too_large_returns_422(admin, storage):
    exactly_max = PNG + b"\x00" * (admin_service.MAX_IMAGE_BYTES - len(PNG))
    response = await admin.post(f"{ADMIN}/images", files={"file": ("a.png", exactly_max)})
    assert response.status_code == 201

    too_large = exactly_max + b"\x00"
    response = await admin.post(f"{ADMIN}/images", files={"file": ("b.png", too_large)})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "IMAGE_TOO_LARGE"
    assert len(storage.files) == 1


@pytest.mark.anyio
async def test_upload_without_file_returns_422(admin):
    response = await admin.post(f"{ADMIN}/images")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.anyio
async def test_upload_when_storage_is_down_returns_503(admin):
    class BrokenStorage:
        async def put(self, key: str, data: bytes, content_type: str) -> str:
            raise StorageError("down")

    app.dependency_overrides[get_image_storage] = BrokenStorage
    response = await admin.post(f"{ADMIN}/images", files={"file": ("a.png", PNG)})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "IMAGE_STORAGE_UNAVAILABLE"
