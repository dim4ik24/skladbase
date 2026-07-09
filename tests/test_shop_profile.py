"""
Назва/лого магазину: acceptance tests.

Сценарії:
  1. PATCH /api/shop — оновити name → 200, name збережено.
  2. PATCH /api/shop — порожнє ім'я → 422.
  3. POST /api/shop/logo — завантажити лого → URL збережено у shop.logo_url.
  4. POST /api/shop/logo не-owner (manager) → 403.
  5. DELETE /api/shop/logo → 204, logo_url = None.

R2-клієнт мокається (aioboto3.Session) — реальний R2 не зачіпається.
"""
from __future__ import annotations

import io

import aioboto3
import pytest
from httpx import AsyncClient
from PIL import Image

from app import db as db_module
from app.config import settings
from app.models import MemberRole, Membership, Shop
from tests.conftest import get_system_role_id, make_init_data

HEADER = "X-Telegram-Init-Data"


# --------------------------------------------------------------------------- #
#  Helpers
# --------------------------------------------------------------------------- #

async def _bootstrap(client: AsyncClient, tg_id: int, name: str = "Тест") -> tuple[str, int]:
    init_data = make_init_data(tg_id, first_name=name)
    r = await client.get("/api/me", headers={HEADER: init_data})
    assert r.status_code == 200
    return init_data, r.json()["shop_id"]


async def _make_manager(shop_id: int, tg_id: int) -> None:
    role_id = await get_system_role_id(shop_id, "Менеджер")
    async with db_module.async_session() as s:
        s.add(Membership(shop_id=shop_id, tg_id=tg_id, role=MemberRole.manager, role_id=role_id))
        await s.commit()


def _make_image_bytes(size: tuple[int, int] = (200, 200)) -> bytes:
    image = Image.new("RGB", size, color=(50, 100, 200))
    buf = io.BytesIO()
    image.save(buf, format="JPEG")
    return buf.getvalue()


# --------------------------------------------------------------------------- #
#  R2 mock
# --------------------------------------------------------------------------- #

class _FakeS3Client:
    calls: list[dict] = []

    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self) -> "_FakeS3Client":
        return self

    async def __aexit__(self, *exc_info) -> bool:
        return False

    async def put_object(self, **kwargs) -> dict:
        _FakeS3Client.calls.append({"op": "put", **kwargs})
        return {}

    async def delete_object(self, **kwargs) -> dict:
        _FakeS3Client.calls.append({"op": "delete", **kwargs})
        return {}


class _FakeR2Session:
    def __init__(self, *args, **kwargs) -> None:
        pass

    def client(self, *args, **kwargs) -> _FakeS3Client:
        return _FakeS3Client()


@pytest.fixture(autouse=True)
def _patch_r2(monkeypatch: pytest.MonkeyPatch) -> None:
    _FakeS3Client.calls.clear()
    monkeypatch.setattr(aioboto3, "Session", _FakeR2Session)
    monkeypatch.setattr(settings, "R2_PUBLIC_URL", "https://cdn.example.test")
    monkeypatch.setattr(settings, "R2_ACCOUNT_ID", "test-account")
    monkeypatch.setattr(settings, "R2_ACCESS_KEY", "test-access-key")
    monkeypatch.setattr(settings, "R2_SECRET_KEY", "test-secret-key")
    monkeypatch.setattr(settings, "R2_BUCKET", "test-bucket")


# --------------------------------------------------------------------------- #
#  Тест 1: PATCH name ok → 200, name збережено
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_patch_shop_name_ok(client: AsyncClient) -> None:
    init_data, shop_id = await _bootstrap(client, tg_id=5001)

    r = await client.patch(
        "/api/shop",
        json={"name": "Новий магазин"},
        headers={HEADER: init_data},
    )
    assert r.status_code == 200, r.text
    assert r.json()["shop_name"] == "Новий магазин"

    # Перевірити що збережено в БД
    async with db_module.async_session() as session:
        shop = await session.get(Shop, shop_id)
        assert shop is not None
        assert shop.name == "Новий магазин"


# --------------------------------------------------------------------------- #
#  Тест 2: PATCH порожнє ім'я → 422
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_patch_shop_name_empty_returns_422(client: AsyncClient) -> None:
    init_data, _shop_id = await _bootstrap(client, tg_id=5002)

    r = await client.patch(
        "/api/shop",
        json={"name": ""},
        headers={HEADER: init_data},
    )
    assert r.status_code == 422, r.text


# --------------------------------------------------------------------------- #
#  Тест 3: POST /api/shop/logo → URL збережено у shop.logo_url
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_upload_shop_logo_saves_url(client: AsyncClient) -> None:
    init_data, shop_id = await _bootstrap(client, tg_id=5003)

    r = await client.post(
        "/api/shop/logo",
        files={"file": ("logo.jpg", _make_image_bytes(), "image/jpeg")},
        headers={HEADER: init_data},
    )
    assert r.status_code == 200, r.text
    logo_url = r.json()["logo_url"]
    assert logo_url.startswith("https://cdn.example.test/")

    # Перевірити збережено в БД
    async with db_module.async_session() as session:
        shop = await session.get(Shop, shop_id)
        assert shop is not None
        assert shop.logo_url == logo_url

    # PUT викликаний у R2
    put_calls = [c for c in _FakeS3Client.calls if c["op"] == "put"]
    assert len(put_calls) == 1
    assert "shops/" in put_calls[0]["Key"]
    assert "/logo/" in put_calls[0]["Key"]


# --------------------------------------------------------------------------- #
#  Тест 4: POST /api/shop/logo не-owner (manager) → 403
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_upload_shop_logo_manager_returns_403(client: AsyncClient) -> None:
    _owner_init, shop_id = await _bootstrap(client, tg_id=5004, name="Власник")
    manager_tg_id = 5005
    await _make_manager(shop_id, manager_tg_id)
    manager_init = make_init_data(manager_tg_id, first_name="Менеджер")

    r = await client.post(
        "/api/shop/logo",
        files={"file": ("logo.jpg", _make_image_bytes(), "image/jpeg")},
        headers={HEADER: manager_init},
    )
    assert r.status_code == 403, r.text
    assert _FakeS3Client.calls == []


# --------------------------------------------------------------------------- #
#  Тест 5: DELETE /api/shop/logo → 204, logo_url = None
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_delete_shop_logo_clears_url(client: AsyncClient) -> None:
    init_data, shop_id = await _bootstrap(client, tg_id=5006)

    # Спершу завантажити лого
    r_upload = await client.post(
        "/api/shop/logo",
        files={"file": ("logo.jpg", _make_image_bytes(), "image/jpeg")},
        headers={HEADER: init_data},
    )
    assert r_upload.status_code == 200

    # Видалити
    r_del = await client.delete("/api/shop/logo", headers={HEADER: init_data})
    assert r_del.status_code == 204, r_del.text

    # Перевірити що logo_url = None в БД
    async with db_module.async_session() as session:
        shop = await session.get(Shop, shop_id)
        assert shop is not None
        assert shop.logo_url is None

    # delete_object викликаний у R2
    delete_calls = [c for c in _FakeS3Client.calls if c["op"] == "delete"]
    assert len(delete_calls) == 1
