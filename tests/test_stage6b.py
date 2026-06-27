"""
Stage 6b acceptance tests (inventory REST API: restock, adjust, reserve,
release, fulfill).

Criteria (ROADMAP.md, Стадія 6b):
  1. restock збільшує on_hand, повертає оновлений варіант
  2. adjust ставить on_hand, нижче reserved -> відмова
  3. reserve зменшує available (не on_hand), створює Reservation;
     >available -> відмова
  4. release повертає reserved в available; fulfill -> продаж (on_hand падає)
  5. ізоляція: чужий варіант/резерв -> 404
  6. expired-підписка -> 402 на мутаціях, GET /api/reservations досі 200
"""
from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app import db
from app.models import (
    Product,
    Reservation,
    ReservationSource,
    ReservationStatus,
    Subscription,
    SubStatus,
    Variant,
)
from tests.conftest import make_init_data

HEADER = "X-Telegram-Init-Data"


async def _bootstrap(client: AsyncClient, tg_id: int, name: str = "Тест") -> tuple[str, int]:
    init_data = make_init_data(tg_id, first_name=name)
    r = await client.get("/api/me", headers={HEADER: init_data})
    assert r.status_code == 200
    return init_data, r.json()["shop_id"]


async def _add_variant(shop_id: int, on_hand: int = 10) -> int:
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


async def _expire_subscription(shop_id: int) -> None:
    async with db.async_session() as session:
        sub = await session.scalar(select(Subscription).where(Subscription.shop_id == shop_id))
        assert sub is not None
        sub.status = SubStatus.expired
        await session.commit()


