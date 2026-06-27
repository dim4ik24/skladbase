"""
F2 — Галерея фото товару: acceptance tests.

Сценарії:
  1. upload платний → 201, position інкрементується
  2. upload free (photos:false) → 402
  3. upload 11-го фото → 409
  4. upload на frozen товар → 402
  5. cross-shop upload → 404
  6. delete ok → 204, зникає з GET /api/products
  7. delete frozen товару → 204 (дозволено)
  8. delete на free-плані → 204 (дозволено попри free)
  9. public каталог повертає галерею
  10. товар без фото → photos: []

R2-клієнт мокається (aioboto3.Session) — реальний R2 не зачіпається.
"""
from __future__ import annotations

import io
from decimal import Decimal

import aioboto3
import pytest
from httpx import AsyncClient
from PIL import Image
from sqlalchemy import select

from app import db
from app.config import settings
from app.models import Plan, Product, ProductPhoto, Shop, Subscription, SubStatus, Variant
from tests.conftest import make_init_data

HEADER = "X-Telegram-Init-Data"


# --------------------------------------------------------------------------- #
#  Helpers
# --------------------------------------------------------------------------- #

async def _bootstrap(client: AsyncClient, tg_id: int, name: str = "Тест") -> tuple[str, int]:
    init_data = make_init_data(tg_id, first_name=name)
    r = await client.get("/api/me", headers={HEADER: init_data})
    assert r.status_code == 200
    return init_data, r.json()["shop_id"]


async def _add_product(shop_id: int) -> int:
    async with db.async_session() as session:
        product = Product(shop_id=shop_id, name="Товар")
        session.add(product)
        await session.flush()
        session.add(Variant(shop_id=shop_id, product_id=product.id, price=Decimal("100")))
        await session.commit()
        return product.id


async def _add_photo(product_id: int, url: str = "https://cdn.example.test/test.webp", position: int = 0) -> int:
    async with db.async_session() as session:
        photo = ProductPhoto(product_id=product_id, url=url, position=position)
        session.add(photo)
        await session.commit()
        return photo.id


async def _set_free_plan(shop_id: int) -> None:
    async with db.async_session() as session:
        free_plan = await session.scalar(select(Plan).where(Plan.code == "free"))
        assert free_plan is not None, "seed free plan required"
        sub = await session.scalar(select(Subscription).where(Subscription.shop_id == shop_id))
        assert sub is not None
        sub.status = SubStatus.active
        sub.plan_id = free_plan.id
        await session.commit()


def _make_image_bytes(size: tuple[int, int] = (200, 200)) -> bytes:
    image = Image.new("RGB", size, color=(200, 30, 30))
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
#  Тест 1: upload ok → 201, position інкрементується
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_upload_photo_ok_position_increments(client: AsyncClient) -> None:
    init_data, shop_id = await _bootstrap(client, tg_id=4001)
    product_id = await _add_product(shop_id)

    r1 = await client.post(
        f"/api/products/{product_id}/photos",
        files={"file": ("a.jpg", _make_image_bytes(), "image/jpeg")},
        headers={HEADER: init_data},
    )
    assert r1.status_code == 201, r1.text
    body1 = r1.json()
    assert body1["position"] == 0
    assert body1["url"].startswith("https://cdn.example.test/")
    assert body1["id"] > 0

    r2 = await client.post(
        f"/api/products/{product_id}/photos",
        files={"file": ("b.jpg", _make_image_bytes(), "image/jpeg")},
        headers={HEADER: init_data},
    )
    assert r2.status_code == 201, r2.text
    assert r2.json()["position"] == 1

    # Обидва PUT calls у R2
    put_calls = [c for c in _FakeS3Client.calls if c["op"] == "put"]
    assert len(put_calls) == 2


# --------------------------------------------------------------------------- #
#  Тест 2: upload free-план → 402
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_upload_photo_free_plan_blocked(client: AsyncClient) -> None:
    init_data, shop_id = await _bootstrap(client, tg_id=4002)
    product_id = await _add_product(shop_id)
    await _set_free_plan(shop_id)

    r = await client.post(
        f"/api/products/{product_id}/photos",
        files={"file": ("a.jpg", _make_image_bytes(), "image/jpeg")},
        headers={HEADER: init_data},
    )
    assert r.status_code == 402
    assert _FakeS3Client.calls == []


