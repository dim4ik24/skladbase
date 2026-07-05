"""
SkladBase — Нова Пошта: довідники міст/відділень, профіль відправника,
створення накладної для резерву (Фіча B3).

Ключ магазину (Shop.np_api_key_encrypted) уже підключений і валідований
у app/api/np.py — тут лише його ВИКОРИСТАННЯ, не зберігання. Профіль
відправника (np_sender_*) не секрет — GET віддає його як є, на відміну
від самого API-ключа.
"""
from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.deps import require_owner, require_permission, require_permission_writable
from app.models import Membership, Shop
from app.security.crypto import decrypt
from app.services.novaposhta import NovaPoshtaError, get_warehouses, search_cities
from app.services.np_shipping import DEFAULT_WEIGHT_KG, NpShippingError, create_ttn

router = APIRouter(prefix="/api", tags=["novaposhta"])


# --------------------------------------------------------------------------- #
#  Схеми
# --------------------------------------------------------------------------- #
class NpCityOut(BaseModel):
    ref: str
    name: str


class NpWarehouseOut(BaseModel):
    ref: str
    name: str


class NpSenderIn(BaseModel):
    city_ref: str
    city_name: str
    warehouse_ref: str
    warehouse_name: str
    phone: str
    name: str


class NpSenderOut(BaseModel):
    city_ref: str | None
    city_name: str | None
    warehouse_ref: str | None
    warehouse_name: str | None
    phone: str | None
    name: str | None


def _shop_to_sender_out(shop: Shop) -> NpSenderOut:
    return NpSenderOut(
        city_ref=shop.np_sender_city_ref,
        city_name=shop.np_sender_city_name,
        warehouse_ref=shop.np_sender_warehouse_ref,
        warehouse_name=shop.np_sender_warehouse_name,
        phone=shop.np_sender_phone,
        name=shop.np_sender_name,
    )


class CreateTtnIn(BaseModel):
    recipient_name: str
    recipient_phone: str
    recipient_city_ref: str
    recipient_warehouse_ref: str
    weight: float = DEFAULT_WEIGHT_KG
    cod: bool = False
    cod_amount: Decimal | None = None
    description: str | None = None


class CreateTtnOut(BaseModel):
    ttn: str
    delivery_cost: Decimal


# --------------------------------------------------------------------------- #
#  Довідники (проксі до НП, потребують підключеного ключа магазину)
# --------------------------------------------------------------------------- #
async def _shop_api_key(shop_id: int, session: AsyncSession) -> str:
    shop = await session.get(Shop, shop_id)
    assert shop is not None
    if not shop.np_api_key_encrypted:
        raise HTTPException(status_code=422, detail="Підключіть ключ Нової Пошти в налаштуваннях")
    return decrypt(shop.np_api_key_encrypted)


@router.get("/np/cities", response_model=list[NpCityOut])
async def list_np_cities(
    q: str,
    membership: Membership = require_permission("can_manage_reservations"),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    api_key = await _shop_api_key(membership.shop_id, session)
    try:
        return await search_cities(api_key, q)
    except NovaPoshtaError as exc:
        raise HTTPException(status_code=422, detail=f"НП: {exc}") from exc


@router.get("/np/warehouses", response_model=list[NpWarehouseOut])
async def list_np_warehouses(
    city_ref: str,
    membership: Membership = require_permission("can_manage_reservations"),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    api_key = await _shop_api_key(membership.shop_id, session)
    try:
        return await get_warehouses(api_key, city_ref)
    except NovaPoshtaError as exc:
        raise HTTPException(status_code=422, detail=f"НП: {exc}") from exc


# --------------------------------------------------------------------------- #
#  Профіль відправника
# --------------------------------------------------------------------------- #
@router.put("/shop/np-sender", response_model=NpSenderOut)
async def set_np_sender(
    payload: NpSenderIn,
    membership: Membership = Depends(require_owner),
    session: AsyncSession = Depends(get_session),
) -> NpSenderOut:
    shop = await session.get(Shop, membership.shop_id)
    assert shop is not None
    shop.np_sender_city_ref = payload.city_ref
    shop.np_sender_city_name = payload.city_name
    shop.np_sender_warehouse_ref = payload.warehouse_ref
    shop.np_sender_warehouse_name = payload.warehouse_name
    shop.np_sender_phone = payload.phone
    shop.np_sender_name = payload.name
    await session.commit()
    return _shop_to_sender_out(shop)


@router.get("/shop/np-sender", response_model=NpSenderOut)
async def get_np_sender(
    membership: Membership = Depends(require_owner),
    session: AsyncSession = Depends(get_session),
) -> NpSenderOut:
    shop = await session.get(Shop, membership.shop_id)
    assert shop is not None
    return _shop_to_sender_out(shop)


# --------------------------------------------------------------------------- #
#  Створення накладної
# --------------------------------------------------------------------------- #
@router.post("/reservations/{reservation_id}/create-ttn", response_model=CreateTtnOut)
async def create_reservation_ttn(
    reservation_id: int,
    payload: CreateTtnIn,
    membership: Membership = require_permission_writable("can_manage_reservations"),
    session: AsyncSession = Depends(get_session),
) -> dict:
    try:
        return await create_ttn(
            session,
            shop_id=membership.shop_id,
            reservation_id=reservation_id,
            recipient_name=payload.recipient_name,
            recipient_phone=payload.recipient_phone,
            recipient_city_ref=payload.recipient_city_ref,
            recipient_warehouse_ref=payload.recipient_warehouse_ref,
            weight=payload.weight,
            cod=payload.cod,
            cod_amount=payload.cod_amount,
            description=payload.description,
        )
    except NpShippingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
