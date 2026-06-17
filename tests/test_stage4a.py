"""
Stage 4a acceptance tests (orders core).

Criteria (ROADMAP.md, Стадія 4a):
  1. подвійний POST з тим самим idempotency_key -> рівно один Order
     (другий повертає той самий)
  2. створення замовлення резервує склад: available падає, on_hand НЕ
     змінюється, Reservation привʼязані до order_id
  3. недостатньо складу на будь-якому item -> 409, жодного часткового
     резерву, стан складу не змінився
  4. відсутній/невалідний X-API-Key -> 401
  5. confirm -> резерви fulfilled, on_hand падає, order=fulfilled
  6. cancel -> резерви released, available повертається, order=canceled
  7. crypto: decrypt(encrypt(x)) == x; різні nonce дають різний шифротекст
  8. ізоляція: магазин A не бачить/не чіпає замовлення магазину B
"""
from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app import db
from app.models import Order, Product, Reservation, ReservationStatus, Shop, Variant
from app.security.crypto import decrypt, encrypt
from app.services.shop import generate_api_key
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


@pytest.mark.asyncio
async def test_duplicate_idempotency_key_returns_same_order(client: AsyncClient) -> None:
    _init_data, shop_id, api_key = await _bootstrap_shop_with_api_key(client, 2001)
    variant_id = await _add_variant(shop_id, on_hand=10)

    payload = {
        "items": [{"variant_id": variant_id, "qty": 2}],
        "idempotency_key": "idem-1",
        "customer_name": "Клієнт",
    }

    r1 = await client.post(
        "/api/website/orders", json=payload, headers={API_KEY_HEADER: api_key}
    )
    assert r1.status_code == 201, r1.text
    order_id_1 = r1.json()["id"]

    r2 = await client.post(
        "/api/website/orders", json=payload, headers={API_KEY_HEADER: api_key}
    )
    assert r2.status_code == 200
    assert r2.json()["id"] == order_id_1

    async with db.async_session() as session:
        count = await session.scalar(select(func.count(Order.id)).where(Order.shop_id == shop_id))
    assert count == 1


@pytest.mark.asyncio
async def test_create_order_reserves_stock_without_touching_on_hand(client: AsyncClient) -> None:
    _init_data, shop_id, api_key = await _bootstrap_shop_with_api_key(client, 2002)
    variant_id = await _add_variant(shop_id, on_hand=10)

    payload = {"items": [{"variant_id": variant_id, "qty": 3}], "idempotency_key": "idem-2"}
    r = await client.post("/api/website/orders", json=payload, headers={API_KEY_HEADER: api_key})
    assert r.status_code == 201, r.text
    order_id = r.json()["id"]

    async with db.async_session() as session:
        variant = await session.get(Variant, variant_id)
        assert variant is not None
        assert variant.on_hand == 10
        assert variant.reserved == 3
        assert variant.available == 7

        reservations = (
            await session.scalars(select(Reservation).where(Reservation.order_id == order_id))
        ).all()
    assert len(reservations) == 1
    assert reservations[0].qty == 3
    assert reservations[0].status == ReservationStatus.active


@pytest.mark.asyncio
async def test_insufficient_stock_on_any_item_rolls_back_whole_order(
    client: AsyncClient,
) -> None:
    _init_data, shop_id, api_key = await _bootstrap_shop_with_api_key(client, 2003)
    variant_ok_id = await _add_variant(shop_id, on_hand=10)
    variant_short_id = await _add_variant(shop_id, on_hand=1)

    payload = {
        "items": [
            {"variant_id": variant_ok_id, "qty": 2},
            {"variant_id": variant_short_id, "qty": 5},
        ],
        "idempotency_key": "idem-3",
    }
    r = await client.post("/api/website/orders", json=payload, headers={API_KEY_HEADER: api_key})
    assert r.status_code == 409

    async with db.async_session() as session:
        variant_ok = await session.get(Variant, variant_ok_id)
        variant_short = await session.get(Variant, variant_short_id)
        assert variant_ok is not None
        assert variant_short is not None
        assert variant_ok.reserved == 0
        assert variant_short.reserved == 0

        orders_count = await session.scalar(
            select(func.count(Order.id)).where(Order.shop_id == shop_id)
        )
        reservations_count = await session.scalar(select(func.count(Reservation.id)))
    assert orders_count == 0
    assert reservations_count == 0


@pytest.mark.asyncio
async def test_missing_or_invalid_api_key_returns_401(client: AsyncClient) -> None:
    _init_data, shop_id, _api_key = await _bootstrap_shop_with_api_key(client, 2004)
    variant_id = await _add_variant(shop_id, on_hand=5)
    payload = {"items": [{"variant_id": variant_id, "qty": 1}], "idempotency_key": "idem-4"}

    r_missing = await client.post("/api/website/orders", json=payload)
    assert r_missing.status_code == 401

    r_invalid = await client.post(
        "/api/website/orders", json=payload, headers={API_KEY_HEADER: "totally-wrong-key"}
    )
    assert r_invalid.status_code == 401


