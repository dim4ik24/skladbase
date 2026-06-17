"""
Stage 5a acceptance tests (billing: Telegram Stars subscription, read-only
enforcement, promo codes).

Criteria (ROADMAP.md, Стадія 5a):
  1. перший successful_payment (Stars) -> підписка active, period_end
     продовжений, є рядок у Payment
  2. recurring successful_payment (is_recurring=True) -> period_end ще
     продовжений
  3. promo -> +60 днів, вдруге тим самим магазином -> помилка
  4. підписка expired -> POST/PATCH/DELETE /api/products дають 402,
     GET /api/products досі 200
  5. cancel -> auto_renew=False, статус canceled, доступ до кінця періоду
  6. ізоляція: платіж одного магазину не чіпає підписку іншого

Бот/Stars мокаються — реальний Telegram API не зачіпається.
"""
from __future__ import annotations

import json
import time

import pytest
from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.types import Update
from httpx import AsyncClient
from sqlalchemy import func, select

from app import db
from app.bot.dispatcher import dp
from app.models import (
    MemberRole,
    Membership,
    Payment,
    Product,
    PromoCode,
    PromoType,
    Subscription,
    SubStatus,
)
from tests.conftest import TEST_BOT_TOKEN, make_init_data

HEADER = "X-Telegram-Init-Data"


async def _bootstrap(client: AsyncClient, tg_id: int, name: str = "Тест") -> tuple[str, int]:
    init_data = make_init_data(tg_id, first_name=name)
    r = await client.get("/api/me", headers={HEADER: init_data})
    assert r.status_code == 200
    return init_data, r.json()["shop_id"]


def _successful_payment_update(
    *,
    update_id: int,
    tg_id: int,
    charge_id: str,
    shop_id: int | None = None,
    plan_code: str = "basic",
    period: str = "month",
    is_recurring: bool = False,
    total_amount: int = 100,
) -> dict:
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id,
            "date": int(time.time()),
            "chat": {"id": tg_id, "type": "private"},
            "from": {"id": tg_id, "is_bot": False, "first_name": "Тест"},
            "successful_payment": {
                "currency": "XTR",
                "total_amount": total_amount,
                "invoice_payload": json.dumps(
                    {"shop_id": shop_id, "plan": plan_code, "period": period}
                ),
                "telegram_payment_charge_id": charge_id,
                "provider_payment_charge_id": f"prov-{charge_id}",
                "is_recurring": is_recurring,
            },
        },
    }


_next_update_id = 1_000


async def _feed_payment(
    tg_id: int, *, charge_id: str, shop_id: int | None = None, is_recurring: bool = False
) -> None:
    global _next_update_id
    _next_update_id += 1

    bot = Bot(token=TEST_BOT_TOKEN)
    update = Update.model_validate(
        _successful_payment_update(
            update_id=_next_update_id,
            tg_id=tg_id,
            charge_id=charge_id,
            shop_id=shop_id,
            is_recurring=is_recurring,
        )
    )
    try:
        async with db.async_session() as session:
            await dp.feed_update(bot, update, session=session)
    finally:
        await bot.session.close()


async def _get_subscription(shop_id: int) -> Subscription:
    async with db.async_session() as session:
        sub = await session.scalar(select(Subscription).where(Subscription.shop_id == shop_id))
        assert sub is not None
        return sub


async def _insert_promo(code: str, *, value_days: int = 60, max_uses: int = 5) -> None:
    async with db.async_session() as session:
        session.add(
            PromoCode(code=code, type=PromoType.free_period, value=value_days, max_uses=max_uses)
        )
        await session.commit()


_telegram_calls: list[tuple[str, object]] = []


async def _fake_make_request(self, bot, method, timeout=None):
    """Підміна реального HTTP-виклику до Telegram на рівні транспорту
    (`AiohttpSession.make_request`) — перехоплює БУДЬ-який спосіб виклику API
    (включно з `pre_checkout_query.answer()`, який не йде через
    `Bot.answer_pre_checkout_query`, а напряму через `Bot.__call__`)."""
    name = type(method).__name__
    _telegram_calls.append((name, method))
    if name == "AnswerPreCheckoutQuery":
        return True
    if name == "CreateInvoiceLink":
        return "https://t.me/invoice/fake-link"
    if name == "EditUserStarSubscription":
        return True
    raise AssertionError(f"непередбачений Telegram API метод у тесті: {name}")


