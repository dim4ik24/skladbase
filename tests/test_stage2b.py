"""
Stage 2b acceptance tests (product photos: R2 upload, compression, plan gating).

Criteria (ROADMAP.md, Стадія 2b):
  1. валідне зображення -> стиснуте, завантажене (мок S3 put викликаний),
     photo_url проставлено
  2. зображення > ліміту -> відхилено на вході (413), Pillow/S3 НЕ викликані
  3. невірний тип -> відхилено (400)
  4. free-план (photos=False) -> 402, фото не вантажиться
  5. ізоляція: фото на варіант чужого магазину -> 404

R2/S3-клієнт мокається (aioboto3.Session) — реальний R2 не зачіпається.
Pillow працює по-справжньому: компресія перевіряється на отриманих байтах.
"""
from __future__ import annotations

import io
from decimal import Decimal
from uuid import uuid4

import aioboto3
import pytest
from httpx import AsyncClient
from PIL import Image
from sqlalchemy import select

from app import db
from app.config import settings
from app.models import Plan, Product, Subscription, SubStatus, Variant
from tests.conftest import make_init_data

HEADER = "X-Telegram-Init-Data"


async def _bootstrap(client: AsyncClient, tg_id: int, name: str = "Тест") -> tuple[str, int]:
    init_data = make_init_data(tg_id, first_name=name)
    r = await client.get("/api/me", headers={HEADER: init_data})
    assert r.status_code == 200
    return init_data, r.json()["shop_id"]


async def _add_variant(shop_id: int, on_hand: int = 5) -> int:
    async with db.async_session() as session:
        product = Product(shop_id=shop_id, name="Товар")
        session.add(product)
        await session.flush()
        variant = Variant(
            shop_id=shop_id,
            product_id=product.id,
            sku=f"SKU-{uuid4().hex[:8]}",
            price=Decimal("100"),
            on_hand=on_hand,
        )
        session.add(variant)
        await session.commit()
        return variant.id


def _make_image_bytes(fmt: str = "JPEG", size: tuple[int, int] = (2000, 1000)) -> bytes:
    image = Image.new("RGB", size, color=(200, 30, 30))
    buffer = io.BytesIO()
    image.save(buffer, format=fmt)
    return buffer.getvalue()


class _FakeS3Client:
    calls: list[dict] = []

    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self) -> "_FakeS3Client":
        return self

    async def __aexit__(self, *exc_info) -> bool:
        return False

    async def put_object(self, **kwargs) -> dict:
        _FakeS3Client.calls.append(kwargs)
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


@pytest.mark.asyncio
async def test_valid_photo_upload_compresses_and_uploads(client: AsyncClient) -> None:
    init_data, shop_id = await _bootstrap(client, 8001)
    variant_id = await _add_variant(shop_id)

    image_bytes = _make_image_bytes(size=(2000, 1000))
    r = await client.post(
        f"/api/variants/{variant_id}/photo",
        files={"file": ("photo.jpg", image_bytes, "image/jpeg")},
        headers={HEADER: init_data},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["photo_url"] is not None
    assert body["photo_url"].startswith(f"https://cdn.example.test/shops/{shop_id}/{variant_id}/")

    assert len(_FakeS3Client.calls) == 1
    call = _FakeS3Client.calls[0]
    assert call["ContentType"] == "image/webp"
    assert call["Key"].endswith(".webp")
    assert call["Key"].startswith(f"shops/{shop_id}/{variant_id}/")

    uploaded = Image.open(io.BytesIO(call["Body"]))
    assert uploaded.format == "WEBP"
    assert max(uploaded.size) <= 1024  # ресайз спрацював
    assert len(call["Body"]) < len(image_bytes)  # стиснення спрацювало

    async with db.async_session() as session:
        variant = await session.get(Variant, variant_id)
    assert variant is not None
    assert variant.photo_url == body["photo_url"]


@pytest.mark.asyncio
async def test_oversized_photo_rejected_before_processing(client: AsyncClient) -> None:
    init_data, shop_id = await _bootstrap(client, 8002)
    variant_id = await _add_variant(shop_id)

    oversized = b"x" * (6 * 1024 * 1024)  # > MAX_PHOTO_UPLOAD_MB (5), і навіть не картинка
    r = await client.post(
        f"/api/variants/{variant_id}/photo",
        files={"file": ("big.jpg", oversized, "image/jpeg")},
        headers={HEADER: init_data},
    )
    assert r.status_code == 413

    # 413, не 400 "невалідне зображення" -> перевірка розміру спрацювала ДО
    # спроби Pillow відкрити файл; і S3 не викликаний.
    assert _FakeS3Client.calls == []

    async with db.async_session() as session:
        variant = await session.get(Variant, variant_id)
    assert variant is not None
    assert variant.photo_url is None


@pytest.mark.asyncio
async def test_invalid_content_type_rejected(client: AsyncClient) -> None:
    init_data, shop_id = await _bootstrap(client, 8003)
    variant_id = await _add_variant(shop_id)

    r = await client.post(
        f"/api/variants/{variant_id}/photo",
        files={"file": ("doc.pdf", b"%PDF-1.4 not-an-image", "application/pdf")},
        headers={HEADER: init_data},
    )
    assert r.status_code == 400
    assert _FakeS3Client.calls == []


@pytest.mark.asyncio
async def test_free_plan_blocks_photo_upload(client: AsyncClient) -> None:
    init_data, shop_id = await _bootstrap(client, 8004)
    variant_id = await _add_variant(shop_id)

    async with db.async_session() as session:
        free_plan = await session.scalar(select(Plan).where(Plan.code == "free"))
        assert free_plan is not None
        sub = await session.scalar(select(Subscription).where(Subscription.shop_id == shop_id))
        assert sub is not None
        sub.status = SubStatus.active
        sub.plan_id = free_plan.id
        await session.commit()

    r = await client.post(
        f"/api/variants/{variant_id}/photo",
        files={"file": ("photo.jpg", _make_image_bytes(), "image/jpeg")},
        headers={HEADER: init_data},
    )
    assert r.status_code == 402
    assert _FakeS3Client.calls == []

    async with db.async_session() as session:
        variant = await session.get(Variant, variant_id)
    assert variant is not None
    assert variant.photo_url is None


@pytest.mark.asyncio
async def test_cross_shop_photo_upload_returns_404(client: AsyncClient) -> None:
    _init_a, shop_a = await _bootstrap(client, 8005, "Шоп А")
    init_b, _shop_b = await _bootstrap(client, 8006, "Шоп Б")

    variant_a = await _add_variant(shop_a)

    r = await client.post(
        f"/api/variants/{variant_a}/photo",
        files={"file": ("photo.jpg", _make_image_bytes(), "image/jpeg")},
        headers={HEADER: init_b},
    )
    assert r.status_code == 404
    assert _FakeS3Client.calls == []

    async with db.async_session() as session:
        variant = await session.get(Variant, variant_a)
    assert variant is not None
    assert variant.photo_url is None
