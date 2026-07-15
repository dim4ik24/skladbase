"""
SkladBase — REST API білінгу (Стадії 5a/5b): тарифи, чекаути (Stars/картка/
крипта), промокоди, скасування.

Підписку активуємо ТІЛЬКИ з вебхука провайдера (Telegram — `app/bot/dispatcher.py`;
WayForPay/NOWPayments — `app/api/payment_webhooks.py`), а не звідси
(CLAUDE.md, інваріант №2) — ці ендпоінти лише готують інвойс/форму оплати або
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

from app.billing.providers import NowPaymentsProvider, StarsProvider, WayForPayProvider
from app.billing.refs import build_ref
from app.config import settings
from app.db import get_session
from app.deps import require_permission
from app.i18n import get_lang, msg
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


class CardCheckoutIn(BaseModel):
    plan_code: str
    period: SubPeriod = SubPeriod.month


class CardCheckoutOut(BaseModel):
    form: dict


class CryptoCheckoutIn(BaseModel):
    plan_code: str
    period: SubPeriod = SubPeriod.month


class CryptoCheckoutOut(BaseModel):
    payment: dict


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


async def _get_subscription(session: AsyncSession, shop_id: int, lang: str) -> Subscription:
    subscription = await session.scalar(
        select(Subscription).where(Subscription.shop_id == shop_id)
    )
    if subscription is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=msg("billing.subscription_not_found", lang),
        )
    return subscription


async def _get_active_plan(session: AsyncSession, plan_code: str, lang: str) -> Plan:
    plan = await session.scalar(
        select(Plan).where(Plan.code == plan_code, Plan.is_active.is_(True))
    )
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=msg("billing.plan_not_found", lang)
        )
    return plan


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
    membership: Membership = require_permission("can_manage_billing"),
    session: AsyncSession = Depends(get_session),
    lang: str = Depends(get_lang),
) -> StarsCheckoutOut:
    plan = await _get_active_plan(session, payload.plan_code, lang)

    if plan.price_stars <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=msg("billing.free_plan_no_payment", lang),
        )

    bot = Bot(token=settings.BOT_TOKEN)
    try:
        invoice_link = await StarsProvider(bot).create_checkout(
            shop_id=membership.shop_id,
            plan_code=plan.code,
            price_stars=plan.price_stars,
            title=plan.name,
        )
    finally:
        await bot.session.close()

    return StarsCheckoutOut(invoice_link=invoice_link)


# --------------------------------------------------------------------------- #
#  Картка (WayForPay, з рекурентним токеном)                                  #
# --------------------------------------------------------------------------- #
@router.post("/checkout/card", response_model=CardCheckoutOut)
async def create_card_checkout(
    payload: CardCheckoutIn,
    membership: Membership = require_permission("can_manage_billing"),
    session: AsyncSession = Depends(get_session),
    lang: str = Depends(get_lang),
) -> CardCheckoutOut:
    plan = await _get_active_plan(session, payload.plan_code, lang)
    amount = SubscriptionService.effective_price_uah(plan, payload.period)
    order_ref = build_ref(membership.shop_id, plan.code, payload.period.value)

    provider = WayForPayProvider(settings.WFP_MERCHANT, settings.WFP_SECRET, settings.WFP_DOMAIN)
    form = await provider.create_checkout(
        order_ref=order_ref,
        amount=amount,
        plan_code=plan.code,
        period=payload.period.value,
        product=plan.name,
    )
    return CardCheckoutOut(form=form)


# --------------------------------------------------------------------------- #
#  Крипта (NOWPayments, разово)                                               #
# --------------------------------------------------------------------------- #
@router.post("/checkout/crypto", response_model=CryptoCheckoutOut)
async def create_crypto_checkout(
    payload: CryptoCheckoutIn,
    membership: Membership = require_permission("can_manage_billing"),
    session: AsyncSession = Depends(get_session),
    lang: str = Depends(get_lang),
) -> CryptoCheckoutOut:
    plan = await _get_active_plan(session, payload.plan_code, lang)
    amount_uah = SubscriptionService.effective_price_uah(plan, payload.period)
    amount_usd = (amount_uah / settings.UAH_USD_RATE).quantize(Decimal("0.01"))
    order_id = build_ref(membership.shop_id, plan.code, payload.period.value)

    provider = NowPaymentsProvider(settings.NOWPAYMENTS_API_KEY, settings.NOWPAYMENTS_IPN_SECRET)
    payment = await provider.create_checkout(
        order_id=order_id,
        amount_usd=amount_usd,
        plan_code=plan.code,
        period=payload.period.value,
    )
    return CryptoCheckoutOut(payment=payment)


# --------------------------------------------------------------------------- #
#  Промокод
# --------------------------------------------------------------------------- #
@router.post("/promo", response_model=SubscriptionOut)
async def redeem_promo(
    payload: PromoIn,
    membership: Membership = require_permission("can_manage_billing"),
    session: AsyncSession = Depends(get_session),
    lang: str = Depends(get_lang),
) -> Subscription:
    shop = await session.get(Shop, membership.shop_id)
    if shop is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=msg("billing.shop_not_found", lang)
        )
    subscription = await _get_subscription(session, membership.shop_id, lang)

    try:
        await SubscriptionService(session).redeem_promo(shop, subscription, payload.code)
    except SubscriptionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail(lang)) from exc

    await session.commit()
    await session.refresh(subscription)
    return subscription


# --------------------------------------------------------------------------- #
#  Скасування
# --------------------------------------------------------------------------- #
@router.post("/cancel", response_model=SubscriptionOut)
async def cancel_subscription(
    membership: Membership = require_permission("can_manage_billing"),
    session: AsyncSession = Depends(get_session),
    lang: str = Depends(get_lang),
) -> Subscription:
    subscription = await _get_subscription(session, membership.shop_id, lang)

    if subscription.provider == SubProvider.stars and subscription.external_sub_id:
        bot = Bot(token=settings.BOT_TOKEN)
        try:
            await StarsProvider(bot).cancel(membership.tg_id, subscription.external_sub_id)
        finally:
            await bot.session.close()

    try:
        await SubscriptionService(session).cancel(subscription)
    except SubscriptionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.detail(lang)) from exc

    await session.commit()
    await session.refresh(subscription)
    return subscription