def _patch_telegram_api(monkeypatch: pytest.MonkeyPatch) -> None:
    _telegram_calls.clear()
    monkeypatch.setattr(AiohttpSession, "make_request", _fake_make_request)


@pytest.mark.asyncio
async def test_first_successful_payment_activates_subscription(client: AsyncClient) -> None:
    _init_data, shop_id = await _bootstrap(client, 5001)

    sub_before = await _get_subscription(shop_id)
    assert sub_before.status == SubStatus.trial

    await _feed_payment(5001, charge_id="charge-1")

    sub_after = await _get_subscription(shop_id)
    assert sub_after.status == SubStatus.active
    assert sub_after.auto_renew is True
    assert sub_after.current_period_end is not None
    assert sub_after.current_period_end > sub_before.current_period_end

    async with db.async_session() as session:
        payments = (await session.scalars(select(Payment).where(Payment.shop_id == shop_id))).all()
    assert len(payments) == 1
    assert payments[0].external_id == "charge-1"


@pytest.mark.asyncio
async def test_recurring_payment_extends_period_further(client: AsyncClient) -> None:
    _init_data, shop_id = await _bootstrap(client, 5002)

    await _feed_payment(5002, charge_id="charge-2a", is_recurring=False)
    sub_after_first = await _get_subscription(shop_id)

    await _feed_payment(5002, charge_id="charge-2b", is_recurring=True)
    sub_after_second = await _get_subscription(shop_id)

    assert sub_after_second.status == SubStatus.active
    assert sub_after_second.current_period_end > sub_after_first.current_period_end

    async with db.async_session() as session:
        payments_count = await session.scalar(
            select(func.count(Payment.id)).where(Payment.shop_id == shop_id)
        )
    assert payments_count == 2


@pytest.mark.asyncio
async def test_promo_extends_period_and_rejects_second_redeem(client: AsyncClient) -> None:
    init_data, shop_id = await _bootstrap(client, 5003)
    await _insert_promo("WELCOME60")

    sub_before = await _get_subscription(shop_id)

    r1 = await client.post(
        "/api/billing/promo", json={"code": "welcome60"}, headers={HEADER: init_data}
    )
    assert r1.status_code == 200, r1.text

    sub_after = await _get_subscription(shop_id)
    assert sub_after.status == SubStatus.active
    assert sub_after.is_comp is True
    assert (sub_after.current_period_end - sub_before.current_period_end).days == 60

    r2 = await client.post(
        "/api/billing/promo", json={"code": "welcome60"}, headers={HEADER: init_data}
    )
    assert r2.status_code == 400


@pytest.mark.asyncio
async def test_expired_subscription_blocks_writes_but_not_reads(client: AsyncClient) -> None:
    init_data, shop_id = await _bootstrap(client, 5004)

    async with db.async_session() as session:
        sub = await session.scalar(select(Subscription).where(Subscription.shop_id == shop_id))
        assert sub is not None
        sub.status = SubStatus.expired
        await session.commit()

    payload = {"name": "Товар", "variants": [{"axis_values": {}, "price": "10"}]}
    r_create = await client.post("/api/products", json=payload, headers={HEADER: init_data})
    assert r_create.status_code == 402

    r_list = await client.get("/api/products", headers={HEADER: init_data})
    assert r_list.status_code == 200

    async with db.async_session() as session:
        product = Product(shop_id=shop_id, name="Товар напряму")
        session.add(product)
        await session.commit()
        product_id = product.id

    r_patch = await client.patch(
        f"/api/products/{product_id}", json={"name": "Х"}, headers={HEADER: init_data}
    )
    assert r_patch.status_code == 402

    r_delete = await client.delete(f"/api/products/{product_id}", headers={HEADER: init_data})
    assert r_delete.status_code == 402