@pytest.mark.asyncio
async def test_restock_increases_on_hand_and_returns_variant(client: AsyncClient) -> None:
    init_data, shop_id = await _bootstrap(client, 9001)
    variant_id = await _add_variant(shop_id, on_hand=5)

    r = await client.post(
        f"/api/variants/{variant_id}/restock", json={"qty": 7}, headers={HEADER: init_data}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["on_hand"] == 12
    assert body["available"] == 12


@pytest.mark.asyncio
async def test_adjust_below_reserved_is_rejected(client: AsyncClient) -> None:
    init_data, shop_id = await _bootstrap(client, 9002)
    variant_id = await _add_variant(shop_id, on_hand=10)

    r_reserve = await client.post(
        f"/api/variants/{variant_id}/reserve", json={"qty": 4}, headers={HEADER: init_data}
    )
    assert r_reserve.status_code == 200, r_reserve.text

    r_adjust = await client.post(
        f"/api/variants/{variant_id}/adjust",
        json={"new_on_hand": 2, "reason": "інвентаризація"},
        headers={HEADER: init_data},
    )
    assert r_adjust.status_code == 409

    async with db.async_session() as session:
        variant = await session.get(Variant, variant_id)
    assert variant is not None
    assert variant.on_hand == 10  # незмінено


@pytest.mark.asyncio
async def test_adjust_sets_on_hand_when_above_reserved(client: AsyncClient) -> None:
    init_data, shop_id = await _bootstrap(client, 9003)
    variant_id = await _add_variant(shop_id, on_hand=10)

    r = await client.post(
        f"/api/variants/{variant_id}/adjust",
        json={"new_on_hand": 6, "reason": "інвентаризація"},
        headers={HEADER: init_data},
    )
    assert r.status_code == 200, r.text
    assert r.json()["on_hand"] == 6


@pytest.mark.asyncio
async def test_reserve_decreases_available_not_on_hand_and_creates_reservation(
    client: AsyncClient,
) -> None:
    init_data, shop_id = await _bootstrap(client, 9004)
    variant_id = await _add_variant(shop_id, on_hand=10)

    r = await client.post(
        f"/api/variants/{variant_id}/reserve",
        json={"qty": 3, "customer_note": "тримати до п'ятниці"},
        headers={HEADER: init_data},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["qty"] == 3
    assert body["status"] == "active"
    assert body["customer_note"] == "тримати до п'ятниці"

    async with db.async_session() as session:
        variant = await session.get(Variant, variant_id)
    assert variant is not None
    assert variant.on_hand == 10
    assert variant.reserved == 3
    assert variant.available == 7

    r_list = await client.get("/api/reservations", headers={HEADER: init_data})
    assert r_list.status_code == 200
    assert any(res["id"] == body["id"] for res in r_list.json())


@pytest.mark.asyncio
async def test_reserve_more_than_available_is_rejected(client: AsyncClient) -> None:
    init_data, shop_id = await _bootstrap(client, 9005)
    variant_id = await _add_variant(shop_id, on_hand=3)

    r = await client.post(
        f"/api/variants/{variant_id}/reserve", json={"qty": 10}, headers={HEADER: init_data}
    )
    assert r.status_code == 409

    async with db.async_session() as session:
        variant = await session.get(Variant, variant_id)
    assert variant is not None
    assert variant.reserved == 0


@pytest.mark.asyncio
async def test_release_returns_reserved_to_available(client: AsyncClient) -> None:
    init_data, shop_id = await _bootstrap(client, 9006)
    variant_id = await _add_variant(shop_id, on_hand=10)

    r_reserve = await client.post(
        f"/api/variants/{variant_id}/reserve", json={"qty": 4}, headers={HEADER: init_data}
    )
    reservation_id = r_reserve.json()["id"]

    r_release = await client.post(
        f"/api/reservations/{reservation_id}/release", headers={HEADER: init_data}
    )
    assert r_release.status_code == 200, r_release.text
    assert r_release.json()["status"] == "released"

    async with db.async_session() as session:
        variant = await session.get(Variant, variant_id)
    assert variant is not None
    assert variant.reserved == 0
    assert variant.available == 10


@pytest.mark.asyncio
async def test_fulfill_sells_reserved_unit_and_drops_on_hand(client: AsyncClient) -> None:
    init_data, shop_id = await _bootstrap(client, 9007)
    variant_id = await _add_variant(shop_id, on_hand=10)

    r_reserve = await client.post(
        f"/api/variants/{variant_id}/reserve", json={"qty": 4}, headers={HEADER: init_data}
    )
    reservation_id = r_reserve.json()["id"]

    r_fulfill = await client.post(
        f"/api/reservations/{reservation_id}/fulfill", headers={HEADER: init_data}
    )
    assert r_fulfill.status_code == 200, r_fulfill.text
    assert r_fulfill.json()["status"] == "fulfilled"

    async with db.async_session() as session:
        variant = await session.get(Variant, variant_id)
    assert variant is not None
    assert variant.on_hand == 6
    assert variant.reserved == 0


@pytest.mark.asyncio
async def test_cross_shop_variant_and_reservation_return_404(client: AsyncClient) -> None:
    _init_a, shop_a = await _bootstrap(client, 9008, "Шоп А")
    init_b, _shop_b = await _bootstrap(client, 9009, "Шоп Б")

    variant_a = await _add_variant(shop_a, on_hand=10)

    r_restock = await client.post(
        f"/api/variants/{variant_a}/restock", json={"qty": 1}, headers={HEADER: init_b}
    )
    assert r_restock.status_code == 404

    r_adjust = await client.post(
        f"/api/variants/{variant_a}/adjust", json={"new_on_hand": 1}, headers={HEADER: init_b}
    )
    assert r_adjust.status_code == 404

    r_reserve = await client.post(
        f"/api/variants/{variant_a}/reserve", json={"qty": 1}, headers={HEADER: init_b}
    )
    assert r_reserve.status_code == 404

    # створюємо легітимний резерв у шопі А, потім намагаємось чіпати його з Б
    async with db.async_session() as session:
        reservation = Reservation(
            shop_id=shop_a,
            variant_id=variant_a,
            qty=1,
            source=ReservationSource.manual,
            status=ReservationStatus.active,
        )
        session.add(reservation)
        await session.commit()
        reservation_id = reservation.id

    r_release = await client.post(
        f"/api/reservations/{reservation_id}/release", headers={HEADER: init_b}
    )
    assert r_release.status_code == 404

    r_fulfill = await client.post(
        f"/api/reservations/{reservation_id}/fulfill", headers={HEADER: init_b}
    )
    assert r_fulfill.status_code == 404


@pytest.mark.asyncio
async def test_expired_subscription_is_free_plan_mutations_allowed_within_limit(
    client: AsyncClient,
) -> None:
    """FREE_PLAN_SPEC §8: expired → free-план, writable.
    Магазин з ≤ 20 товарів → нічого не заморожено → мутації дозволені."""
    init_data, shop_id = await _bootstrap(client, 9010)
    variant_id = await _add_variant(shop_id, on_hand=10)
    await _expire_subscription(shop_id)

    r_restock = await client.post(
        f"/api/variants/{variant_id}/restock", json={"qty": 1}, headers={HEADER: init_data}
    )
    assert r_restock.status_code == 200  # expired = free, не заморожений (≤ 20 товарів)

    r_adjust = await client.post(
        f"/api/variants/{variant_id}/adjust", json={"new_on_hand": 1}, headers={HEADER: init_data}
    )
    assert r_adjust.status_code == 200

    r_reserve = await client.post(
        f"/api/variants/{variant_id}/reserve", json={"qty": 1}, headers={HEADER: init_data}
    )
    assert r_reserve.status_code == 200

    r_list = await client.get("/api/reservations", headers={HEADER: init_data})
    assert r_list.status_code == 200
