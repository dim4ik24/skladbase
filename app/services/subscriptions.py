"""
SkladBase — стейт-машина підписки + SubscriptionService.

Стани і дозволені переходи:

    trial ──pay──────────► active
      │                      │
      │ (7 днів вийшло)      │ auto_renew=False -> cancel()
      ▼                      ▼
    expired ◄──────────── canceled ──(period_end)──► expired
      ▲                      │
      └──────pay (re-sub)────┘
                             ▲
    active ──renew_fail──► past_due ──renew_ok──► active
                             │
                             └──(grace вийшов)──► expired

Провайдери:
  * stars  — Telegram Stars, нативне авто-продовження (subscription_period=30д).
             Продовження саме приходить вебхуком is_recurring=True.
  * card   — WayForPay/Fondy/LiqPay: токен картки, авто-списання робимо МИ по крону.
  * crypto — NOWPayments: РАЗОВО. auto_renew завжди False. Тільки нагадування.
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Payment,
    PaymentStatus,
    Plan,
    PromoCode,
    PromoRedemption,
    PromoType,
    Shop,
    SubPeriod,
    SubProvider,
    Subscription,
    SubStatus,
    ensure_aware_utc,
    utcnow,
)

TRIAL_DAYS = 7
PAST_DUE_GRACE_DAYS = 3        # скільки тримаємо доступ після провалу авто-списання
YEAR_DISCOUNT = Decimal("0.90")  # річна підписка -10%

# Дозволені переходи стейт-машини.
_ALLOWED: dict[SubStatus, set[SubStatus]] = {
    SubStatus.trial:    {SubStatus.active, SubStatus.expired, SubStatus.canceled},
    SubStatus.active:   {SubStatus.past_due, SubStatus.canceled, SubStatus.expired},
    SubStatus.past_due: {SubStatus.active, SubStatus.expired, SubStatus.canceled},
    SubStatus.canceled: {SubStatus.active, SubStatus.expired},
    SubStatus.expired:  {SubStatus.active},
}


class SubscriptionError(Exception):
    pass


def _period_delta(period: SubPeriod) -> timedelta:
    return timedelta(days=365) if period == SubPeriod.year else timedelta(days=30)


class SubscriptionService:
    """Уся логіка життєвого циклу підписки. Провайдери сюди не лізуть —
    вони лише викликають record_payment() після успішної оплати."""

    def __init__(self, session: AsyncSession):
        self.s = session

    # --- внутрішній guard переходів ------------------------------------- #
    def _transition(self, sub: Subscription, to: SubStatus) -> None:
        if to == sub.status:
            return
        if to not in _ALLOWED.get(sub.status, set()):
            raise SubscriptionError(f"недозволений перехід {sub.status} -> {to}")
        sub.status = to

    # --- 1. Тріал ------------------------------------------------------- #
    async def start_trial(self, shop: Shop, plan: Plan | None = None) -> Subscription:
        """Викликати при ПЕРШІЙ реальній дії (додав перший товар), не при відкритті."""
        existing = await self.s.scalar(
            select(Subscription).where(Subscription.shop_id == shop.id)
        )
        if existing:
            return existing  # тріал не перевидаємо — анти-абʼюз
        sub = Subscription(
            shop_id=shop.id,
            plan_id=plan.id if plan else None,
            status=SubStatus.trial,
            trial_ends_at=utcnow() + timedelta(days=TRIAL_DAYS),
            current_period_end=utcnow() + timedelta(days=TRIAL_DAYS),
            auto_renew=False,
        )
        self.s.add(sub)
        await self.s.flush()
        return sub

    # --- 2. Успішна оплата (від будь-якого провайдера) ------------------ #
    async def record_payment(
        self,
        sub: Subscription,
        *,
        provider: SubProvider,
        plan: Plan,
        period: SubPeriod,
        amount: Decimal,
        currency: str,
        external_id: str | None,
        is_recurring: bool,
        auto_renew: bool,
        raw: dict | None = None,
    ) -> Payment:
        """Єдина точка входу для всіх провайдерів. Активує/продовжує підписку
        і пише рядок у леджер платежів."""
        now = utcnow()

        # продовжуємо від більшої з дат: 'зараз' або поточний кінець періоду
        current_end = sub.current_period_end and ensure_aware_utc(sub.current_period_end)
        base = current_end if (current_end and current_end > now) else now
        sub.current_period_end = base + _period_delta(period)
        sub.plan_id = plan.id
        sub.provider = provider
        sub.period = period
        sub.auto_renew = auto_renew
        sub.is_comp = False
        sub.renewal_reminder_sent = False
        if external_id:
            sub.external_sub_id = external_id
        self._transition(sub, SubStatus.active)

        payment = Payment(
            shop_id=sub.shop_id,
            subscription_id=sub.id,
            provider=provider,
            status=PaymentStatus.succeeded,
            amount=amount,
            currency=currency,
            is_recurring=is_recurring,
            external_id=external_id,
            raw=raw or {},
        )
        self.s.add(payment)
        await self.s.flush()
        return payment

    # --- 3. Авто-списання не пройшло ------------------------------------ #
    async def mark_past_due(self, sub: Subscription) -> None:
        """Stars/картка: продовження не вдалось. Даємо грейс-період."""
        self._transition(sub, SubStatus.past_due)
        sub.current_period_end = utcnow() + timedelta(days=PAST_DUE_GRACE_DAYS)
        await self.s.flush()

    # --- 4. Скасування (auto_renew off, доступ до кінця періоду) -------- #
    async def cancel(self, sub: Subscription) -> None:
        self._transition(sub, SubStatus.canceled)
        sub.auto_renew = False
        sub.canceled_at = utcnow()
        await self.s.flush()
        # для Stars додатково смикнути editUserStarSubscription (див. billing/providers.py)

    # --- 5. Протермінування (з крона) ----------------------------------- #
    async def expire(self, sub: Subscription) -> None:
        self._transition(sub, SubStatus.expired)
        sub.auto_renew = False
        await self.s.flush()

    # --- 6. Промокод ---------------------------------------------------- #
    async def redeem_promo(self, shop: Shop, sub: Subscription, code: str) -> Subscription:
        """Кейс 'магазин рекламує -> 2 місяці безкоштовно'."""
        promo = await self.s.scalar(
            select(PromoCode).where(PromoCode.code == code.strip().upper())
        )
        if not promo or not promo.is_redeemable:
            raise SubscriptionError("промокод недійсний або вичерпаний")

        already = await self.s.scalar(
            select(PromoRedemption).where(
                PromoRedemption.promo_code_id == promo.id,
                PromoRedemption.shop_id == shop.id,
            )
        )
        if already:
            raise SubscriptionError("промокод уже активовано цим магазином")

        if promo.type == PromoType.free_period:
            now = utcnow()
            current_end = sub.current_period_end and ensure_aware_utc(sub.current_period_end)
            base = current_end if (current_end and current_end > now) else now
            sub.current_period_end = base + timedelta(days=promo.value)
            sub.is_comp = True
            sub.auto_renew = False
            self._transition(sub, SubStatus.active)
        # promo.type == percent застосовується на етапі формування інвойсу, не тут

        promo.used_count += 1
        self.s.add(PromoRedemption(promo_code_id=promo.id, shop_id=shop.id))
        await self.s.flush()
        return sub

    # --- helper: ціна з урахуванням періоду ----------------------------- #
    @staticmethod
    def effective_price_uah(plan: Plan, period: SubPeriod) -> Decimal:
        if period == SubPeriod.year:
            # річна = 12 міс * (-10%)
            return (plan.price_uah * 12 * YEAR_DISCOUNT).quantize(Decimal("0.01"))
        return plan.price_uah