@pytest.mark.asyncio
async def test_cancel_sets_auto_renew_false_status_canceled_access_until_period_end(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_telegram_api(monkeypatch)
    init_data, _shop_id = await _bootstrap(client, 5005)
    await _feed_payment(5005, charge_id="charge-5")

    r = await client.post("/api/billing/cancel", headers={HEADER: init_data})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["auto_renew"] is False
    assert body["status"] == "canceled"

    payload = {"name": "Товар", "variants": [{"axis_values": {}, "price": "10"}]}
    r_create = await client.post("/api/products", json=payload, headers={HEADER: init_data})
    assert r_create.status_code == 201, r_create.text


@pytest.mark.asyncio
async def test_payment_does_not_affect_other_shop_subscription(client: AsyncClient) -> None:
    _init_a, shop_a = await _bootstrap(client, 5006, "Шоп А")
    _init_b, shop_b = await _bootstrap(client, 5007, "Шоп Б")

    sub_b_before = await _get_subscription(shop_b)

    await _feed_payment(5006, charge_id="charge-6")

    sub_a_after = await _get_subscription(shop_a)
    sub_b_after = await _get_subscription(shop_b)

    assert sub_a_after.status == SubStatus.active
    assert sub_b_after.status == SubStatus.trial
    assert sub_b_after.current_period_end == sub_b_before.current_period_end


@pytest.mark.asyncio
async def test_payment_credits_shop_from_payload_for_owner_of_two_shops(
    client: AsyncClient,
) -> None:
    """Регресія: інвойс не несе shop_id неявно (tg_id платника не унікально
    визначає магазин — власник може мати кілька). Оплата має зарахуватись
    саме shop_id з payload, а не першому-ліпшому Membership цього tg_id."""
    tg_id = 5010
    _init_data, shop_a = await _bootstrap(client, tg_id, "Шоп А власника")

    _other_init_data, shop_b = await _bootstrap(client, 5011, "Шоп Б іншого власника")
    async with db.async_session() as session:
        session.add(Membership(shop_id=shop_b, tg_id=tg_id, role=MemberRole.manager))
        await session.commit()

    sub_b_before = await _get_subscription(shop_b)

    await _feed_payment(tg_id, charge_id="charge-multi-1", shop_id=shop_a)

    sub_a_after = await _get_subscription(shop_a)
    sub_b_after = await _get_subscription(shop_b)

    assert sub_a_after.status == SubStatus.active
    assert sub_b_after.status == SubStatus.trial
    assert sub_b_after.current_period_end == sub_b_before.current_period_end


@pytest.mark.asyncio
async def test_payment_ignored_when_payer_not_member_of_payload_shop(client: AsyncClient) -> None:
    """Захист від підробленого payload: shop_id вказує на магазин, де платник
    не є членом -> платіж ігнорується, підписка того магазину не змінюється."""
    _init_a, shop_a = await _bootstrap(client, 5012, "Шоп А")
    _init_b, _shop_b = await _bootstrap(client, 5013, "Шоп Б")

    sub_a_before = await _get_subscription(shop_a)

    await _feed_payment(5013, charge_id="charge-spoof-1", shop_id=shop_a)

    sub_a_after = await _get_subscription(shop_a)
    assert sub_a_after.status == SubStatus.trial
    assert sub_a_after.current_period_end == sub_a_before.current_period_end


@pytest.mark.asyncio
async def test_pre_checkout_query_is_answered_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_telegram_api(monkeypatch)

    bot = Bot(token=TEST_BOT_TOKEN)
    update = Update.model_validate(
        {
            "update_id": 999,
            "pre_checkout_query": {
                "id": "pcq-1",
                "from": {"id": 1, "is_bot": False, "first_name": "Тест"},
                "currency": "XTR",
                "total_amount": 100,
                "invoice_payload": "{}",
            },
        }
    )
    try:
        await dp.feed_update(bot, update)
    finally:
        await bot.session.close()

    assert len(_telegram_calls) == 1
    name, method = _telegram_calls[0]
    assert name == "AnswerPreCheckoutQuery"
    assert method.pre_checkout_query_id == "pcq-1"
    assert method.ok is True


@pytest.mark.asyncio
async def test_webhook_endpoint_processes_successful_payment(client: AsyncClient) -> None:
    _init_data, shop_id = await _bootstrap(client, 5008)

    update_payload = _successful_payment_update(
        update_id=1, tg_id=5008, charge_id="charge-http-1"
    )
    r = await client.post("/webhook/telegram", json=update_payload)
    assert r.status_code == 200
    assert r.json() == {"ok": True}

    sub = await _get_subscription(shop_id)
    assert sub.status == SubStatus.active


@pytest.mark.asyncio
async def test_checkout_stars_returns_invoice_link(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_telegram_api(monkeypatch)

    init_data, _shop_id = await _bootstrap(client, 5009)
    r = await client.post(
        "/api/billing/checkout/stars", json={"plan_code": "basic"}, headers={HEADER: init_data}
    )
    assert r.status_code == 200, r.text
    assert r.json()["invoice_link"] == "https://t.me/invoice/fake-link"
