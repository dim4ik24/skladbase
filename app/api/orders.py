"""
SkladBase — REST API замовлень (Стадія 4a).

`POST /api/website/orders` — server-to-server від сайту, авторизація через
`X-API-Key` (НЕ initData — це не дія користувача в Telegram).

Решта — під `require_member`: підтвердження/скасування замовлень це робота
менеджера, не лише власника (CLAUDE.md: "manager — резерв і замовлення, без
фінансів").
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.bot.notify import notifier
from app.db import get_session
from app.deps import require_api_key, require_member
from app.models import Membership, Order, OrderSource, OrderStatus, Shop
from app.services import orders as orders_service

router = APIRouter(prefix="/api", tags=["orders"])


# --------------------------------------------------------------------------- #
#  Схеми
# --------------------------------------------------------------------------- #
class WebsiteOrderItemIn(BaseModel):
    variant_id: int
    qty: int


class WebsiteOrderIn(BaseModel):
    items: list[WebsiteOrderItemIn]
    idempotency_key: str
    customer_name: str | None = None
    customer_contact: str | None = None


class OrderItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    variant_id: int
    qty: int
    price_at_order: Decimal


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source: OrderSource
    status: OrderStatus
    customer_name: str | None
    customer_contact: str | None
    total: Decimal
    created_at: datetime
    items: list[OrderItemOut]


# --------------------------------------------------------------------------- #
#  Сайт (server-to-server, X-API-Key)
# --------------------------------------------------------------------------- #
@router.post("/website/orders", response_model=OrderOut)
async def submit_website_order(
    payload: WebsiteOrderIn,
    response: Response,
    shop: Shop = Depends(require_api_key),
    session: AsyncSession = Depends(get_session),
) -> Order:
    service_payload = orders_service.OrderInput(
        items=[
            orders_service.OrderItemInput(variant_id=item.variant_id, qty=item.qty)
            for item in payload.items
        ],
        idempotency_key=payload.idempotency_key,
        customer_name=payload.customer_name,
        customer_contact=payload.customer_contact,
    )
    try:
        order, created = await orders_service.create_website_order(
            session, shop_id=shop.id, payload=service_payload
        )
    except orders_service.OrderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK

    if created:
        items_text = "\n".join(f"• variant #{i.variant_id} × {i.qty}" for i in payload.items)
        await notifier(shop.owner_tg_id, f"Нове замовлення з сайту #{order.id}\n{items_text}")

    return order


# --------------------------------------------------------------------------- #
#  Власник/менеджер (initData)
# --------------------------------------------------------------------------- #
@router.get("/orders", response_model=list[OrderOut])
async def list_orders(
    membership: Membership = Depends(require_member),
    session: AsyncSession = Depends(get_session),
) -> list[Order]:
    orders = (
        await session.scalars(
            select(Order)
            .options(selectinload(Order.items))
            .where(Order.shop_id == membership.shop_id)
            .order_by(Order.created_at.desc())
        )
    ).all()
    return list(orders)


@router.post("/orders/{order_id}/confirm", response_model=OrderOut)
async def confirm_order(
    order_id: int,
    membership: Membership = Depends(require_member),
    session: AsyncSession = Depends(get_session),
) -> Order:
    try:
        return await orders_service.confirm_order(
            session, shop_id=membership.shop_id, order_id=order_id
        )
    except orders_service.OrderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.post("/orders/{order_id}/cancel", response_model=OrderOut)
async def cancel_order(
    order_id: int,
    membership: Membership = Depends(require_member),
    session: AsyncSession = Depends(get_session),
) -> Order:
    try:
        return await orders_service.cancel_order(
            session, shop_id=membership.shop_id, order_id=order_id
        )
    except orders_service.OrderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
