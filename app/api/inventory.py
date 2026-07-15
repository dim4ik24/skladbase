"""
SkladBase — REST API складу (Стадія 6b): ручні операції з апки над тим, що
вже реалізовано в `app/services/inventory.py` (єдиний дозволений шлях зміни
складу, CLAUDE.md, інваріант №3) — тут лише HTTP-шар над ним, бізнес-логіка
не дублюється.

Мутації під `require_writable` (протермінована підписка -> 402, read-only).
`GET /api/reservations` — під `require_member`, доступний завжди (читання не
блокується read-only режимом). shop_id скрізь з `membership.shop_id`, тенант-
ізоляція гарантується самим `inventory.py` (чужий variant/reservation -> 404).
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.catalog import VariantOut
from app.db import get_session
from app.deps import require_permission, require_permission_writable
from app.i18n import get_lang, msg
from app.models import Membership, Reservation, ReservationSource, ReservationStatus, Variant
from app.services import catalog as catalog_service
from app.services import inventory
from app.services.inventory import InventoryError

router = APIRouter(prefix="/api", tags=["inventory"])


# --------------------------------------------------------------------------- #
#  Схеми
# --------------------------------------------------------------------------- #
class RestockIn(BaseModel):
    qty: int


class AdjustIn(BaseModel):
    qty: int = Field(gt=0)
    reason: Literal["sold", "defect", "correction", "other"]
    comment: str | None = None


class ReserveIn(BaseModel):
    qty: int
    customer_note: str | None = None
    expires_at: datetime | None = None


class ReleaseIn(BaseModel):
    reason: Literal["customer_changed_mind", "unresponsive", "mistaken_reservation", "other"] | None = None
    comment: str | None = None


class ShipIn(BaseModel):
    ttn: str | None = None


class UpdateTtnIn(BaseModel):
    ttn: str


class NotPickedUpIn(BaseModel):
    reason: Literal["did_not_pick_up", "refused", "other"]
    comment: str | None = None


class ReservationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    variant_id: int
    order_id: int | None
    qty: int
    reason: str | None
    customer_note: str | None
    source: ReservationSource
    status: ReservationStatus
    ttn: str | None
    np_status: str | None
    np_recipient: str | None
    expires_at: datetime | None
    created_at: datetime
    released_at: datetime | None
    shipped_at: datetime | None


# --------------------------------------------------------------------------- #
#  Варіанти: поповнення / корекція / ручний резерв
# --------------------------------------------------------------------------- #
async def _enforce_variant_product_writable(
    variant_id: int, shop_id: int, session: AsyncSession, lang: str
) -> None:
    """Завантажує варіант без lock, дістає product_id, перевіряє enforce_product_writable.
    Inventory-сервіс потім ще раз локує той самий варіант через SELECT FOR UPDATE."""
    variant = await session.scalar(
        select(Variant).where(Variant.id == variant_id, Variant.shop_id == shop_id)
    )
    if variant is None:
        raise HTTPException(status_code=404, detail=msg("catalog.variant_not_found", lang))
    try:
        await catalog_service.enforce_product_writable(variant.product_id, shop_id, session)
    except catalog_service.CatalogError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail(lang)) from exc


@router.post("/variants/{variant_id}/restock", response_model=VariantOut)
async def restock_variant(
    variant_id: int,
    payload: RestockIn,
    membership: Membership = require_permission_writable("can_manage_stock"),
    session: AsyncSession = Depends(get_session),
    lang: str = Depends(get_lang),
) -> Variant:
    await _enforce_variant_product_writable(variant_id, membership.shop_id, session, lang)
    try:
        return await inventory.restock(
            session, shop_id=membership.shop_id, variant_id=variant_id, qty=payload.qty
        )
    except InventoryError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail(lang)) from exc


@router.post("/variants/{variant_id}/adjust", response_model=VariantOut)
async def adjust_variant(
    variant_id: int,
    payload: AdjustIn,
    membership: Membership = require_permission_writable("can_manage_stock"),
    session: AsyncSession = Depends(get_session),
    lang: str = Depends(get_lang),
) -> Variant:
    await _enforce_variant_product_writable(variant_id, membership.shop_id, session, lang)
    try:
        return await inventory.write_off(
            session,
            shop_id=membership.shop_id,
            variant_id=variant_id,
            qty=payload.qty,
            reason=payload.reason,
            comment=payload.comment,
        )
    except InventoryError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail(lang)) from exc


@router.post("/variants/{variant_id}/reserve", response_model=ReservationOut)
async def reserve_variant(
    variant_id: int,
    payload: ReserveIn,
    membership: Membership = require_permission_writable("can_manage_reservations"),
    session: AsyncSession = Depends(get_session),
    lang: str = Depends(get_lang),
) -> Reservation:
    """Ручний резерв «відклади товар» — менеджер тримає одиницю для клієнта
    поза замовленням із сайту (`ReservationSource.manual`)."""
    await _enforce_variant_product_writable(variant_id, membership.shop_id, session, lang)
    try:
        return await inventory.reserve(
            session,
            shop_id=membership.shop_id,
            variant_id=variant_id,
            qty=payload.qty,
            source=ReservationSource.manual,
            customer_note=payload.customer_note,
            expires_at=payload.expires_at,
        )
    except InventoryError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail(lang)) from exc


# --------------------------------------------------------------------------- #
#  Резерви: зняти / продати
# --------------------------------------------------------------------------- #
@router.post("/reservations/{reservation_id}/release", response_model=ReservationOut)
async def release_reservation(
    reservation_id: int,
    payload: ReleaseIn | None = None,
    membership: Membership = require_permission_writable("can_manage_reservations"),
    session: AsyncSession = Depends(get_session),
    lang: str = Depends(get_lang),
) -> Reservation:
    try:
        return await inventory.release(
            session,
            shop_id=membership.shop_id,
            reservation_id=reservation_id,
            reason=payload.reason if payload else None,
            comment=payload.comment if payload else None,
        )
    except InventoryError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail(lang)) from exc


@router.post("/reservations/{reservation_id}/fulfill", response_model=ReservationOut)
async def fulfill_reservation(
    reservation_id: int,
    membership: Membership = require_permission_writable("can_manage_reservations"),
    session: AsyncSession = Depends(get_session),
    lang: str = Depends(get_lang),
) -> Reservation:
    """Ручний продаж раніше відкладеного резерву (списує on_hand)."""
    try:
        return await inventory.fulfill(
            session, shop_id=membership.shop_id, reservation_id=reservation_id
        )
    except InventoryError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail(lang)) from exc


@router.post("/reservations/{reservation_id}/ship", response_model=ReservationOut)
async def ship_reservation(
    reservation_id: int,
    payload: ShipIn | None = None,
    membership: Membership = require_permission_writable("can_manage_reservations"),
    session: AsyncSession = Depends(get_session),
    lang: str = Depends(get_lang),
) -> Reservation:
    try:
        return await inventory.ship(
            session,
            shop_id=membership.shop_id,
            reservation_id=reservation_id,
            ttn=payload.ttn if payload else None,
        )
    except InventoryError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail(lang)) from exc


@router.patch("/reservations/{reservation_id}/ttn", response_model=ReservationOut)
async def update_reservation_ttn(
    reservation_id: int,
    payload: UpdateTtnIn,
    membership: Membership = require_permission_writable("can_manage_reservations"),
    session: AsyncSession = Depends(get_session),
    lang: str = Depends(get_lang),
) -> Reservation:
    try:
        return await inventory.update_ttn(
            session, shop_id=membership.shop_id, reservation_id=reservation_id, ttn=payload.ttn
        )
    except InventoryError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail(lang)) from exc


@router.post("/reservations/{reservation_id}/pick-up", response_model=ReservationOut)
async def pick_up_reservation(
    reservation_id: int,
    membership: Membership = require_permission_writable("can_manage_reservations"),
    session: AsyncSession = Depends(get_session),
    lang: str = Depends(get_lang),
) -> Reservation:
    """Клієнт забрав відправлення — продаж (списує on_hand, дохід)."""
    try:
        return await inventory.pick_up(
            session, shop_id=membership.shop_id, reservation_id=reservation_id
        )
    except InventoryError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail(lang)) from exc


@router.post("/reservations/{reservation_id}/not-picked-up", response_model=ReservationOut)
async def not_picked_up_reservation(
    reservation_id: int,
    payload: NotPickedUpIn,
    membership: Membership = require_permission_writable("can_manage_reservations"),
    session: AsyncSession = Depends(get_session),
    lang: str = Depends(get_lang),
) -> Reservation:
    """Клієнт не забрав відправлення — товар повертається на склад, без доходу."""
    try:
        return await inventory.not_picked_up(
            session,
            shop_id=membership.shop_id,
            reservation_id=reservation_id,
            reason=payload.reason,
            comment=payload.comment,
        )
    except InventoryError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail(lang)) from exc


@router.get("/reservations", response_model=list[ReservationOut])
async def list_reservations(
    membership: Membership = require_permission("can_view_inventory"),
    session: AsyncSession = Depends(get_session),
) -> list[Reservation]:
    reservations = (
        await session.scalars(
            select(Reservation)
            .where(
                Reservation.shop_id == membership.shop_id,
                Reservation.status.in_(
                    (ReservationStatus.active, ReservationStatus.shipped)
                ),
            )
            .order_by(Reservation.created_at.desc())
        )
    ).all()
    return list(reservations)