# --------------------------------------------------------------------------- #
#  Тест 3: upload 11-го → 409
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_upload_eleventh_photo_returns_409(client: AsyncClient) -> None:
    init_data, shop_id = await _bootstrap(client, tg_id=4003)
    product_id = await _add_product(shop_id)

    # Засіяти 10 фото напряму в БД
    for i in range(10):
        await _add_photo(product_id, url=f"https://cdn.example.test/p{i}.webp", position=i)

    r = await client.post(
        f"/api/products/{product_id}/photos",
        files={"file": ("x.jpg", _make_image_bytes(), "image/jpeg")},
        headers={HEADER: init_data},
    )
    assert r.status_code == 409
    assert "10" in r.json()["detail"]
    assert _FakeS3Client.calls == []


# --------------------------------------------------------------------------- #
#  Тест 4: upload на frozen товар → 402
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_upload_photo_frozen_product_blocked(client: AsyncClient) -> None:
    init_data, shop_id = await _bootstrap(client, tg_id=4004)

    # Поставити ліміт max_products=1, додати 2 товари → перший стає frozen
    async with db.async_session() as session:
        free_plan = await session.scalar(select(Plan).where(Plan.code == "free"))
        assert free_plan is not None
        # Не змінюємо план (потрібні photos=True для перевірки frozen, не free block)
        # Натомість вручну переводимо в стан з max_products=1 через custom plan
        sub = await session.scalar(select(Subscription).where(Subscription.shop_id == shop_id))
        assert sub is not None
        # Ставимо active план з photos=True але max_products=1
        from app.models import Plan as PlanModel
        custom = PlanModel(
            code=f"frozen_test_{shop_id}",
            name="Test",
            limits={"max_products": 1, "photos": True},
        )
        session.add(custom)
        await session.flush()
        sub.status = SubStatus.active
        sub.plan_id = custom.id
        await session.commit()

    # Додаємо 2 товари — другий (старіший за created_at) стає frozen
    product_id1 = await _add_product(shop_id)
    product_id2 = await _add_product(shop_id)

    # product_id1 — більший id (пізніший) — в топ-1; product_id2 — frozen
    # frozen_product_ids вибирає топ-N по (created_at DESC, id DESC)
    # тому product_id1 (більший id, пізніший) → in top → NOT frozen
    # product_id2 (менший id, раніший) → frozen
    # Але у _add_product вони йдуть послідовно → product_id1 < product_id2
    # product_id2 — більший id → top 1 → NOT frozen
    # product_id1 — менший id → frozen
    frozen_product_id = product_id1

    r = await client.post(
        f"/api/products/{frozen_product_id}/photos",
        files={"file": ("a.jpg", _make_image_bytes(), "image/jpeg")},
        headers={HEADER: init_data},
    )
    assert r.status_code == 402, r.text
    assert _FakeS3Client.calls == []


# --------------------------------------------------------------------------- #
#  Тест 5: cross-shop upload → 404
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_upload_photo_cross_shop_returns_404(client: AsyncClient) -> None:
    init_a, shop_a = await _bootstrap(client, tg_id=4005, name="Shop A")
    init_b, _shop_b = await _bootstrap(client, tg_id=4006, name="Shop B")

    product_a = await _add_product(shop_a)

    r = await client.post(
        f"/api/products/{product_a}/photos",
        files={"file": ("a.jpg", _make_image_bytes(), "image/jpeg")},
        headers={HEADER: init_b},
    )
    assert r.status_code == 404
    assert _FakeS3Client.calls == []


# --------------------------------------------------------------------------- #
#  Тест 6: delete ok → 204, зникає з GET /api/products
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_delete_photo_removes_from_product(client: AsyncClient) -> None:
    init_data, shop_id = await _bootstrap(client, tg_id=4007)
    product_id = await _add_product(shop_id)

    # Завантажити фото через API
    r_upload = await client.post(
        f"/api/products/{product_id}/photos",
        files={"file": ("a.jpg", _make_image_bytes(), "image/jpeg")},
        headers={HEADER: init_data},
    )
    assert r_upload.status_code == 201
    photo_id = r_upload.json()["id"]

    # Видалити
    r_del = await client.delete(
        f"/api/products/{product_id}/photos/{photo_id}",
        headers={HEADER: init_data},
    )
    assert r_del.status_code == 204

    # Перевірити що delete_object викликаний у R2
    delete_calls = [c for c in _FakeS3Client.calls if c["op"] == "delete"]
    assert len(delete_calls) == 1

    # GET /api/products → photos порожній
    r_list = await client.get("/api/products", headers={HEADER: init_data})
    assert r_list.status_code == 200
    product_data = next(p for p in r_list.json() if p["id"] == product_id)
    assert product_data["photos"] == []


