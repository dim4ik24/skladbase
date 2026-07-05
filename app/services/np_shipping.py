"""
SkladBase — оркестрація створення накладної НП для резерву (Фіча B3).

Бізнес-логіка (guards, дефолти, DB-запис) тут; сама розмова з API Нової
Пошти — в services/novaposhta.py (чистий клієнт). Успішне створення
документа завершується викликом existing inventory.ship() — жодного
дублювання логіки відправки резерву.
"""
from __future__ import annotations

from decimal import Decimal
from http import HTTPStatus

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Product, Reservation, ReservationStatus, Shop, Variant
from app.security.crypto import decrypt
from app.services import inventory
from app.services.novaposhta import NovaPoshtaError, create_document

DEFAULT_WEIGHT_KG = 0.5


class NpShippingError(Exception):
    """Помилка створення накладної з HTTP статус-кодом для API-шару."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


async def create_ttn(
    session: AsyncSession,
    *,
    shop_id: int,
    reservation_id: int,
    recipient_name: str,
    recipient_phone: str,
    recipient_city_ref: str,
    recipient_warehouse_ref: str,
    weight: float = DEFAULT_WEIGHT_KG,
    cod: bool = False,
    cod_amount: Decimal | None = None,
    description: str | None = None,
) -> dict:
    """Гварди в порядку: резерв active (409) -> ключ НП підключено (422) ->
    дані відправника заповнені (422). Аж потім — реальний виклик НП (щоб не
    палити документ на завідомо невалідному резерві)."""
    reservation = await session.scalar(
        select(Reservation).where(Reservation.id == reservation_id, Reservation.shop_id == shop_id)
    )
    if reservation is None:
        raise NpShippingError(HTTPStatus.NOT_FOUND, "Резерв не знайдено")
    if reservation.status != ReservationStatus.active:
        raise NpShippingError(HTTPStatus.CONFLICT, "Резерв не активний")

    shop = await session.get(Shop, shop_id)
    assert shop is not None
    if not shop.np_api_key_encrypted:
        raise NpShippingError(HTTPStatus.UNPROCESSABLE_ENTITY, "Підключіть ключ Нової Пошти в налаштуваннях")

    sender_city_ref = shop.np_sender_city_ref
    sender_warehouse_ref = shop.np_sender_warehouse_ref
    sender_phone = shop.np_sender_phone
    if (
        sender_city_ref is None
        or sender_warehouse_ref is None
        or sender_phone is None
        or shop.np_sender_name is None
    ):
        raise NpShippingError(HTTPStatus.UNPROCESSABLE_ENTITY, "Заповніть дані відправника в налаштуваннях")

    variant = await session.scalar(
        select(Variant).where(Variant.id == reservation.variant_id, Variant.shop_id == shop_id)
    )
    assert variant is not None
    product = await session.get(Product, variant.product_id)
    assert product is not None

    declared_value = variant.price * reservation.qty
    resolved_description = description or product.name
    resolved_cod_amount = cod_amount if cod_amount is not None else declared_value

    api_key = decrypt(shop.np_api_key_encrypted)
    try:
        result = await create_document(
            api_key,
            sender_city_ref=sender_city_ref,
            sender_warehouse_ref=sender_warehouse_ref,
            sender_phone=sender_phone,
            recipient_name=recipient_name,
            recipient_phone=recipient_phone,
            recipient_city_ref=recipient_city_ref,
            recipient_warehouse_ref=recipient_warehouse_ref,
            weight=weight,
            description=resolved_description,
            cost=declared_value,
            cod_amount=resolved_cod_amount if cod else None,
        )
    except NovaPoshtaError as exc:
        raise NpShippingError(HTTPStatus.UNPROCESSABLE_ENTITY, f"НП: {exc}") from exc

    await inventory.ship(session, shop_id=shop_id, reservation_id=reservation_id, ttn=result.ttn)

    return {"ttn": result.ttn, "delivery_cost": result.cost}
