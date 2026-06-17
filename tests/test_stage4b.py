"""
Stage 4b acceptance tests (public catalog, outbound stock webhook).

Criteria (ROADMAP.md, Стадія 4b):
  1. GET /api/public/{slug} для public_catalog_enabled=True -> 200, у відповіді
     є in_stock, НЕМА on_hand/reserved/SKU
  2. для public_catalog_enabled=False або неіснуючого slug -> 404
  3. створення website-замовлення з заданим webhook_url -> dispatch
     викликаний, тіло підписане валідним HMAC (httpx замокано)
  4. вебхук кидає виняток/таймаут -> замовлення все одно успішне (best-effort)
  5. ізоляція: публічний каталог магазину A не показує товари B
"""
from __future__ import annotations

import hashlib
import hmac
import json
from decimal import Decimal
from uuid import uuid4

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app import db
from app.models import Product, Shop, Variant
from app.services.shop import generate_api_key, set_webhook
from tests.conftest import make_init_data

HEADER = "X-Telegram-Init-Data"
API_KEY_HEADER = "X-API-Key"


async def _bootstrap_shop_with_api_key(
    client: AsyncClient, tg_id: int, name: str = "Тест"
) -> tuple[str, int, str]:
    init_data = make_init_data(tg_id, first_name=name)
    r = await client.get("/api/me", headers={HEADER: init_data})
    assert r.status_code == 200
    shop_id = r.json()["shop_id"]

    async with db.async_session() as session:
        shop = await session.get(Shop, shop_id)
        assert shop is not None
        plaintext_key = await generate_api_key(session, shop)

    return init_data, shop_id, plaintext_key


async def _add_variant(shop_id: int, on_hand: int, price: str = "100") -> int:
    async with db.async_session() as session:
        product = Product(shop_id=shop_id, name="Товар")
        session.add(product)
        await session.flush()

        variant = Variant(
            shop_id=shop_id,
            product_id=product.id,
            sku=f"SKU-{uuid4().hex[:8]}",
            price=Decimal(price),
            on_hand=on_hand,
        )
        session.add(variant)
        await session.commit()
        return variant.id


async def _enable_public_catalog(shop_id: int) -> str:
    async with db.async_session() as session:
        shop = await session.get(Shop, shop_id)
        assert shop is not None
        shop.public_catalog_enabled = True
        slug = shop.slug
        await session.commit()
        return slug


async def _set_shop_webhook(session: AsyncSession, shop_id: int, url: str) -> str:
    shop = await session.get(Shop, shop_id)
    assert shop is not None
    return await set_webhook(session, shop, url)


class _FakeResponse:
    status_code = 200


class _RecordingAsyncClient:
    """Записує POST-запити замість реального HTTP — підмінюється через
    `monkeypatch.setattr(httpx, "AsyncClient", ...)`."""

    calls: list[dict] = []

    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self) -> "_RecordingAsyncClient":
        return self

    async def __aexit__(self, *exc_info) -> bool:
        return False

    async def post(self, url, *, content, headers) -> _FakeResponse:
        _RecordingAsyncClient.calls.append({"url": url, "content": content, "headers": headers})
        return _FakeResponse()


class _FailingAsyncClient:
    """Симулює недосяжний сайт власника (таймаут/мережева помилка)."""

    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self) -> "_FailingAsyncClient":
        return self

    async def __aexit__(self, *exc_info) -> bool:
        return False

    async def post(self, url, *, content, headers):
        raise httpx.ConnectTimeout("simulated timeout")


@pytest.mark.asyncio
async def test_public_catalog_exposes_in_stock_without_internal_fields(
    client: AsyncClient,
) -> None:
    _init_data, shop_id, _api_key = await _bootstrap_shop_with_api_key(client, 4001)
    await _add_variant(shop_id, on_hand=5)
    await _add_variant(shop_id, on_hand=0)
    slug = await _enable_public_catalog(shop_id)

    r = await client.get(f"/api/public/{slug}")
    assert r.status_code == 200
    body = r.json()

    assert body["name"]
    assert "accent_color" in body

    all_variants = [v for p in body["products"] for v in p["variants"]]
    assert any(v["in_stock"] is True for v in all_variants)
    assert any(v["in_stock"] is False for v in all_variants)

    body_text = r.text
    for forbidden in ("on_hand", "reserved", "sku", "low_stock_threshold"):
        assert forbidden not in body_text


