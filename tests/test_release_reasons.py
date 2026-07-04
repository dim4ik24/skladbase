"""
Причина зняття резерву (StockMovement.reason/comment на type=release,
POST /api/reservations/{id}/release приймає опційний {reason, comment}).

Criteria:
  1. release з reason -> StockMovement(type=release) має reason
  2. release без body (авто-зняття/попередній контракт) -> як і раніше, reason=None
  3. reason=other без comment -> 422, резерв лишається активним
  4. reason=other з comment -> StockMovement.comment заповнений
"""
from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app import db
from app.models import MovementType, Product, StockMovement, Variant
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
            price=Decimal("100.00"),
            on_hand=on_hand,
        )
        session.add(variant)
        await session.commit()
        return variant.id


async def _reserve(client: AsyncClient, init_data: str, variant_id: int, qty: int = 2) -> int:
    r = await client.post(
        f"/api/variants/{variant_id}/reserve", json={"qty": qty}, headers={HEADER: init_data}
    )
    assert r.status_code == 200, r.text
    return r.json()["id"]


async def _last_release_movement(variant_id: int) -> StockMovement:
    async with db.async_session() as session:
        movement = await session.scalar(
            select(StockMovement)
            .where(
                StockMovement.variant_id == variant_id,
                StockMovement.type == MovementType.release,
            )
            .order_by(StockMovement.id.desc())
        )
    assert movement is not None
    return movement


@pytest.mark.asyncio
async def test_release_with_reason_writes_reason_on_movement(client: AsyncClient) -> None:
    init_data, shop_id = await _bootstrap(client, 70001)
    variant_id = await _add_variant(shop_id)
    reservation_id = await _reserve(client, init_data, variant_id)

    r = await client.post(
        f"/api/reservations/{reservation_id}/release",
        json={"reason": "customer_changed_mind"},
        headers={HEADER: init_data},
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "released"

    movement = await _last_release_movement(variant_id)
    assert movement.reason == "customer_changed_mind"
    assert movement.comment is None


@pytest.mark.asyncio
async def test_release_without_body_keeps_reason_none(client: AsyncClient) -> None:
    """Авто-зняття (протермінований резерв, скасування замовлення) і старі
    клієнти й далі шлють release без body — контракт не зламано."""
    init_data, shop_id = await _bootstrap(client, 70002)
    variant_id = await _add_variant(shop_id)
    reservation_id = await _reserve(client, init_data, variant_id)

    r = await client.post(
        f"/api/reservations/{reservation_id}/release", headers={HEADER: init_data}
    )
    assert r.status_code == 200, r.text

    movement = await _last_release_movement(variant_id)
    assert movement.reason is None


@pytest.mark.asyncio
async def test_release_other_without_comment_returns_422_and_reservation_stays_active(
    client: AsyncClient,
) -> None:
    init_data, shop_id = await _bootstrap(client, 70003)
    variant_id = await _add_variant(shop_id)
    reservation_id = await _reserve(client, init_data, variant_id)

    r = await client.post(
        f"/api/reservations/{reservation_id}/release",
        json={"reason": "other"},
        headers={HEADER: init_data},
    )
    assert r.status_code == 422

    async with db.async_session() as session:
        variant = await session.get(Variant, variant_id)
    assert variant is not None
    assert variant.reserved == 2  # резерв не знято


@pytest.mark.asyncio
async def test_release_other_with_comment_succeeds(client: AsyncClient) -> None:
    init_data, shop_id = await _bootstrap(client, 70004)
    variant_id = await _add_variant(shop_id)
    reservation_id = await _reserve(client, init_data, variant_id)

    r = await client.post(
        f"/api/reservations/{reservation_id}/release",
        json={"reason": "other", "comment": "клієнт заблокував бота"},
        headers={HEADER: init_data},
    )
    assert r.status_code == 200, r.text

    movement = await _last_release_movement(variant_id)
    assert movement.reason == "other"
    assert movement.comment == "клієнт заблокував бота"
