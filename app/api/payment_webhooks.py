"""
SkladBase — вхідні вебхуки платіжних провайдерів (Стадія 5b): WayForPay
(картка) і NOWPayments (крипта).

Підписку активуємо ТІЛЬКИ тут (CLAUDE.md, інваріант №2). Підпис провайдера —
межа довіри і перевіряється ПЕРШИМ; shop_id резолвиться з orderReference/
order_id (`app/billing/refs.py`), а НЕ з тіла запиту напряму (інваріант №1).
`record_payment` викликається лише з цих хендлерів, ніколи з checkout-
ендпоінтів (`app/api/billing.py`).
"""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.billing.providers import NowPaymentsProvider, WayForPayProvider
from app.billing.refs import ParsedRef, RefError, parse_ref
from app.config import settings
from app.db import get_session
from app.models import Plan, SubPeriod, SubProvider, Subscription
from app.services.subscriptions import SubscriptionService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhook", tags=["payment-webhooks"])


async def _resolve_from_ref(
    session: AsyncSession, ref: str
) -> tuple[Subscription, Plan, str] | None:
    """`(subscription, plan, period)` за ref, або None — якщо ref/магазин/
    план не резолвляться (вебхук просто ігнорується, без 500)."""
    try:
        parsed: ParsedRef = parse_ref(ref)
    except RefError:
        logger.warning("невалідний ref у вебхуку: %r", ref)
        return None

    subscription = await session.scalar(
        select(Subscription).where(Subscription.shop_id == parsed.shop_id)
    )
    if subscription is None:
        logger.warning("shop %s (з ref) не має Subscription — ігноруємо", parsed.shop_id)
        return None

    plan = await session.scalar(select(Plan).where(Plan.code == parsed.plan_code))
    if plan is None:
        logger.warning("план '%s' (з ref) не знайдено — ігноруємо", parsed.plan_code)
        return None

    return subscription, plan, parsed.period


def _ignored(detail: str) -> JSONResponse:
    logger.warning(detail)
    return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"ok": False})


# --------------------------------------------------------------------------- #
#  WayForPay — картка з рекурентним токеном                                   #
# --------------------------------------------------------------------------- #
@router.post("/wayforpay")
async def wayforpay_webhook(
    request: Request, session: AsyncSession = Depends(get_session)
) -> JSONResponse:
    data = await request.json()

    provider = WayForPayProvider(settings.WFP_MERCHANT, settings.WFP_SECRET, settings.WFP_DOMAIN)
    try:
        signature_valid = provider.verify_callback(data)
    except KeyError:
        return _ignored("WayForPay callback з відсутніми полями — ігноруємо")
    if not signature_valid:
        return _ignored("WayForPay callback з невалідним підписом — ігноруємо")

    resolved = await _resolve_from_ref(session, data.get("orderReference", ""))
    if resolved is None:
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"ok": False})
    subscription, plan, period = resolved

    result = provider.parse_callback(data, plan_code=plan.code, period=period)

    await SubscriptionService(session).record_payment(
        subscription,
        provider=SubProvider.card,
        plan=plan,
        period=SubPeriod.year if result.period == "year" else SubPeriod.month,
        amount=result.amount,
        currency=result.currency,
        external_id=result.external_id,
        is_recurring=result.is_recurring,
        auto_renew=result.auto_renew,
        raw=result.raw,
    )
    await session.commit()

    return JSONResponse(content={"ok": True})


# --------------------------------------------------------------------------- #
#  NOWPayments — крипта, разово                                               #
# --------------------------------------------------------------------------- #
@router.post("/nowpayments")
async def nowpayments_webhook(
    request: Request, session: AsyncSession = Depends(get_session)
) -> JSONResponse:
    raw_body = await request.body()
    signature = request.headers.get("x-nowpayments-sig", "")

    provider = NowPaymentsProvider(settings.NOWPAYMENTS_API_KEY, settings.NOWPAYMENTS_IPN_SECRET)
    try:
        signature_valid = provider.verify_ipn(raw_body, signature)
    except (json.JSONDecodeError, KeyError):
        return _ignored("NOWPayments IPN з нерозбірливим тілом — ігноруємо")
    if not signature_valid:
        return _ignored("NOWPayments IPN з невалідним підписом — ігноруємо")

    data = json.loads(raw_body)

    resolved = await _resolve_from_ref(session, data.get("order_id", ""))
    if resolved is None:
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"ok": False})
    subscription, plan, period = resolved

    result = provider.parse_ipn(data, plan_code=plan.code, period=period)
    if result is None:
        # Валідний підпис, але платіж ще не finished/confirmed — не помилка,
        # просто рано активувати. Підтверджуємо отримання, чекаємо наступний IPN.
        return JSONResponse(content={"ok": True})

    await SubscriptionService(session).record_payment(
        subscription,
        provider=SubProvider.crypto,
        plan=plan,
        period=SubPeriod.year if result.period == "year" else SubPeriod.month,
        amount=result.amount,
        currency=result.currency,
        external_id=result.external_id,
        is_recurring=result.is_recurring,
        auto_renew=result.auto_renew,
        raw=result.raw,
    )
    await session.commit()

    return JSONResponse(content={"ok": True})
