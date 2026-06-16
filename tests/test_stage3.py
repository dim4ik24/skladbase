"""
Stage 3 acceptance tests (inventory: stock, reservations, movements, low-stock).

Criteria (ROADMAP.md, Стадія 3):
  1. reserve зменшує available, але НЕ on_hand; reserved росте
  2. reserve(qty > available) -> відмова (не виняток/500), стан не змінюється
  3. fulfill: on_hand і reserved падають на qty, available консистентний,
     Reservation=fulfilled, є StockMovement(sale)
  4. release повертає reserved у available
  5. restock вище порога обнуляє low_stock_notified_at
  6. sell_direct(qty > on_hand) -> відмова
  7. після будь-якої операції: reserved <= on_hand і available >= 0

ПРИМІТКА: реальний конкурентний оверсел (два паралельні fulfill/sell_direct
останньої одиниці) тут НЕ перевіряється — SQLite серіалізує записи на рівні
файлу, тож гонку умов відтворити неможливо. `with_for_update()` дає реальний
row-lock лише на Postgres; конкурентний тест має сенс тільки там.
"""
from __future__ import annotations

from decimal import Decimal
from http import HTTPStatus
from uuid import uuid4

import pytest
from sqlalchemy import select

from app import db
from app.models import (
    MovementType,
    Product,
    Reservation,
    ReservationSource,
    ReservationStatus,
    Shop,
    StockMovement,
    Variant,
    utcnow,
)
from app.services import inventory
from app.services.inventory import InventoryError


async def _make_variant(on_hand: int, low_stock_threshold: int = 3) -> tuple[int, int]:
    async with db.async_session() as session:
        shop = Shop(owner_tg_id=1, name="Тест", slug=f"shop-{uuid4().hex[:8]}")
        session.add(shop)
        await session.flush()

        product = Product(shop_id=shop.id, name="Товар")
        session.add(product)
        await session.flush()

        variant = Variant(
            shop_id=shop.id,
            product_id=product.id,
            sku=f"SKU-{uuid4().hex[:8]}",
            price=Decimal("100"),
            on_hand=on_hand,
            low_stock_threshold=low_stock_threshold,
        )
        session.add(variant)
        await session.commit()
        return shop.id, variant.id


async def _get_variant(variant_id: int) -> Variant:
    async with db.async_session() as session:
        variant = await session.get(Variant, variant_id)
        assert variant is not None
        return variant


@pytest.mark.asyncio
async def test_reserve_decreases_available_not_on_hand() -> None:
    shop_id, variant_id = await _make_variant(on_hand=10)

    async with db.async_session() as session:
        reservation = await inventory.reserve(
            session,
            shop_id=shop_id,
            variant_id=variant_id,
            qty=4,
            source=ReservationSource.manual,
        )

    assert reservation.status == ReservationStatus.active
    assert reservation.qty == 4

    variant = await _get_variant(variant_id)
    assert variant.on_hand == 10
    assert variant.reserved == 4
    assert variant.available == 6


@pytest.mark.asyncio
async def test_reserve_more_than_available_fails_without_side_effects() -> None:
    shop_id, variant_id = await _make_variant(on_hand=5)

    async with db.async_session() as session:
        with pytest.raises(InventoryError) as exc_info:
            await inventory.reserve(
                session,
                shop_id=shop_id,
                variant_id=variant_id,
                qty=6,
                source=ReservationSource.manual,
            )
    assert exc_info.value.status_code == HTTPStatus.CONFLICT

    variant = await _get_variant(variant_id)
    assert variant.on_hand == 5
    assert variant.reserved == 0

    async with db.async_session() as session:
        reservations = (
            await session.scalars(select(Reservation).where(Reservation.variant_id == variant_id))
        ).all()
    assert reservations == []