@pytest.mark.asyncio
async def test_confirm_fulfills_active_reservations(client: AsyncClient) -> None:
    init_data, shop_id, api_key = await _bootstrap_shop_with_api_key(client, 2005)
    variant_id = await _add_variant(shop_id, on_hand=10)

    payload = {"items": [{"variant_id": variant_id, "qty": 4}], "idempotency_key": "idem-5"}
    r_create = await client.post(
        "/api/website/orders", json=payload, headers={API_KEY_HEADER: api_key}
    )
    order_id = r_create.json()["id"]

    r_confirm = await client.post(f"/api/orders/{order_id}/confirm", headers={HEADER: init_data})
    assert r_confirm.status_code == 200, r_confirm.text
    assert r_confirm.json()["status"] == "fulfilled"

    async with db.async_session() as session:
        variant = await session.get(Variant, variant_id)
        assert variant is not None
        assert variant.on_hand == 6
        assert variant.reserved == 0

        reservation = await session.scalar(
            select(Reservation).where(Reservation.order_id == order_id)
        )
        assert reservation is not None
        assert reservation.status == ReservationStatus.fulfilled


@pytest.mark.asyncio
async def test_cancel_releases_active_reservations(client: AsyncClient) -> None:
    init_data, shop_id, api_key = await _bootstrap_shop_with_api_key(client, 2006)
    variant_id = await _add_variant(shop_id, on_hand=10)

    payload = {"items": [{"variant_id": variant_id, "qty": 4}], "idempotency_key": "idem-6"}
    r_create = await client.post(
        "/api/website/orders", json=payload, headers={API_KEY_HEADER: api_key}
    )
    order_id = r_create.json()["id"]

    r_cancel = await client.post(f"/api/orders/{order_id}/cancel", headers={HEADER: init_data})
    assert r_cancel.status_code == 200, r_cancel.text
    assert r_cancel.json()["status"] == "canceled"

    async with db.async_session() as session:
        variant = await session.get(Variant, variant_id)
        assert variant is not None
        assert variant.on_hand == 10
        assert variant.reserved == 0
        assert variant.available == 10

        reservation = await session.scalar(
            select(Reservation).where(Reservation.order_id == order_id)
        )
        assert reservation is not None
        assert reservation.status == ReservationStatus.released


@pytest.mark.asyncio
async def test_crypto_roundtrip_and_nonce_uniqueness() -> None:
    plaintext = "secret-api-key-value"
    token_a = encrypt(plaintext)
    token_b = encrypt(plaintext)

    assert decrypt(token_a) == plaintext
    assert decrypt(token_b) == plaintext
    assert token_a != token_b  # випадковий nonce -> різний шифротекст на той самий plaintext


@pytest.mark.asyncio
async def test_cross_shop_order_isolation(client: AsyncClient) -> None:
    init_data_a, shop_a, api_key_a = await _bootstrap_shop_with_api_key(client, 2007, "Шоп А")
    init_data_b, _shop_b, _api_key_b = await _bootstrap_shop_with_api_key(client, 2008, "Шоп Б")

    variant_a = await _add_variant(shop_a, on_hand=5)
    payload = {"items": [{"variant_id": variant_a, "qty": 1}], "idempotency_key": "idem-8"}
    r_create = await client.post(
        "/api/website/orders", json=payload, headers={API_KEY_HEADER: api_key_a}
    )
    assert r_create.status_code == 201
    order_id = r_create.json()["id"]

    r_list_b = await client.get("/api/orders", headers={HEADER: init_data_b})
    assert r_list_b.status_code == 200
    assert all(o["id"] != order_id for o in r_list_b.json())

    r_confirm_b = await client.post(
        f"/api/orders/{order_id}/confirm", headers={HEADER: init_data_b}
    )
    assert r_confirm_b.status_code == 404

    r_cancel_b = await client.post(
        f"/api/orders/{order_id}/cancel", headers={HEADER: init_data_b}
    )
    assert r_cancel_b.status_code == 404

    # власник магазину А все ж бачить своє замовлення
    r_list_a = await client.get("/api/orders", headers={HEADER: init_data_a})
    assert any(o["id"] == order_id for o in r_list_a.json())


@pytest.mark.asyncio
async def test_notifier_called_once_per_new_order_not_on_replay(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[int, str]] = []

    async def _fake_notifier(tg_id: int, text: str) -> None:
        calls.append((tg_id, text))

    monkeypatch.setattr("app.api.orders.notifier", _fake_notifier)

    _init_data, shop_id, api_key = await _bootstrap_shop_with_api_key(client, 2009)
    variant_id = await _add_variant(shop_id, on_hand=5)
    payload = {"items": [{"variant_id": variant_id, "qty": 1}], "idempotency_key": "idem-9"}

    r1 = await client.post("/api/website/orders", json=payload, headers={API_KEY_HEADER: api_key})
    assert r1.status_code == 201
    assert len(calls) == 1

    r2 = await client.post("/api/website/orders", json=payload, headers={API_KEY_HEADER: api_key})
    assert r2.status_code == 200
    assert len(calls) == 1  # ідемпотентний повтор не нотифікує знову
