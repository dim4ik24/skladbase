"""
Stage 6 acceptance tests (APScheduler jobs + live Telegram notifier).

Criteria (ROADMAP.md, Стадія 6):
  1. expire_subscriptions: підписка з current_period_end у минулому й
     auto_renew=False -> expired, notifier викликаний; Stars/картка з
     auto_renew=True НЕ чіпаються
  2. send_renewal_reminders: підписка закінчується <3 днів, auto_renew=False,
     ще не нагадано -> нагадано один раз; повторний запуск -> не дублює
  3. release_expired_reservations: резерв з expires_at у минулому -> released,
     reserved повертається в available
  4. low_stock_scan: variant available<=threshold і notified_at=NULL ->
     сповіщено один раз + прапорець; повторний скан -> тиша (дебаунс); після
     restock вище порога прапорець скинуто -> при наступному падінні
     сповіщає знову
  5. charge_due_card_subscriptions: картка до списання, мок
     wfp.charge_recurring Approved -> період продовжено; Declined ->
     mark_past_due + notifier
  6. notifier при порожньому BOT_TOKEN -> no-op; помилка send -> зловлена

Час крутимо станом БД (current_period_end/expires_at у минулому/майбутньому),
не реальним sleep. Notifier у тестах задач — стаб, що записує виклики.
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError
from aiogram.methods import SendMessage
from sqlalchemy import select

from app import db, tasks
from app.bot.notify import notifier
from app.config import settings
from app.models import (
    MemberRole,
    Membership,
    Plan,
    Product,
    Reservation,
    ReservationSource,
    ReservationStatus,
    Shop,
    SubPeriod,
    SubProvider,
    Subscription,
    SubStatus,
    Variant,
    ensure_aware_utc,
    utcnow,
)
from app.services import inventory


class _StubNotifier:
    def __init__(self) -> None:
        self.calls: list[tuple[int, str]] = []

    async def __call__(self, tg_id: int, text: str) -> None:
        self.calls.append((tg_id, text))


async def _make_shop(tg_id: int, name: str = "Тест") -> int:
    async with db.async_session() as session:
        shop = Shop(owner_tg_id=tg_id, name=name, slug=f"shop-{uuid4().hex[:8]}")
        session.add(shop)
        await session.flush()
        session.add(Membership(shop_id=shop.id, tg_id=tg_id, role=MemberRole.owner))
        await session.commit()
        return shop.id


async def _make_subscription(
    shop_id: int,
    *,
    status: SubStatus,
    current_period_end,
    auto_renew: bool,
    provider: SubProvider | None = None,
    renewal_reminder_sent: bool = False,
    external_sub_id: str | None = None,
    plan_id: int | None = None,
) -> int:
    async with db.async_session() as session:
        sub = Subscription(
            shop_id=shop_id,
            status=status,
            current_period_end=current_period_end,
            auto_renew=auto_renew,
            provider=provider,
            period=SubPeriod.month,
            renewal_reminder_sent=renewal_reminder_sent,
            external_sub_id=external_sub_id,
            plan_id=plan_id,
        )
        session.add(sub)
        await session.commit()
        return sub.id


async def _ensure_plan(code: str = "basic") -> int:
    async with db.async_session() as session:
        existing = await session.scalar(select(Plan).where(Plan.code == code))
        if existing is not None:
            return existing.id
        plan = Plan(
            code=code,
            name="Basic",
            period=SubPeriod.month,
            price_uah=Decimal("150"),
            price_stars=100,
            limits={},
        )
        session.add(plan)
        await session.commit()
        return plan.id


async def _make_variant(shop_id: int, *, on_hand: int, low_stock_threshold: int = 3) -> int:
    async with db.async_session() as session:
        product = Product(shop_id=shop_id, name="Товар")
        session.add(product)
        await session.flush()
        variant = Variant(
            shop_id=shop_id,
            product_id=product.id,
            sku=f"SKU-{uuid4().hex[:8]}",
            price=Decimal("10"),
            on_hand=on_hand,
            low_stock_threshold=low_stock_threshold,
        )
        session.add(variant)
        await session.commit()
        return variant.id


# --------------------------------------------------------------------------- #
#  expire_subscriptions
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_expire_subscriptions_expires_non_auto_renew_and_skips_auto_renew() -> None:
    shop_a = await _make_shop(7001)
    shop_b = await _make_shop(7002)

    sub_a_id = await _make_subscription(
        shop_a,
        status=SubStatus.trial,
        current_period_end=utcnow() - timedelta(days=1),
        auto_renew=False,
    )
    sub_b_id = await _make_subscription(
        shop_b,
        status=SubStatus.active,
        current_period_end=utcnow() - timedelta(days=1),
        auto_renew=True,
        provider=SubProvider.stars,
    )

    stub = _StubNotifier()
    async with db.async_session() as session:
        count = await tasks.expire_subscriptions(session, stub)
    assert count == 1

    async with db.async_session() as session:
        sub_a = await session.get(Subscription, sub_a_id)
        sub_b = await session.get(Subscription, sub_b_id)
    assert sub_a is not None and sub_a.status == SubStatus.expired
    assert sub_b is not None and sub_b.status == SubStatus.active

    assert len(stub.calls) == 1
    assert stub.calls[0][0] == 7001


# --------------------------------------------------------------------------- #
#  send_renewal_reminders
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_send_renewal_reminders_once_then_debounced() -> None:
    shop_id = await _make_shop(7003)
    sub_id = await _make_subscription(
        shop_id,
        status=SubStatus.active,
        current_period_end=utcnow() + timedelta(days=2),
        auto_renew=False,
    )

    stub = _StubNotifier()
    async with db.async_session() as session:
        count1 = await tasks.send_renewal_reminders(session, stub)
    assert count1 == 1
    assert len(stub.calls) == 1

    async with db.async_session() as session:
        sub = await session.get(Subscription, sub_id)
        assert sub is not None
        assert sub.renewal_reminder_sent is True

    async with db.async_session() as session:
        count2 = await tasks.send_renewal_reminders(session, stub)
    assert count2 == 0
    assert len(stub.calls) == 1


# --------------------------------------------------------------------------- #
#  release_expired_reservations
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_release_expired_reservations_returns_reserved_to_available() -> None:
    shop_id = await _make_shop(7004)
    variant_id = await _make_variant(shop_id, on_hand=10)

    async with db.async_session() as session:
        await inventory.reserve(
            session,
            shop_id=shop_id,
            variant_id=variant_id,
            qty=4,
            source=ReservationSource.manual,
        )
        reservation = await session.scalar(
            select(Reservation).where(Reservation.variant_id == variant_id)
        )
        assert reservation is not None
        reservation.expires_at = utcnow() - timedelta(hours=1)
        reservation_id = reservation.id
        await session.commit()

    async with db.async_session() as session:
        count = await tasks.release_expired_reservations(session)
    assert count == 1

    async with db.async_session() as session:
        variant = await session.get(Variant, variant_id)
        reservation = await session.get(Reservation, reservation_id)
    assert variant is not None
    assert variant.reserved == 0
    assert variant.available == 10
    assert reservation is not None
    assert reservation.status == ReservationStatus.released


# --------------------------------------------------------------------------- #
#  low_stock_scan
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_low_stock_scan_debounced_and_resets_after_restock() -> None:
    shop_id = await _make_shop(7005)
    variant_id = await _make_variant(shop_id, on_hand=2, low_stock_threshold=3)

    stub = _StubNotifier()
    async with db.async_session() as session:
        count1 = await tasks.low_stock_scan(session, stub)
    assert count1 == 1
    assert len(stub.calls) == 1

    async with db.async_session() as session:
        variant = await session.get(Variant, variant_id)
        assert variant is not None
        assert variant.low_stock_notified_at is not None

    # повторний скан -> тиша (дебаунс)
    async with db.async_session() as session:
        count2 = await tasks.low_stock_scan(session, stub)
    assert count2 == 0
    assert len(stub.calls) == 1

    # restock вище порога -> скидає прапорець (логіка вже в inventory.restock)
    async with db.async_session() as session:
        await inventory.restock(session, shop_id=shop_id, variant_id=variant_id, qty=10)

    async with db.async_session() as session:
        variant = await session.get(Variant, variant_id)
        assert variant is not None
        assert variant.low_stock_notified_at is None

    # знову впав нижче порога -> сповіщає вдруге (12 -> 2, той самий поріг 3)
    async with db.async_session() as session:
        await inventory.write_off(
            session, shop_id=shop_id, variant_id=variant_id, qty=10, reason="correction"
        )

    async with db.async_session() as session:
        count3 = await tasks.low_stock_scan(session, stub)
    assert count3 == 1
    assert len(stub.calls) == 2


# --------------------------------------------------------------------------- #
#  charge_due_card_subscriptions
# --------------------------------------------------------------------------- #
class _FakeWfpApproved:
    async def charge_recurring(self, *, rec_token: str, order_ref: str, amount: Decimal) -> dict:
        return {"transactionStatus": "Approved", "orderReference": order_ref}


class _FakeWfpDeclined:
    async def charge_recurring(self, *, rec_token: str, order_ref: str, amount: Decimal) -> dict:
        return {"transactionStatus": "Declined", "orderReference": order_ref}


@pytest.mark.asyncio
async def test_charge_due_card_subscriptions_approved_extends_period() -> None:
    shop_id = await _make_shop(7006)
    plan_id = await _ensure_plan()
    sub_id = await _make_subscription(
        shop_id,
        status=SubStatus.active,
        current_period_end=utcnow() + timedelta(hours=1),
        auto_renew=True,
        provider=SubProvider.card,
        external_sub_id="rec-token-x",
        plan_id=plan_id,
    )

    stub = _StubNotifier()
    async with db.async_session() as session:
        charged = await tasks.charge_due_card_subscriptions(session, _FakeWfpApproved(), stub)
    assert charged == 1

    async with db.async_session() as session:
        sub = await session.get(Subscription, sub_id)
    assert sub is not None
    assert sub.status == SubStatus.active
    assert sub.current_period_end is not None
    assert ensure_aware_utc(sub.current_period_end) > utcnow() + timedelta(days=20)
    assert len(stub.calls) == 0


@pytest.mark.asyncio
async def test_charge_due_card_subscriptions_declined_marks_past_due_and_notifies() -> None:
    shop_id = await _make_shop(7007)
    plan_id = await _ensure_plan()
    sub_id = await _make_subscription(
        shop_id,
        status=SubStatus.active,
        current_period_end=utcnow() + timedelta(hours=1),
        auto_renew=True,
        provider=SubProvider.card,
        external_sub_id="rec-token-y",
        plan_id=plan_id,
    )

    stub = _StubNotifier()
    async with db.async_session() as session:
        charged = await tasks.charge_due_card_subscriptions(session, _FakeWfpDeclined(), stub)
    assert charged == 0

    async with db.async_session() as session:
        sub = await session.get(Subscription, sub_id)
    assert sub is not None
    assert sub.status == SubStatus.past_due
    assert len(stub.calls) == 1


# --------------------------------------------------------------------------- #
#  notifier
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_notifier_noop_when_bot_token_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "BOT_TOKEN", "")
    await notifier(123, "тест")  # не падає


@pytest.mark.asyncio
async def test_notifier_catches_send_error(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_send_message(self, chat_id, text, **kwargs):
        raise TelegramForbiddenError(
            method=SendMessage(chat_id=chat_id, text=text), message="bot was blocked by the user"
        )

    monkeypatch.setattr(Bot, "send_message", _fake_send_message)

    await notifier(123, "тест")  # не падає — помилка зловлена й залогована


# --------------------------------------------------------------------------- #
#  scheduler: реєстрація джоб і гейтинг прапорцем
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_scheduler_registers_expected_jobs_with_intervals() -> None:
    from app.scheduler import create_scheduler

    scheduler = create_scheduler()
    jobs = {job.id: job for job in scheduler.get_jobs()}

    assert set(jobs) == {
        "np_tracking",
        "release_expired_reservations",
        "low_stock_scan",
        "charge_due_card_subscriptions",
        "expire_subscriptions",
        "send_renewal_reminders",
    }
    assert jobs["np_tracking"].trigger.interval == timedelta(minutes=10)
    assert jobs["release_expired_reservations"].trigger.interval == timedelta(hours=1)
    assert jobs["low_stock_scan"].trigger.interval == timedelta(hours=1)
    assert jobs["charge_due_card_subscriptions"].trigger.interval == timedelta(hours=6)
    assert jobs["expire_subscriptions"].trigger.interval == timedelta(hours=24)
    assert jobs["send_renewal_reminders"].trigger.interval == timedelta(hours=24)


@pytest.mark.asyncio
async def test_lifespan_respects_run_scheduler_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.main as main_module

    calls: list[str] = []

    class _FakeScheduler:
        def start(self) -> None:
            calls.append("start")

        def shutdown(self, wait: bool = False) -> None:
            calls.append("shutdown")

    monkeypatch.setattr(main_module, "create_scheduler", lambda: _FakeScheduler())

    monkeypatch.setattr(settings, "RUN_SCHEDULER", False)
    async with main_module.app.router.lifespan_context(main_module.app):
        pass
    assert calls == []

    monkeypatch.setattr(settings, "RUN_SCHEDULER", True)
    async with main_module.app.router.lifespan_context(main_module.app):
        pass
    assert calls == ["start", "shutdown"]