# --------------------------------------------------------------------------- #
#  Тест 7: delete photo frozen товару → 204 (дозволено)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_delete_photo_frozen_product_allowed(client: AsyncClient) -> None:
    init_data, shop_id = await _bootstrap(client, tg_id=4008)

    # Налаштувати план з max_products=1 + photos=True
    async with db.async_session() as session:
        from app.models import Plan as PlanModel
        custom = PlanModel(
            code=f"frozen_del_{shop_id}",
            name="Test",
            limits={"max_products": 1, "photos": True},
        )
        session.add(custom)
        await session.flush()
        sub = await session.scalar(select(Subscription).where(Subscription.shop_id == shop_id))
        assert sub is not None
        sub.status = SubStatus.active
        sub.plan_id = custom.id
        await session.commit()

    product_id1 = await _add_product(shop_id)
    product_id2 = await _add_product(shop_id)
    # product_id1 → frozen (менший id → раніший → не в топ-1)
    frozen_product_id = product_id1

    # Засіяти фото напряму (upload через API заблокований для frozen)
    photo_id = await _add_photo(frozen_product_id)

    r = await client.delete(
        f"/api/products/{frozen_product_id}/photos/{photo_id}",
        headers={HEADER: init_data},
    )
    assert r.status_code == 204, r.text


# --------------------------------------------------------------------------- #
#  Тест 8: delete на FREE-плані → 204 (дозволено попри free)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_delete_photo_free_plan_allowed(client: AsyncClient) -> None:
    init_data, shop_id = await _bootstrap(client, tg_id=4009)
    product_id = await _add_product(shop_id)

    # Засіяти фото напряму в БД (уникаємо API, який блокує на free)
    photo_id = await _add_photo(product_id)

    # Понизити до free
    await _set_free_plan(shop_id)

    r = await client.delete(
        f"/api/products/{product_id}/photos/{photo_id}",
        headers={HEADER: init_data},
    )
    assert r.status_code == 204, r.text


# --------------------------------------------------------------------------- #
#  Тест 9: public каталог повертає галерею (платний план)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_public_catalog_returns_photos(client: AsyncClient) -> None:
    init_data, shop_id = await _bootstrap(client, tg_id=4010)
    product_id = await _add_product(shop_id)

    # Засіяти фото напряму
    await _add_photo(product_id, url="https://cdn.example.test/photo0.webp", position=0)
    await _add_photo(product_id, url="https://cdn.example.test/photo1.webp", position=1)

    # Увімкнути публічний каталог
    async with db.async_session() as session:
        shop = await session.get(Shop, shop_id)
        assert shop is not None
        shop.public_catalog_enabled = True
        await session.commit()

    r = await client.get(f"/api/public/{(await _get_shop_slug(shop_id))}")
    assert r.status_code == 200, r.text
    products = r.json()["products"]
    # Filter to the product we added (demo catalog may also appear)
    target = next((p for p in products if p["name"] == "Товар"), None)
    assert target is not None
    photos = target["photos"]
    assert len(photos) == 2
    assert photos[0]["position"] == 0
    assert photos[1]["position"] == 1


# --------------------------------------------------------------------------- #
#  Тест 10: товар без фото → photos: []
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_product_without_photos_returns_empty_list(client: AsyncClient) -> None:
    init_data, shop_id = await _bootstrap(client, tg_id=4011)
    product_id = await _add_product(shop_id)

    r = await client.get("/api/products", headers={HEADER: init_data})
    assert r.status_code == 200
    product_data = next(p for p in r.json() if p["id"] == product_id)
    assert product_data["photos"] == []


# --------------------------------------------------------------------------- #
#  Internal helper
# --------------------------------------------------------------------------- #
async def _get_shop_slug(shop_id: int) -> str:
    async with db.async_session() as session:
        shop = await session.get(Shop, shop_id)
        assert shop is not None
        return shop.slug
