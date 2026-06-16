"""
SkladBase — єдиний сервіс зміни складу (CLAUDE.md, інваріант №3).

Жодна інша частина системи не повинна напряму змінювати `Variant.on_hand` /
`Variant.reserved`. Кожна операція тут атомарна (`SELECT ... FOR UPDATE` по
варіанту — на Postgres це реальний row-lock; на SQLite ігнорується, бо БД
серіалізує записи на рівні файлу — для dev/тестів цього достатньо) і завжди
пише `StockMovement`.

Інваріант (CLAUDE.md, №4): замовлення -> резерв, не пряме списання.
  reserved <= on_hand
  available = on_hand - reserved >= 0

Реальний конкурентний оверсел (два паралельні `fulfill`/`sell_direct` останньої
одиниці) на SQLite не відтворити — потрібен Postgres з реальним row-level
locking під конкурентним навантаженням.
"""
from __future__ import annotations

from datetime import datetime
from http import HTTPStatus

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    MovementType,
    Reservation,
    ReservationSource,
    ReservationStatus,
    StockMovement,
    Variant,
    utcnow,
)


class InventoryError(Exception):
    """Помилка складу з HTTP статус-кодом для API-шару."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


async def _locked_variant(session: AsyncSession, shop_id: int, variant_id: int) -> Variant:
    variant = await session.scalar(
        select(Variant)
        .where(Variant.id == variant_id, Variant.shop_id == shop_id)
        .with_for_update()
    )
    if variant is None:
        raise InventoryError(HTTPStatus.NOT_FOUND, "Варіант не знайдено")
    return variant


async def _locked_reservation(
    session: AsyncSession, shop_id: int, reservation_id: int
) -> Reservation:
    reservation = await session.scalar(
        select(Reservation)
        .where(Reservation.id == reservation_id, Reservation.shop_id == shop_id)
        .with_for_update()
    )
    if reservation is None:
        raise InventoryError(HTTPStatus.NOT_FOUND, "Резерв не знайдено")
    return reservation


def _record_movement(
    session: AsyncSession,
    *,
    shop_id: int,
    variant_id: int,
    type_: MovementType,
    delta: int,
    order_id: int | None = None,
) -> None:
    if delta == 0:
        return
    session.add(
        StockMovement(
            shop_id=shop_id,
            variant_id=variant_id,
            order_id=order_id,
            type=type_,
            delta=delta,
        )
    )


def _maybe_reset_low_stock_flag(variant: Variant) -> None:
    if variant.available > variant.low_stock_threshold:
        variant.low_stock_notified_at = None


def _require_positive_qty(qty: int) -> None:
    if qty <= 0:
        raise InventoryError(HTTPStatus.BAD_REQUEST, "qty має бути додатнім")


# --------------------------------------------------------------------------- #
#  Резерв (замовлення -> резерв, не пряме списання)                           #
# --------------------------------------------------------------------------- #
async def reserve(
    session: AsyncSession,
    *,
    shop_id: int,
    variant_id: int,
    qty: int,
    source: ReservationSource,
    reason: str | None = None,
    customer_note: str | None = None,
    expires_at: datetime | None = None,
    order_id: int | None = None,
) -> Reservation:
    _require_positive_qty(qty)

    variant = await _locked_variant(session, shop_id, variant_id)
    if variant.available < qty:
        raise InventoryError(
            HTTPStatus.CONFLICT,
            f"Недостатньо залишку: доступно {variant.available}, потрібно {qty}",
        )

    variant.reserved += qty

    reservation = Reservation(
        shop_id=shop_id,
        variant_id=variant_id,
        order_id=order_id,
        qty=qty,
        reason=reason,
        customer_note=customer_note,
        source=source,
        status=ReservationStatus.active,
        expires_at=expires_at,
    )
    session.add(reservation)

    _record_movement(
        session,
        shop_id=shop_id,
        variant_id=variant_id,
        type_=MovementType.reserve,
        delta=qty,
        order_id=order_id,
    )

    await session.commit()
    await session.refresh(reservation)
    return reservation


async def release(session: AsyncSession, *, shop_id: int, reservation_id: int) -> Reservation:
    reservation = await _locked_reservation(session, shop_id, reservation_id)
    if reservation.status != ReservationStatus.active:
        raise InventoryError(HTTPStatus.CONFLICT, "Резерв не активний")

    variant = await _locked_variant(session, shop_id, reservation.variant_id)
    variant.reserved -= reservation.qty

    reservation.status = ReservationStatus.released
    reservation.released_at = utcnow()

    _record_movement(
        session,
        shop_id=shop_id,
        variant_id=variant.id,
        type_=MovementType.release,
        delta=-reservation.qty,
        order_id=reservation.order_id,
    )

    await session.commit()
    await session.refresh(reservation)
    return reservation


async def fulfill(session: AsyncSession, *, shop_id: int, reservation_id: int) -> Reservation:
    reservation = await _locked_reservation(session, shop_id, reservation_id)
    if reservation.status != ReservationStatus.active:
        raise InventoryError(HTTPStatus.CONFLICT, "Резерв не активний")

    variant = await _locked_variant(session, shop_id, reservation.variant_id)
    if variant.on_hand < reservation.qty:
        # Не повинно траплятись (резерв уже гарантував available), захист про всяк випадок.
        raise InventoryError(HTTPStatus.CONFLICT, "Недостатньо залишку для списання резерву")

    variant.on_hand -= reservation.qty
    variant.reserved -= reservation.qty

    reservation.status = ReservationStatus.fulfilled

    _record_movement(
        session,
        shop_id=shop_id,
        variant_id=variant.id,
        type_=MovementType.sale,
        delta=-reservation.qty,
        order_id=reservation.order_id,
    )

    await session.commit()
    await session.refresh(reservation)
    return reservation


# --------------------------------------------------------------------------- #
#  Прямий продаж (без попереднього резерву)                                   #
# --------------------------------------------------------------------------- #
async def sell_direct(
    session: AsyncSession,
    *,
    shop_id: int,
    variant_id: int,
    qty: int,
    order_id: int | None = None,
) -> Variant:
    _require_positive_qty(qty)

    variant = await _locked_variant(session, shop_id, variant_id)
    if variant.available < qty:
        raise InventoryError(
            HTTPStatus.CONFLICT,
            f"Недостатньо доступного залишку: доступно {variant.available}, потрібно {qty}",
        )

    variant.on_hand -= qty

    _record_movement(
        session,
        shop_id=shop_id,
        variant_id=variant_id,
        type_=MovementType.sale,
        delta=-qty,
        order_id=order_id,
    )

    await session.commit()
    await session.refresh(variant)
    return variant


# --------------------------------------------------------------------------- #
#  Поповнення і ручна корекція                                                #
# --------------------------------------------------------------------------- #
async def restock(session: AsyncSession, *, shop_id: int, variant_id: int, qty: int) -> Variant:
    _require_positive_qty(qty)

    variant = await _locked_variant(session, shop_id, variant_id)
    variant.on_hand += qty
    _maybe_reset_low_stock_flag(variant)

    _record_movement(
        session,
        shop_id=shop_id,
        variant_id=variant_id,
        type_=MovementType.restock,
        delta=qty,
    )

    await session.commit()
    await session.refresh(variant)
    return variant


async def adjust(
    session: AsyncSession,
    *,
    shop_id: int,
    variant_id: int,
    new_on_hand: int,
    reason: str | None = None,
) -> Variant:
    """Ручна корекція залишку. `reason` приймається для контексту викликача,
    але не персистується — у `StockMovement` немає відповідного поля
    (models.py — існуючий файл, не переписуємо його без потреби)."""
    if new_on_hand < 0:
        raise InventoryError(HTTPStatus.BAD_REQUEST, "on_hand не може бути від'ємним")

    variant = await _locked_variant(session, shop_id, variant_id)
    if new_on_hand < variant.reserved:
        raise InventoryError(
            HTTPStatus.CONFLICT,
            f"Новий залишок ({new_on_hand}) менший за зарезервований ({variant.reserved})",
        )

    delta = new_on_hand - variant.on_hand
    variant.on_hand = new_on_hand
    _maybe_reset_low_stock_flag(variant)

    _record_movement(
        session,
        shop_id=shop_id,
        variant_id=variant_id,
        type_=MovementType.adjustment,
        delta=delta,
    )

    await session.commit()
    await session.refresh(variant)
    return variant
