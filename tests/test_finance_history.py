"""
GET /api/finance/history?period=&date= — стрічка подій каси/складу.

Criteria:
  1. sale/return/release типи присутні з правильними полями
  2. customer/ttn підтягуються з резерву (reservation_id), коли рух ним
     породжений; прямий продаж (adjust reason=sold) — без customer/ttn
  3. date звужує до одного дня і переважає period
  4. period фільтрує без date
  5. сортування DESC за датою
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import AsyncClient

from app import db
from app.models import MovementType, Product, StockMovement, Variant, utcnow
from tests.conftest import make_init_data

HEADER = "X-Telegram-Init-Data"


async def _bootstrap(client: AsyncClient, tg_id: int, name: str = "Тест") -> tuple[str, int]:
    init_data = make_init_data(tg_id, first_name=name)
    r = await client.get("/api/me", headers={HEADER: init_data})
    assert r.status_code == 200
    return init_data, r.json()["shop_id"]


async def _add_variant(
    shop_id: int, name: str = "Товар", price: str = "100.00", axis_values: dict | None = None
) -> int:
    async with db.async_session() as session:
        product = Product(shop_id=shop_id, name=name)
        session.add(product)
        await session.flush()
        variant = Variant(
            shop_id=shop_id,
            product_id=product.id,
            sku=f"SKU-{uuid4().hex[:8]}",
            price=Decimal(price),
            on_hand=100,
            axis_values=axis_values or {},
        )
        session.add(variant)
        await session.commit()
        return variant.id


async def _reserve(client: AsyncClient, init_data: str, variant_id: int, **extra) -> int:
    r = await client.post(
        f"/api/variants/{variant_id}/reserve",
        json={"qty": 1, **extra},
        headers={HEADER: init_data},
    )
    assert r.status_code == 200, r.text
    return r.json()["id"]


async def _history(client: AsyncClient, init_data: str, **params) -> list[dict]:
    r = await client.get("/api/finance/history", params=params, headers={HEADER: init_data})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.asyncio
async def test_pick_up_event_carries_customer_and_ttn_from_reservation(
    client: AsyncClient,
) -> None:
    init_data, shop_id = await _bootstrap(client, 72001)
    variant_id = await _add_variant(shop_id, name="Сукня", price="450.00", axis_values={"size": "M"})
    reservation_id = await _reserve(
        client, init_data, variant_id, customer_note="Оксана, +380501112233"
    )

    r = await client.post(
        f"/api/reservations/{reservation_id}/ship",
        json={"ttn": "20450123456789"},
        headers={HEADER: init_data},
    )
    assert r.status_code == 200, r.text

    r2 = await client.post(
        f"/api/reservations/{reservation_id}/pick-up", headers={HEADER: init_data}
    )
    assert r2.status_code == 200, r2.text

    events = await _history(client, init_data, period="all")
    assert len(events) == 1
    event = events[0]
    assert event["type"] == "sale"
    assert event["product_name"] == "Сукня"
    assert event["variant_label"] == "M"
    assert event["qty"] == 1
    assert event["amount"] == "450.00"
    assert event["customer"] == "Оксана, +380501112233"
    assert event["ttn"] == "20450123456789"
    assert event["reason"] is None


@pytest.mark.asyncio
async def test_direct_write_off_sale_has_no_customer_or_ttn(client: AsyncClient) -> None:
    init_data, shop_id = await _bootstrap(client, 72002)
    variant_id = await _add_variant(shop_id, name="Кепка", price="300.00")

    r = await client.post(
        f"/api/variants/{variant_id}/adjust",
        json={"qty": 2, "reason": "sold"},
        headers={HEADER: init_data},
    )
    assert r.status_code == 200, r.text

    events = await _history(client, init_data, period="all")
    assert len(events) == 1
    event = events[0]
    assert event["type"] == "sale"
    assert event["amount"] == "600.00"
    assert event["customer"] is None
    assert event["ttn"] is None


@pytest.mark.asyncio
async def test_release_event_has_reason_and_customer_but_no_amount(client: AsyncClient) -> None:
    init_data, shop_id = await _bootstrap(client, 72003)
    variant_id = await _add_variant(shop_id, name="Штани", price="500.00")
    reservation_id = await _reserve(client, init_data, variant_id, customer_note="Іван")

    r = await client.post(
        f"/api/reservations/{reservation_id}/release",
        json={"reason": "customer_changed_mind"},
        headers={HEADER: init_data},
    )
    assert r.status_code == 200, r.text

    events = await _history(client, init_data, period="all")
    assert len(events) == 1
    event = events[0]
    assert event["type"] == "release"
    assert event["amount"] is None
    assert event["reason"] == "customer_changed_mind"
    assert event["customer"] == "Іван"


@pytest.mark.asyncio
async def test_not_picked_up_event_is_return_type_with_ttn(client: AsyncClient) -> None:
    init_data, shop_id = await _bootstrap(client, 72004)
    variant_id = await _add_variant(shop_id, name="Черевики", price="800.00")
    reservation_id = await _reserve(client, init_data, variant_id)

    r = await client.post(
        f"/api/reservations/{reservation_id}/ship",
        json={"ttn": "20450000000099"},
        headers={HEADER: init_data},
    )
    assert r.status_code == 200, r.text

    r2 = await client.post(
        f"/api/reservations/{reservation_id}/not-picked-up",
        json={"reason": "did_not_pick_up"},
        headers={HEADER: init_data},
    )
    assert r2.status_code == 200, r2.text

    events = await _history(client, init_data, period="all")
    assert len(events) == 1
    event = events[0]
    assert event["type"] == "return"
    assert event["amount"] is None
    assert event["reason"] == "did_not_pick_up"
    assert event["ttn"] == "20450000000099"


@pytest.mark.asyncio
async def test_date_narrows_to_one_day_and_overrides_period(client: AsyncClient) -> None:
    init_data, shop_id = await _bootstrap(client, 72005)
    variant_id = await _add_variant(shop_id, name="Шапка", price="200.00")

    today = utcnow()
    yesterday = today - timedelta(days=1)

    async with db.async_session() as session:
        session.add(StockMovement(
            shop_id=shop_id, variant_id=variant_id, type=MovementType.sale,
            delta=-1, price_at=Decimal("200.00"), created_at=today,
        ))
        session.add(StockMovement(
            shop_id=shop_id, variant_id=variant_id, type=MovementType.sale,
            delta=-1, price_at=Decimal("200.00"), created_at=yesterday,
        ))
        await session.commit()

    today_only = await _history(
        client, init_data, period="all", date=today.strftime("%Y-%m-%d")
    )
    assert len(today_only) == 1

    all_time = await _history(client, init_data, period="all")
    assert len(all_time) == 2


@pytest.mark.asyncio
async def test_period_filters_without_date(client: AsyncClient) -> None:
    init_data, shop_id = await _bootstrap(client, 72006)
    variant_id = await _add_variant(shop_id, name="Рукавички", price="150.00")

    async with db.async_session() as session:
        session.add(StockMovement(
            shop_id=shop_id, variant_id=variant_id, type=MovementType.sale,
            delta=-1, price_at=Decimal("150.00"), created_at=utcnow() - timedelta(days=40),
        ))
        await session.commit()

    month_events = await _history(client, init_data, period="month")
    assert month_events == []

    all_events = await _history(client, init_data, period="all")
    assert len(all_events) == 1


@pytest.mark.asyncio
async def test_events_sorted_newest_first(client: AsyncClient) -> None:
    init_data, shop_id = await _bootstrap(client, 72007)
    variant_a = await _add_variant(shop_id, name="Товар А", price="10.00")
    variant_b = await _add_variant(shop_id, name="Товар Б", price="10.00")

    await client.post(
        f"/api/variants/{variant_a}/adjust",
        json={"qty": 1, "reason": "sold"},
        headers={HEADER: init_data},
    )
    await client.post(
        f"/api/variants/{variant_b}/adjust",
        json={"qty": 1, "reason": "sold"},
        headers={HEADER: init_data},
    )

    events = await _history(client, init_data, period="all")
    assert len(events) == 2
    assert events[0]["product_name"] == "Товар Б"
    assert events[1]["product_name"] == "Товар А"
