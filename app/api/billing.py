"""
SkladBase — REST API білінгу (Стадія 5a): тарифи, Stars checkout, промокоди,
скасування.

Підписку активуємо ТІЛЬКИ з вебхука Telegram (`app/bot/dispatcher.py`), а не
звідси (CLAUDE.md, інваріант №2) — ці ендпоінти лише готують інвойс або
виконують дії, явно дозволені стейт-машиною `SubscriptionService`, і ніколи
не виставляють `status=active` напряму.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from aiogram import Bot
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.billing.providers import StarsProvider
from app.config import settings
from app.db import get_session
from app.deps import require_member, require_owner
from app.models import Membership, Plan, Shop, SubPeriod, SubProvider, Subscription, SubStatus
from app.services.subscriptions import SubscriptionError, SubscriptionService

router = APIRouter(prefix="/api/billing", tags=["billing"])


# --------------------------------------------------------------------------- #
#  Схеми
# --------------------------------------------------------------------------- #
class PlanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    name: str
    period: SubPeriod
    price_uah: Decimal
    price_stars: int
    limits: dict


class StarsCheckoutIn(BaseModel):
    plan_code: str


class StarsCheckoutOut(BaseModel):
    invoice_link: str


class PromoIn(BaseModel):
    code: str


class SubscriptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    status: SubStatus
    provider: SubProvider | None
    period: SubPeriod
    current_period_end: datetime | None
    auto_renew: bool
    is_comp: bool


async def _get_subscription(session: AsyncSession, shop_id: int) -> Subscription:
    subscription = await session.scalar(
        select(Subscription).where(Subscription.shop_id == shop_id)
    )
    if subscription is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Підписку не знайдено")
    return subscription


# --------------------------------------------------------------------------- #
#  Тарифи
# --------------------------------------------------------------------------- #
@router.get("/plans", response_model=list[PlanOut])
async def list_plans(session: AsyncSession = Depends(get_session)) -> list[Plan]:
    plans = (
        await session.scalars(
            select(Plan).where(Plan.is_active.is_(True)).order_by(Plan.id)
        )
    ).all()
    return list(plans)


# --------------------------------------------------------------------------- #
#  Stars checkout
# --------------------------------------------------------------------------- #
@router.post("/checkout/stars", response_model=StarsCheckoutOut)
async def create_stars_checkout(
    payload: StarsCheckoutIn,
    membership: Membership = Depends(require_member),
    session: AsyncSession = Depends(get_session),
) -> StarsCheckoutOut:
    plan = await session.scalar(
        select(Plan).where(Plan.code == payload.plan_code, Plan.is_active.is_(True))
    )
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="План не знайдено")

    bot = Bot(token=settings.BOT_TOKEN)
    try:
        invoice_link = await StarsProvider(bot).create_checkout(
            plan_code=plan.code, price_stars=plan.price_stars, title=plan.name
        )
    finally:
        await bot.session.close()

    return StarsCheckoutOut(invoice_link=invoice_link)


# --------------------------------------------------------------------------- #
#  Промокод
# --------------------------------------------------------------------------- #
@router.post("/promo", response_model=SubscriptionOut)
async def redeem_promo(
    payload: PromoIn,
    membership: Membership = Depends(require_member),
    session: AsyncSession = Depends(get_session),
) -> Subscription:
    shop = await session.get(Shop, membership.shop_id)
    if shop is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Магазин не знайдено")
    subscription = await _get_subscription(session, membership.shop_id)

    try:
        await SubscriptionService(session).redeem_promo(shop, subscription, payload.code)
    except SubscriptionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    await session.commit()
    await session.refresh(subscription)
    return subscription


# --------------------------------------------------------------------------- #
#  Скасування
# --------------------------------------------------------------------------- #
@router.post("/cancel", response_model=SubscriptionOut)
async def cancel_subscription(
    membership: Membership = Depends(require_owner),
    session: AsyncSession = Depends(get_session),
) -> Subscription:
    subscription = await _get_subscription(session, membership.shop_id)

    if subscription.provider == SubProvider.stars and subscription.external_sub_id:
        bot = Bot(token=settings.BOT_TOKEN)
        try:
            await StarsProvider(bot).cancel(membership.tg_id, subscription.external_sub_id)
        finally:
            await bot.session.close()

    try:
        await SubscriptionService(session).cancel(subscription)
    except SubscriptionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    await session.commit()
    await session.refresh(subscription)
    return subscription
