"""
SkladBase — aiogram Dispatcher: обробка Telegram Stars платежів (Стадія 5a).

Підписку активуємо ТІЛЬКИ тут, з вебхука Telegram, ніколи з відповіді
Mini App (CLAUDE.md, інваріант №2: клієнт може підробити «я оплатив»,
вебхук з валідним підписом — ні). `pre_checkout_query` підтверджуємо одразу:
це підписка на сервіс, не складський товар, додаткової перевірки наявності
тут не потрібно.

`session` сюди не Depends-иться (aiogram — не FastAPI): викликач
(`app/api/telegram.py`) передає її через `dp.feed_update(bot, update,
session=session)`, а aiogram підставляє в хендлер за збігом імені параметра.
"""
from __future__ import annotations

import logging

from aiogram import Dispatcher, F
from aiogram.types import Message, PreCheckoutQuery
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.billing.providers import StarsProvider
from app.models import Membership, Plan, SubPeriod, SubProvider, Subscription
from app.services.subscriptions import SubscriptionService

logger = logging.getLogger(__name__)

dp = Dispatcher()


@dp.pre_checkout_query()
async def on_pre_checkout_query(pre_checkout_query: PreCheckoutQuery) -> None:
    await pre_checkout_query.answer(ok=True)


async def _resolve_payer_membership(
    session: AsyncSession, *, payer_tg_id: int, shop_id: int | None
) -> Membership | None:
    """Знаходить магазин, якому належить ця оплата.

    `shop_id` з payload інвойсу — єдине детерміноване джерело: власник може
    мати кілька магазинів, тож вгадувати shop за tg_id платника небезпечно
    (зарахує не той магазин). Якщо shop_id присутній, додатково перевіряємо,
    що платник дійсно член саме цього магазину — захист від підробленого
    payload."""
    if shop_id is not None:
        membership = await session.scalar(
            select(Membership).where(
                Membership.tg_id == payer_tg_id, Membership.shop_id == shop_id
            )
        )
        if membership is None:
            logger.warning(
                "tg_id=%s не є членом shop_id=%s (з payload інвойсу) — ігноруємо платіж",
                payer_tg_id,
                shop_id,
            )
        return membership

    # Фолбек для інвойсів без shop_id у payload (старі/сторонні посилання):
    # менш надійно, бере перший-ліпший membership платника.
    membership = await session.scalar(
        select(Membership).where(Membership.tg_id == payer_tg_id)
    )
    if membership is None:
        logger.warning("successful_payment від невідомого tg_id=%s — ігноруємо", payer_tg_id)
    return membership


@dp.message(F.successful_payment)
async def on_successful_payment(message: Message, session: AsyncSession) -> None:
    sp = message.successful_payment
    if sp is None or message.from_user is None:
        return

    result = StarsProvider.parse_successful_payment(sp, sp.invoice_payload)

    membership = await _resolve_payer_membership(
        session, payer_tg_id=message.from_user.id, shop_id=result.shop_id
    )
    if membership is None:
        return

    subscription = await session.scalar(
        select(Subscription).where(Subscription.shop_id == membership.shop_id)
    )
    if subscription is None:
        logger.warning("shop %s: немає Subscription для оплати — ігноруємо", membership.shop_id)
        return

    plan = await session.scalar(select(Plan).where(Plan.code == result.plan_code))
    if plan is None:
        logger.warning("план '%s' не знайдено — ігноруємо платіж", result.plan_code)
        return

    period = SubPeriod.year if result.period == "year" else SubPeriod.month
    await SubscriptionService(session).record_payment(
        subscription,
        provider=SubProvider.stars,
        plan=plan,
        period=period,
        amount=result.amount,
        currency=result.currency,
        external_id=result.external_id,
        is_recurring=result.is_recurring,
        auto_renew=result.auto_renew,
        raw=result.raw,
    )
    await session.commit()
