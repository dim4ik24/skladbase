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

Кожна операція приймає `commit: bool = True`. За замовчуванням викликана
самостійно — комітить себе. Коли кілька операцій мають бути атомарними разом
(наприклад, резерв усіх позицій замовлення — все або нічого), викликач
передає `commit=False` і сам керує транзакцією (commit/rollback) навколо
всієї послідовності (див. `services/orders.py`).
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from http import HTTPStatus
from typing import TypeVar

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

_T = TypeVar("_T")

WRITE_OFF_REASONS = ("sold", "defect", "correction", "other")
RELEASE_REASONS = ("customer_changed_mind", "unresponsive", "mistaken_reservation", "other")
NOT_PICKED_UP_REASONS = ("did_not_pick_up", "refused", "other")


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
    reason: str | None = None,
    comment: str | None = None,
    price_at: Decimal | None = None,
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
            reason=reason,
            comment=comment,
            price_at=price_at,
        )
    )


def _maybe_reset_low_stock_flag(variant: Variant) -> None:
    if variant.available > variant.low_stock_threshold:
        variant.low_stock_notified_at = None


def _require_positive_qty(qty: int) -> None:
    if qty <= 0:
        raise InventoryError(HTTPStatus.BAD_REQUEST, "qty має бути додатнім")


async def _finalize(session: AsyncSession, obj: _T, *, commit: bool) -> _T:
    if commit:
        await session.commit()
        await session.refresh(obj)
    else:
        await session.flush()
    return obj


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
    commit: bool = True,
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

    return await _finalize(session, reservation, commit=commit)


async def release(
    session: AsyncSession,
    *,
    shop_id: int,
    reservation_id: int,
    reason: str | None = None,
    comment: str | None = None,
    commit: bool = True,
) -> Reservation:
    """Зняття резерву. `reason` опційний — авто-зняття (протермінований резерв
    у `tasks.py`, скасування замовлення в `orders.py`) викликають без причини;
    причина потрібна лише коли менеджер знімає резерв вручну через діалог."""
    if reason is not None and reason not in RELEASE_REASONS:
        raise InventoryError(HTTPStatus.UNPROCESSABLE_ENTITY, f"Невідома причина: {reason}")
    if reason == "other" and not comment:
        raise InventoryError(
            HTTPStatus.UNPROCESSABLE_ENTITY, "Для причини 'other' коментар обов'язковий"
        )

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
        reason=reason,
        comment=comment,
    )

    return await _finalize(session, reservation, commit=commit)


async def _finalize_sale(
    session: AsyncSession,
    *,
    shop_id: int,
    reservation: Reservation,
    variant: Variant,
    commit: bool,
) -> Reservation:
    """Спільний хвіст fulfill()/pick_up(): фіксує продаж і дохід. On_hand/reserved
    уже скориговані викликачем (fulfill — напряму з active; pick_up — раніше,
    на ship(), бо товар фізично поїхав ще тоді) — тут лише статус і sale-рух."""
    reservation.status = ReservationStatus.fulfilled

    _record_movement(
        session,
        shop_id=shop_id,
        variant_id=variant.id,
        type_=MovementType.sale,
        delta=-reservation.qty,
        order_id=reservation.order_id,
        price_at=variant.price,
    )

    return await _finalize(session, reservation, commit=commit)


async def fulfill(
    session: AsyncSession,
    *,
    shop_id: int,
    reservation_id: int,
    commit: bool = True,
) -> Reservation:
    """Прямий продаж раніше відкладеного резерву (без відправки, зустріч/самовивіз)."""
    reservation = await _locked_reservation(session, shop_id, reservation_id)
    if reservation.status != ReservationStatus.active:
        raise InventoryError(HTTPStatus.CONFLICT, "Резерв не активний")

    variant = await _locked_variant(session, shop_id, reservation.variant_id)
    if variant.on_hand < reservation.qty:
        # Не повинно траплятись (резерв уже гарантував available), захист про всяк випадок.
        raise InventoryError(HTTPStatus.CONFLICT, "Недостатньо залишку для списання резерву")

    variant.on_hand -= reservation.qty
    variant.reserved -= reservation.qty

    return await _finalize_sale(session, shop_id=shop_id, reservation=reservation, variant=variant, commit=commit)


async def ship(
    session: AsyncSession,
    *,
    shop_id: int,
    reservation_id: int,
    ttn: str | None = None,
    commit: bool = True,
) -> Reservation:
    """Відправка резерву (Нова пошта тощо). Товар фізично покидає магазин —
    on_hand і reserved знімаються ОБОМА одразу (інакше available зайво
    занижується: earmark більше нікому не потрібен, бо одиниця вже їде до
    конкретного клієнта). ТТН опційний — продавець може вписати пізніше
    через update_ttn(). Без stock-руху: сума on_hand+reserved не змінюється,
    змінюється лише статус/локація товару."""
    reservation = await _locked_reservation(session, shop_id, reservation_id)
    if reservation.status != ReservationStatus.active:
        raise InventoryError(HTTPStatus.CONFLICT, "Резерв не активний")

    variant = await _locked_variant(session, shop_id, reservation.variant_id)
    variant.on_hand -= reservation.qty
    variant.reserved -= reservation.qty

    reservation.status = ReservationStatus.shipped
    reservation.shipped_at = utcnow()
    reservation.ttn = ttn

    return await _finalize(session, reservation, commit=commit)


