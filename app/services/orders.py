"""
SkladBase — оркестрація замовлень (Стадія 4a, ядро).

Замовлення -> резерв, ніколи пряме списання (CLAUDE.md, інваріант №4).
Списання (`fulfill`) відбувається лише після підтвердження власником
(`confirm_order`); резерви знімаються при скасуванні (`cancel_order`).

Ідемпотентність: повторний запит з тим самим (shop_id, idempotency_key)
повертає вже створене замовлення, новий запис не з'являється — навіть під
конкурентним POST (`UNIQUE(shop_id, idempotency_key)` ловить гонку,
`IntegrityError` -> повертаємо наявний order).

Резерви всіх позицій замовлення атомарні РАЗОМ: якщо хоч один item не може
зарезервуватись — відкат усього замовлення (жодного часткового резерву).
Для цього кожен виклик `inventory.*` тут робиться з `commit=False`, і єдиний
`session.commit()` стоїть наприкінці успішної послідовності.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from http import HTTPStatus

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    Order,
    OrderItem,
    OrderSource,
    OrderStatus,
    Reservation,
    ReservationSource,
    ReservationStatus,
    Shop,
    Variant,
)
from app.services import inventory
from app.services.inventory import InventoryError
from app.services.webhooks import dispatch_stock_changed


class OrderError(Exception):
    """Помилка замовлення з HTTP статус-кодом для API-шару."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


@dataclass
class OrderItemInput:
    variant_id: int
    qty: int


@dataclass
class OrderInput:
    items: list[OrderItemInput]
    idempotency_key: str
    customer_name: str | None = None
    customer_contact: str | None = None


def _order_query():
    return select(Order).options(selectinload(Order.items))


async def _find_by_idempotency_key(
    session: AsyncSession, shop_id: int, idempotency_key: str
) -> Order | None:
    return await session.scalar(
        _order_query().where(Order.shop_id == shop_id, Order.idempotency_key == idempotency_key)
    )


async def _get_owned_order(session: AsyncSession, shop_id: int, order_id: int) -> Order:
    order = await session.scalar(
        _order_query().where(Order.id == order_id, Order.shop_id == shop_id)
    )
    if order is None:
        raise OrderError(HTTPStatus.NOT_FOUND, "Замовлення не знайдено")
    return order


async def _active_reservations(
    session: AsyncSession, shop_id: int, order_id: int
) -> list[Reservation]:
    return list(
        (
            await session.scalars(
                select(Reservation).where(
                    Reservation.shop_id == shop_id,
                    Reservation.order_id == order_id,
                    Reservation.status == ReservationStatus.active,
                )
            )
        ).all()
    )


async def _notify_stock_changed(session: AsyncSession, shop_id: int, order: Order) -> None:
    """Best-effort вихідний вебхук ПІСЛЯ commit (стан складу вже змінився).
    Викликається з уже завершеної транзакції — помилка вебхука сюди не
    долетить (`dispatch_stock_changed` сама ловить мережеві винятки)."""
    shop = await session.get(Shop, shop_id)
    if shop is None:
        return

    variant_ids = {item.variant_id for item in order.items}
    if not variant_ids:
        return

    variants = list(
        (await session.scalars(select(Variant).where(Variant.id.in_(variant_ids)))).all()
    )
    await dispatch_stock_changed(shop, variants)


async def create_website_order(
    session: AsyncSession, *, shop_id: int, payload: OrderInput
) -> tuple[Order, bool]:
    """Повертає `(order, created)`. `created=False` означає ідемпотентний
    повтор — викликач (API-шар) на цій підставі вирішує, чи слати notify-хук
    власнику (повторно нотифікувати про вже відоме замовлення не треба)."""
    if not payload.items:
        raise OrderError(HTTPStatus.BAD_REQUEST, "Потрібен хоча б один товар у замовленні")

    existing = await _find_by_idempotency_key(session, shop_id, payload.idempotency_key)
    if existing is not None:
        return existing, False

    order = Order(
        shop_id=shop_id,
        source=OrderSource.website,
        status=OrderStatus.pending,
        idempotency_key=payload.idempotency_key,
        customer_name=payload.customer_name,
        customer_contact=payload.customer_contact,
        total=Decimal("0"),
    )
    session.add(order)

    try:
        # Отримати order.id; гонку двох однакових POST по
        # UNIQUE(shop_id, idempotency_key) ловимо саме тут.
        await session.flush()
    except IntegrityError:
        await session.rollback()
        existing = await _find_by_idempotency_key(session, shop_id, payload.idempotency_key)
        if existing is not None:
            return existing, False
        raise

    total = Decimal("0")
    try:
        for item in payload.items:
            variant = await session.scalar(
                select(Variant).where(Variant.id == item.variant_id, Variant.shop_id == shop_id)
            )
            if variant is None:
                raise OrderError(HTTPStatus.NOT_FOUND, f"Варіант {item.variant_id} не знайдено")

            session.add(
                OrderItem(
                    order_id=order.id,
                    variant_id=variant.id,
                    qty=item.qty,
                    price_at_order=variant.price,
                )
            )
            total += variant.price * item.qty

            await inventory.reserve(
                session,
                shop_id=shop_id,
                variant_id=variant.id,
                qty=item.qty,
                source=ReservationSource.website,
                order_id=order.id,
                commit=False,
            )
    except InventoryError as exc:
        await session.rollback()
        raise OrderError(exc.status_code, exc.detail) from exc
    except OrderError:
        await session.rollback()
        raise

    order.total = total
    await session.commit()
    await session.refresh(order, attribute_names=["items"])
    await _notify_stock_changed(session, shop_id, order)
    return order, True


async def confirm_order(session: AsyncSession, *, shop_id: int, order_id: int) -> Order:
    """Підтвердження власником: всі активні резерви замовлення -> fulfilled."""
    order = await _get_owned_order(session, shop_id, order_id)
    if order.status != OrderStatus.pending:
        raise OrderError(HTTPStatus.CONFLICT, "Замовлення вже не очікує підтвердження")

    reservations = await _active_reservations(session, shop_id, order_id)
    try:
        for reservation in reservations:
            await inventory.fulfill(
                session, shop_id=shop_id, reservation_id=reservation.id, commit=False
            )
    except InventoryError as exc:
        await session.rollback()
        raise OrderError(exc.status_code, exc.detail) from exc

    order.status = OrderStatus.fulfilled
    await session.commit()
    await session.refresh(order, attribute_names=["items"])
    await _notify_stock_changed(session, shop_id, order)
    return order


async def cancel_order(session: AsyncSession, *, shop_id: int, order_id: int) -> Order:
    """Скасування: всі активні резерви замовлення -> released."""
    order = await _get_owned_order(session, shop_id, order_id)
    if order.status != OrderStatus.pending:
        raise OrderError(HTTPStatus.CONFLICT, "Замовлення не можна скасувати в цьому статусі")

    reservations = await _active_reservations(session, shop_id, order_id)
    try:
        for reservation in reservations:
            await inventory.release(
                session, shop_id=shop_id, reservation_id=reservation.id, commit=False
            )
    except InventoryError as exc:
        await session.rollback()
        raise OrderError(exc.status_code, exc.detail) from exc

    order.status = OrderStatus.canceled
    await session.commit()
    await session.refresh(order, attribute_names=["items"])
    await _notify_stock_changed(session, shop_id, order)
    return order