@pytest.mark.asyncio
async def test_public_catalog_404_when_disabled_or_missing(client: AsyncClient) -> None:
    _init_data, shop_id, _api_key = await _bootstrap_shop_with_api_key(client, 4002)
    async with db.async_session() as session:
        shop = await session.get(Shop, shop_id)
        assert shop is not None
        slug = shop.slug
        # public_catalog_enabled лишається False (дефолт) — нічого не змінюємо

    r_disabled = await client.get(f"/api/public/{slug}")
    assert r_disabled.status_code == 404

    r_missing = await client.get("/api/public/no-such-shop-slug")
    assert r_missing.status_code == 404


@pytest.mark.asyncio
async def test_public_catalog_isolation_between_shops(client: AsyncClient) -> None:
    _init_a, shop_a, _api_key_a = await _bootstrap_shop_with_api_key(client, 4003, "Шоп А")
    _init_b, shop_b, _api_key_b = await _bootstrap_shop_with_api_key(client, 4004, "Шоп Б")

    await _add_variant(shop_a, on_hand=3, price="111.11")
    await _add_variant(shop_b, on_hand=3, price="999.99")
    slug_a = await _enable_public_catalog(shop_a)

    r = await client.get(f"/api/public/{slug_a}")
    assert r.status_code == 200
    body = r.json()

    all_prices = {Decimal(str(v["price"])) for p in body["products"] for v in p["variants"]}
    assert Decimal("111.11") in all_prices
    assert Decimal("999.99") not in all_prices


@pytest.mark.asyncio
async def test_create_order_dispatches_signed_webhook(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _RecordingAsyncClient.calls.clear()
    monkeypatch.setattr(httpx, "AsyncClient", _RecordingAsyncClient)

    _init_data, shop_id, api_key = await _bootstrap_shop_with_api_key(client, 4005)
    variant_id = await _add_variant(shop_id, on_hand=10)

    async with db.async_session() as session:
        webhook_secret = await _set_shop_webhook(
            session, shop_id, "https://example.test/hooks/stock"
        )

    payload = {"items": [{"variant_id": variant_id, "qty": 2}], "idempotency_key": "wh-1"}
    r = await client.post(
        "/api/website/orders", json=payload, headers={API_KEY_HEADER: api_key}
    )
    assert r.status_code == 201, r.text

    assert len(_RecordingAsyncClient.calls) == 1
    call = _RecordingAsyncClient.calls[0]
    assert call["url"] == "https://example.test/hooks/stock"

    body_bytes = call["content"]
    expected_signature = hmac.new(
        webhook_secret.encode(), body_bytes, hashlib.sha256
    ).hexdigest()
    assert call["headers"]["X-Signature"] == expected_signature

    sent_payload = json.loads(body_bytes)
    sent_variant_ids = {v["variant_id"] for v in sent_payload["variants"]}
    assert sent_variant_ids == {variant_id}


@pytest.mark.asyncio
async def test_webhook_failure_does_not_break_order_creation(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(httpx, "AsyncClient", _FailingAsyncClient)

    _init_data, shop_id, api_key = await _bootstrap_shop_with_api_key(client, 4006)
    variant_id = await _add_variant(shop_id, on_hand=5)

    async with db.async_session() as session:
        await _set_shop_webhook(session, shop_id, "https://example.test/hooks/stock")

    payload = {"items": [{"variant_id": variant_id, "qty": 1}], "idempotency_key": "wh-2"}
    r = await client.post(
        "/api/website/orders", json=payload, headers={API_KEY_HEADER: api_key}
    )
    assert r.status_code == 201, r.text
