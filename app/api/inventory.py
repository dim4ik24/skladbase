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

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.catalog import VariantOut
from app.db import get_session
from app.deps import require_member, require_writable
from app.models import Membership, Reservation, ReservationSource, ReservationStatus, Variant
from app.services import inventory
from app.services.inventory import InventoryError

router = APIRouter(prefix="/api", tags=["inventory"])


# --------------------------------------------------------------------------- #
#  Схеми
# --------------------------------------------------------------------------- #
class RestockIn(BaseModel):
    qty: int


class AdjustIn(BaseModel):
    new_on_hand: int
    reason: str | None = None


class ReserveIn(BaseModel):
    qty: int
    customer_note: str | None = None
    expires_at: datetime | None = None


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
    expires_at: datetime | None
    created_at: datetime
    released_at: datetime | None


# --------------------------------------------------------------------------- #
#  Варіанти: поповнення / корекція / ручний резерв
# --------------------------------------------------------------------------- #
@router.post("/variants/{variant_id}/restock", response_model=VariantOut)
async def restock_variant(
    variant_id: int,
    payload: RestockIn,
    membership: Membership = Depends(require_writable),
    session: AsyncSession = Depends(get_session),
) -> Variant:
    try:
        return await inventory.restock(
            session, shop_id=membership.shop_id, variant_id=variant_id, qty=payload.qty
        )
    except InventoryError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.post("/variants/{variant_id}/adjust", response_model=VariantOut)
async def adjust_variant(
    variant_id: int,
    payload: AdjustIn,
    membership: Membership = Depends(require_writable),
    session: AsyncSession = Depends(get_session),
) -> Variant:
    try:
        return await inventory.adjust(
            session,
            shop_id=membership.shop_id,
            variant_id=variant_id,
            new_on_hand=payload.new_on_hand,
            reason=payload.reason,
        )
    except InventoryError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.post("/variants/{variant_id}/reserve", response_model=ReservationOut)
async def reserve_variant(
    variant_id: int,
    payload: ReserveIn,
    membership: Membership = Depends(require_writable),
    session: AsyncSession = Depends(get_session),
) -> Reservation:
    """Ручний резерв «відклади товар» — менеджер тримає одиницю для клієнта
    поза замовленням із сайту (`ReservationSource.manual`)."""
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
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


# --------------------------------------------------------------------------- #
#  Резерви: зняти / продати
# --------------------------------------------------------------------------- #
@router.post("/reservations/{reservation_id}/release", response_model=ReservationOut)
async def release_reservation(
    reservation_id: int,
    membership: Membership = Depends(require_writable),
    session: AsyncSession = Depends(get_session),
) -> Reservation:
    try:
        return await inventory.release(
            session, shop_id=membership.shop_id, reservation_id=reservation_id
        )
    except InventoryError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.post("/reservations/{reservation_id}/fulfill", response_model=ReservationOut)
async def fulfill_reservation(
    reservation_id: int,
    membership: Membership = Depends(require_writable),
    session: AsyncSession = Depends(get_session),
) -> Reservation:
    """Ручний продаж раніше відкладеного резерву (списує on_hand)."""
    try:
        return await inventory.fulfill(
            session, shop_id=membership.shop_id, reservation_id=reservation_id
        )
    except InventoryError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.get("/reservations", response_model=list[ReservationOut])
async def list_active_reservations(
    membership: Membership = Depends(require_member),
    session: AsyncSession = Depends(get_session),
) -> list[Reservation]:
    reservations = (
        await session.scalars(
            select(Reservation)
            .where(
                Reservation.shop_id == membership.shop_id,
                Reservation.status == ReservationStatus.active,
            )
            .order_by(Reservation.created_at.desc())
        )
    ).all()
    return list(reservations)