@pytest.mark.asyncio
async def test_fulfill_moves_reservation_to_sale() -> None:
    shop_id, variant_id = await _make_variant(on_hand=10)

    async with db.async_session() as session:
        reservation = await inventory.reserve(
            session,
            shop_id=shop_id,
            variant_id=variant_id,
            qty=3,
            source=ReservationSource.app,
        )

    available_before_fulfill = (await _get_variant(variant_id)).available

    async with db.async_session() as session:
        fulfilled = await inventory.fulfill(
            session, shop_id=shop_id, reservation_id=reservation.id
        )

    assert fulfilled.status == ReservationStatus.fulfilled

    variant = await _get_variant(variant_id)
    assert variant.on_hand == 7
    assert variant.reserved == 0
    assert variant.available == available_before_fulfill  # фулфіл не змінює available

    async with db.async_session() as session:
        movements = (
            await session.scalars(
                select(StockMovement).where(
                    StockMovement.variant_id == variant_id,
                    StockMovement.type == MovementType.sale,
                )
            )
        ).all()
    assert len(movements) == 1
    assert movements[0].delta == -3


@pytest.mark.asyncio
async def test_release_returns_reserved_to_available() -> None:
    shop_id, variant_id = await _make_variant(on_hand=8)

    async with db.async_session() as session:
        reservation = await inventory.reserve(
            session,
            shop_id=shop_id,
            variant_id=variant_id,
            qty=5,
            source=ReservationSource.website,
        )

    async with db.async_session() as session:
        released = await inventory.release(
            session, shop_id=shop_id, reservation_id=reservation.id
        )

    assert released.status == ReservationStatus.released
    assert released.released_at is not None

    variant = await _get_variant(variant_id)
    assert variant.on_hand == 8
    assert variant.reserved == 0
    assert variant.available == 8


@pytest.mark.asyncio
async def test_restock_above_threshold_resets_low_stock_flag() -> None:
    shop_id, variant_id = await _make_variant(on_hand=1, low_stock_threshold=3)

    async with db.async_session() as session:
        variant = await session.get(Variant, variant_id)
        assert variant is not None
        variant.low_stock_notified_at = utcnow()
        await session.commit()

    async with db.async_session() as session:
        restocked = await inventory.restock(
            session, shop_id=shop_id, variant_id=variant_id, qty=10
        )

    assert restocked.available > restocked.low_stock_threshold
    assert restocked.low_stock_notified_at is None


@pytest.mark.asyncio
async def test_sell_direct_more_than_on_hand_fails() -> None:
    shop_id, variant_id = await _make_variant(on_hand=2)

    async with db.async_session() as session:
        with pytest.raises(InventoryError) as exc_info:
            await inventory.sell_direct(session, shop_id=shop_id, variant_id=variant_id, qty=3)
    assert exc_info.value.status_code == HTTPStatus.CONFLICT

    variant = await _get_variant(variant_id)
    assert variant.on_hand == 2


@pytest.mark.asyncio
async def test_invariants_hold_after_sequence_of_operations() -> None:
    shop_id, variant_id = await _make_variant(on_hand=10)

    async def _assert_invariants() -> None:
        variant = await _get_variant(variant_id)
        assert variant.reserved <= variant.on_hand
        assert variant.available >= 0

    async with db.async_session() as session:
        reservation = await inventory.reserve(
            session,
            shop_id=shop_id,
            variant_id=variant_id,
            qty=4,
            source=ReservationSource.manual,
        )
    await _assert_invariants()

    async with db.async_session() as session:
        await inventory.fulfill(session, shop_id=shop_id, reservation_id=reservation.id)
    await _assert_invariants()

    async with db.async_session() as session:
        await inventory.restock(session, shop_id=shop_id, variant_id=variant_id, qty=5)
    await _assert_invariants()

    async with db.async_session() as session:
        await inventory.sell_direct(session, shop_id=shop_id, variant_id=variant_id, qty=2)
    await _assert_invariants()

    async with db.async_session() as session:
        await inventory.adjust(session, shop_id=shop_id, variant_id=variant_id, new_on_hand=1)
    await _assert_invariants()
