"""
SkladBase — щоденні/щохвилинні крон-задачі.

Запуск: APScheduler або окремий воркер. Усі функції приймають AsyncSession.
Рекомендований розклад:
  every 10m -> np_tracking
  every 1h  -> release_expired_reservations
  every 1h  -> low_stock_scan
  every 6h  -> charge_due_card_subscriptions
  daily     -> expire_subscriptions, send_renewal_reminders

`notify` — async callable(tg_id: int, text: str) -> None (обгортка над bot.send_message).
"""
from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import timedelta
from decimal import Decimal

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
    ensure_aware_utc,
    utcnow,
)
from app.security.crypto import CryptoError, decrypt
from app.services import inventory
from app.services.inventory import InventoryError
from app.services.novaposhta import PICKED_CODES, RETURNED_CODES, NovaPoshtaError
from app.services.subscriptions import SubscriptionService

logger = logging.getLogger(__name__)

Notifier = Callable[[int, str], Awaitable[None]]
NpTrackFn = Callable[[str, list[str]], Awaitable[list[dict]]]


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
        period_end = ensure_aware_utc(sub.current_period_end)  # type: ignore[arg-type]
        days = max((period_end - now).days, 0)
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
                transaction_id=order_ref,  # унікальний на цю спробу списання
                recurring_token=sub.external_sub_id,  # recToken — стабільний між списаннями
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


async def _np_display_name(session: AsyncSession, variant_id: int) -> tuple[str, Variant | None]:
    variant = await session.get(Variant, variant_id)
    if variant is None:
        return f"Варіант #{variant_id}", None
    product = await session.get(Product, variant.product_id)
    name = product.name if product else f"Варіант #{variant_id}"
    return name, variant


def _extract_np_recipient(result: dict) -> str | None:
    """"ПІБ · Місто, відділення" з відповіді getStatusDocuments. Зберігаємо
    лише коли ВСІ три поля непорожні — часткові дані гірші за їх відсутність."""
    name = result.get("RecipientFullName")
    city = result.get("CityRecipient")
    warehouse = result.get("WarehouseRecipient")
    if not (name and city and warehouse):
        return None
    return f"{name} · {city}, {warehouse}"


async def np_tracking(session: AsyncSession, notify: Notifier, track: NpTrackFn) -> int:
    """Фіча B1: пуш-трекінг shipped-резервів через Нова Пошта.

    Для кожного магазину з підключеним ключем — усі shipped-резерви з ttn
    батчем у track(); PICKED_CODES -> pick_up (дохід, як і ручний "Забрав");
    RETURNED_CODES -> not_picked_up(reason="refused") (товар назад на склад,
    без доходу); інакший код -> зберігаємо текст статусу в np_status (UI B2).

    Стійкість: поганий ключ чи мережевий збій одного магазину не валить цикл
    (try/except на магазин); резерв, уже оброблений вручну паралельно (409
    від pick_up/not_picked_up) — тихо пропускаємо (try/except на резерв)."""
    processed = 0
    shops = (await session.scalars(
        select(Shop).where(Shop.np_api_key_encrypted.is_not(None))
    )).all()

    for shop in shops:
        try:
            assert shop.np_api_key_encrypted is not None
            api_key = decrypt(shop.np_api_key_encrypted)

            reservations = (await session.scalars(
                select(Reservation).where(
                    Reservation.shop_id == shop.id,
                    Reservation.status == ReservationStatus.shipped,
                    Reservation.ttn.is_not(None),
                )
            )).all()
            by_ttn = {r.ttn: r for r in reservations if r.ttn}
            if not by_ttn:
                continue

            results = await track(api_key, list(by_ttn.keys()))
        except (CryptoError, NovaPoshtaError):
            logger.warning("np_tracking: магазин %s пропущено", shop.id, exc_info=True)
            continue

        for result in results:
            number = result.get("Number")
            if not isinstance(number, str):
                continue
            reservation = by_ttn.get(number)
            if reservation is None:
                continue
            try:
                code = int(result["StatusCode"])
            except (KeyError, TypeError, ValueError):
                continue

            recipient = _extract_np_recipient(result)
            if recipient:
                reservation.np_recipient = recipient

            try:
                if code in PICKED_CODES:
                    updated = await inventory.pick_up(
                        session, shop_id=shop.id, reservation_id=reservation.id
                    )
                    name, variant = await _np_display_name(session, updated.variant_id)
                    amount = (variant.price * updated.qty) if variant else Decimal("0")
                    await notify(
                        shop.owner_tg_id,
                        f"📦 Посилку {reservation.ttn} отримано — {name}, "
                        f"+{amount.quantize(Decimal('0.01'))} ₴",
                    )
                    processed += 1
                elif code in RETURNED_CODES:
                    updated = await inventory.not_picked_up(
                        session, shop_id=shop.id, reservation_id=reservation.id, reason="refused"
                    )
                    name, _ = await _np_display_name(session, updated.variant_id)
                    await notify(
                        shop.owner_tg_id,
                        f"↩️ Посилку {reservation.ttn} не забрали — {name} повернуто на склад",
                    )
                    processed += 1
                else:
                    reservation.np_status = result.get("Status")
                    await session.commit()
            except InventoryError:
                # Уже оброблено вручну (pick_up/not_picked_up/release) паралельно з кроном.
                logger.warning(
                    "np_tracking: резерв %s вже оброблено, скіп", reservation.id, exc_info=True
                )
                continue

    return processed


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