async def update_ttn(
    session: AsyncSession,
    *,
    shop_id: int,
    reservation_id: int,
    ttn: str,
    commit: bool = True,
) -> Reservation:
    """Правка ТТН на вже відправленому резерві (продавець вписав її пізніше)."""
    reservation = await _locked_reservation(session, shop_id, reservation_id)
    if reservation.status != ReservationStatus.shipped:
        raise InventoryError(HTTPStatus.CONFLICT, "Резерв не відправлено")

    reservation.ttn = ttn
    return await _finalize(session, reservation, commit=commit)


async def pick_up(
    session: AsyncSession,
    *,
    shop_id: int,
    reservation_id: int,
    commit: bool = True,
) -> Reservation:
    """Клієнт забрав відправлення. On_hand/reserved вже скориговані на ship() —
    тут лише фіксація продажу/доходу (спільна з fulfill логіка)."""
    reservation = await _locked_reservation(session, shop_id, reservation_id)
    if reservation.status != ReservationStatus.shipped:
        raise InventoryError(HTTPStatus.CONFLICT, "Резерв не відправлено")

    variant = await _locked_variant(session, shop_id, reservation.variant_id)

    return await _finalize_sale(session, shop_id=shop_id, reservation=reservation, variant=variant, commit=commit)


async def not_picked_up(
    session: AsyncSession,
    *,
    shop_id: int,
    reservation_id: int,
    reason: str,
    comment: str | None = None,
    commit: bool = True,
) -> Reservation:
    """Клієнт не забрав відправлення — товар повертається на склад. Доходу
    не було (fulfill/pick_up ще не викликались), тож нема що віднімати:
    рух type=ret з price_at=None (не впливає на revenue у finance_summary).
    Reserved далі не чіпаємо — earmark уже знято на ship()."""
    if reason not in NOT_PICKED_UP_REASONS:
        raise InventoryError(HTTPStatus.UNPROCESSABLE_ENTITY, f"Невідома причина: {reason}")
    if reason == "other" and not comment:
        raise InventoryError(
            HTTPStatus.UNPROCESSABLE_ENTITY, "Для причини 'other' коментар обов'язковий"
        )

    reservation = await _locked_reservation(session, shop_id, reservation_id)
    if reservation.status != ReservationStatus.shipped:
        raise InventoryError(HTTPStatus.CONFLICT, "Резерв не відправлено")

    variant = await _locked_variant(session, shop_id, reservation.variant_id)
    variant.on_hand += reservation.qty

    reservation.status = ReservationStatus.released
    reservation.released_at = utcnow()

    _record_movement(
        session,
        shop_id=shop_id,
        variant_id=variant.id,
        type_=MovementType.ret,
        delta=reservation.qty,
        order_id=reservation.order_id,
        reason=reason,
        comment=comment,
        price_at=None,
    )

    return await _finalize(session, reservation, commit=commit)


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
    commit: bool = True,
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
        price_at=variant.price,
    )

    return await _finalize(session, variant, commit=commit)


# --------------------------------------------------------------------------- #
#  Поповнення і ручна корекція                                                #
# --------------------------------------------------------------------------- #
async def restock(
    session: AsyncSession,
    *,
    shop_id: int,
    variant_id: int,
    qty: int,
    commit: bool = True,
) -> Variant:
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

    return await _finalize(session, variant, commit=commit)


async def write_off(
    session: AsyncSession,
    *,
    shop_id: int,
    variant_id: int,
    qty: int,
    reason: str,
    comment: str | None = None,
    commit: bool = True,
) -> Variant:
    """Списання `qty` одиниць із причиною. Замінює колишній `adjust`
    (встановлення АБСОЛЮТНОГО on_hand) — інший контракт, тому інша назва:
    тут завжди СПИСУЄМО кількість, ніколи не встановлюємо число напряму.

    `reason="sold"` — це реальний продаж повз резерв (прямий облік доходу,
    `type=sale` + `price_at`); `defect`/`correction`/`other` — списання без
    грошового ефекту (`type=adjustment`, `price_at=None`). `other` вимагає
    `comment` — без причини "інше" незрозуміло, що сталось за фактом.
    """
    _require_positive_qty(qty)
    if reason not in WRITE_OFF_REASONS:
        raise InventoryError(HTTPStatus.UNPROCESSABLE_ENTITY, f"Невідома причина: {reason}")
    if reason == "other" and not comment:
        raise InventoryError(
            HTTPStatus.UNPROCESSABLE_ENTITY, "Для причини 'other' коментар обов'язковий"
        )

    variant = await _locked_variant(session, shop_id, variant_id)
    if qty > variant.available:
        raise InventoryError(
            HTTPStatus.CONFLICT,
            f"Недостатньо доступного залишку: доступно {variant.available}, потрібно списати {qty}",
        )

    variant.on_hand -= qty

    if reason == "sold":
        type_ = MovementType.sale
        price_at = variant.price
    else:
        type_ = MovementType.adjustment
        price_at = None

    _record_movement(
        session,
        shop_id=shop_id,
        variant_id=variant_id,
        type_=type_,
        delta=-qty,
        reason=reason,
        comment=comment,
        price_at=price_at,
    )

    return await _finalize(session, variant, commit=commit)
