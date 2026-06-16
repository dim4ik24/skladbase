"""
SkladBase — щоденні/щохвилинні крон-задачі.

Запуск: APScheduler або окремий воркер. Усі функції приймають AsyncSession.
Рекомендований розклад:
  every 1h  -> release_expired_reservations
  every 1h  -> low_stock_scan
  every 6h  -> charge_due_card_subscriptions
  daily     -> expire_subscriptions, send_renewal_reminders

`notify` — async callable(tg_id: int, text: str) -> None (обгортка над bot.send_message).
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    MovementType,
    Plan,
    Product,
    Reservation,
    ReservationStatus,
    Shop,
    StockMovement,
    SubProvider,
    Subscription,
    SubStatus,
    Variant,
    utcnow,
)
from app.services.subscriptions import SubscriptionService

Notifier = Callable[[int, str], Awaitable[None]]


# --------------------------------------------------------------------------- #
#  Підписки                                                                   #
# --------------------------------------------------------------------------- #
async def expire_subscriptions(session: AsyncSession, notify: Notifier) -> int:
    """Перевести у read-only ті, що закінчились і не мають авто-продовження.

    Stars/картку з auto_renew=True НЕ чіпаємо — за них відповідає вебхук
    провайдера (успіх -> record_payment, провал -> mark_past_due)."""
    now = utcnow()
    svc = SubscriptionService(session)

    expired_candidates = (await session.scalars(
        select(Subscription).where(
            Subscription.current_period_end < now,
            (
                Subscription.status.in_([SubStatus.trial, SubStatus.canceled, SubStatus.past_due])
            ) | (
                (Subscription.status == SubStatus.active) & (Subscription.auto_renew.is_(False))
            ),
        )
    )).all()

    for sub in expired_candidates:
        await svc.expire(sub)
        shop = await session.get(Shop, sub.shop_id)
        await notify(
            shop.owner_tg_id,  # type: ignore[union-attr]
            "⏳ Підписку призупинено. Дані збережено — оформи підписку, щоб редагувати.",
        )
    await session.commit()
    return len(expired_candidates)


async def send_renewal_reminders(session: AsyncSession, notify: Notifier) -> int:
    """Нагадати тим, у кого нема авто-продовження (крипта/разові) за 3 дні до кінця."""
    now = utcnow()
    subs = (await session.scalars(
        select(Subscription).where(
            Subscription.status.in_([SubStatus.active, SubStatus.trial]),
            Subscription.auto_renew.is_(False),
            Subscription.renewal_reminder_sent.is_(False),
            Subscription.current_period_end < now + timedelta(days=3),
            Subscription.current_period_end > now,
        )
    )).all()
    for sub in subs:
        days = max((sub.current_period_end - now).days, 0)  # type: ignore[operator]
        shop = await session.get(Shop, sub.shop_id)
        await notify(shop.owner_tg_id, f"🔔 Підписка закінчується через {days} дн. Продовжити можна в меню.")  # type: ignore[union-attr]
        sub.renewal_reminder_sent = True
    await session.commit()
    return len(subs)


async def charge_due_card_subscriptions(
    session: AsyncSession, wfp_provider: object, notify: Notifier
) -> int:
    """Авто-списання карткових підписок (WayForPay не списує сам — це наша робота)."""
    now = utcnow()
    svc = SubscriptionService(session)
    subs = (await session.scalars(
        select(Subscription).where(
            Subscription.provider == SubProvider.card,
            Subscription.auto_renew.is_(True),
            Subscription.status.in_([SubStatus.active, SubStatus.past_due]),
            Subscription.current_period_end < now + timedelta(hours=12),
        )
    )).all()

    charged = 0
    for sub in subs:
        plan = await session.get(Plan, sub.plan_id) if sub.plan_id else None
        if not plan:
            continue
        amount = SubscriptionService.effective_price_uah(plan, sub.period)
        order_ref = f"sb-{sub.shop_id}-{int(now.timestamp())}"
        result = await wfp_provider.charge_recurring(  # type: ignore[attr-defined]
            rec_token=sub.external_sub_id, order_ref=order_ref, amount=amount
        )
        if result.get("transactionStatus") == "Approved":
            await svc.record_payment(
                sub,
                provider=SubProvider.card,
                plan=plan,
                period=sub.period,
                amount=amount,
                currency="UAH",
                external_id=sub.external_sub_id,
                is_recurring=True,
                auto_renew=True,
                raw=result,
            )
            charged += 1
        else:
            await svc.mark_past_due(sub)
            shop = await session.get(Shop, sub.shop_id)
            await notify(shop.owner_tg_id, "⚠️ Не вдалось списати оплату з картки. Онови картку протягом 3 днів.")  # type: ignore[union-attr]
    await session.commit()
    return charged


# --------------------------------------------------------------------------- #
#  Склад                                                                       #
# --------------------------------------------------------------------------- #
async def release_expired_reservations(session: AsyncSession) -> int:
    """Зняти мертві резерви: повернути reserved у available (фіча 8)."""
    now = utcnow()
    resvs = (await session.scalars(
        select(Reservation).where(
            Reservation.status == ReservationStatus.active,
            Reservation.expires_at.is_not(None),
            Reservation.expires_at < now,
        )
    )).all()
    for r in resvs:
        variant = await session.get(Variant, r.variant_id)
        if variant:
            variant.reserved = max(0, variant.reserved - r.qty)
            session.add(StockMovement(
                shop_id=r.shop_id, variant_id=r.variant_id,
                type=MovementType.release, delta=0,
            ))
        r.status = ReservationStatus.released
        r.released_at = now
    await session.commit()
    return len(resvs)


async def low_stock_scan(session: AsyncSession, notify: Notifier) -> int:
    """Пуш 'товар закінчується' — один раз при перетині порога (дебаунс).

    Скидання low_stock_notified_at при поповненні робиться в логіці restock."""
    variants = (await session.scalars(
        select(Variant).where(
            (Variant.on_hand - Variant.reserved) <= Variant.low_stock_threshold,
            Variant.low_stock_notified_at.is_(None),
        )
    )).all()
    for v in variants:
        avail = v.on_hand - v.reserved
        product = await session.get(Product, v.product_id)
        shop = await session.get(Shop, v.shop_id)
        name = product.name if product else f"Товар #{v.product_id}"
        await notify(shop.owner_tg_id, f"📦 «{name}» закінчується — залишилось {avail} {_units(avail)}.")  # type: ignore[union-attr]
        v.low_stock_notified_at = utcnow()
    await session.commit()
    return len(variants)


def _units(n: int) -> str:
    """Українська плюралізація: 1 одиниця / 2 одиниці / 5 одиниць."""
    if n % 10 == 1 and n % 100 != 11:
        return "одиниця"
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return "одиниці"
    return "одиниць"
