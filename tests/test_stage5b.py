"""
Stage 5b acceptance tests (billing: WayForPay card + NOWPayments crypto).

Criteria (ROADMAP.md, Стадія 5b):
  1. card checkout -> форма з валідним підписом, ref кодує shop_id/plan/period
  2. WFP callback валідний підпис -> subscription active, provider=card,
     auto_renew=True, recToken у external_sub_id, period продовжений
  3. WFP callback невалідний підпис -> 400/ігнор, підписка НЕ активована
  4. crypto checkout (мок) -> order_id кодує shop/plan/period
  5. NOWPayments IPN валідний + finished -> active, provider=crypto,
     auto_renew=False
  6. IPN невалідний підпис АБО статус не finished -> ігнор, без активації
  7. річний план через картку рахується з -10% (effective_price_uah)
  8. record_payment викликається лише з вебхук-обробників (не з checkout)
  9. ізоляція: платіж резолвиться по ref у потрібний магазин

httpx/провайдери мокаються — реальні WayForPay/NOWPayments API не зачіпаються.
"""
from __future__ import annotations

import hashlib
import hmac
import json
from decimal import Decimal

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app import db
from app.billing.refs import build_ref, parse_ref
from app.config import settings
from app.models import Payment, Plan, SubProvider, Subscription, SubStatus
from app.services.subscriptions import SubscriptionService
from tests.conftest import make_init_data

HEADER = "X-Telegram-Init-Data"

TEST_WFP_MERCHANT = "test_merchant"
TEST_WFP_SECRET = "test_wfp_secret"
TEST_WFP_DOMAIN = "shop.example.com"
TEST_NOWPAYMENTS_API_KEY = "test_np_api_key"
TEST_NOWPAYMENTS_IPN_SECRET = "test_np_ipn_secret"


@pytest.fixture(autouse=True)
def _billing_provider_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "WFP_MERCHANT", TEST_WFP_MERCHANT)
    monkeypatch.setattr(settings, "WFP_SECRET", TEST_WFP_SECRET)
    monkeypatch.setattr(settings, "WFP_DOMAIN", TEST_WFP_DOMAIN)
    monkeypatch.setattr(settings, "NOWPAYMENTS_API_KEY", TEST_NOWPAYMENTS_API_KEY)
    monkeypatch.setattr(settings, "NOWPAYMENTS_IPN_SECRET", TEST_NOWPAYMENTS_IPN_SECRET)


async def _bootstrap(client: AsyncClient, tg_id: int, name: str = "Тест") -> tuple[str, int]:
    init_data = make_init_data(tg_id, first_name=name)
    r = await client.get("/api/me", headers={HEADER: init_data})
    assert r.status_code == 200
    return init_data, r.json()["shop_id"]


async def _get_subscription(shop_id: int) -> Subscription:
    async with db.async_session() as session:
        sub = await session.scalar(select(Subscription).where(Subscription.shop_id == shop_id))
        assert sub is not None
        return sub


def _wfp_sign(secret: str, fields: list) -> str:
    msg = ";".join(str(f) for f in fields)
    return hmac.new(secret.encode(), msg.encode(), hashlib.md5).hexdigest()


def _wfp_callback_payload(
    *,
    order_ref: str,
    amount: str = "150.00",
    currency: str = "UAH",
    rec_token: str = "rec-token-1",
    merchant: str = TEST_WFP_MERCHANT,
    secret: str = TEST_WFP_SECRET,
    tamper: bool = False,
) -> dict:
    auth_code = "auth-1"
    card_pan = "4111XXXXXXXX1111"
    transaction_status = "Approved"
    reason_code = "1100"
    sign = _wfp_sign(
        secret,
        [merchant, order_ref, amount, currency, auth_code, card_pan, transaction_status, reason_code],
    )
    return {
        "merchantAccount": merchant,
        "orderReference": order_ref,
        "amount": amount,
        "currency": currency,
        "authCode": auth_code,
        "cardPan": card_pan,
        "transactionStatus": transaction_status,
        "reasonCode": reason_code,
        "recToken": rec_token,
        "merchantSignature": "0" * 32 if tamper else sign,
    }


def _nowpayments_ipn_payload(
    *,
    order_id: str,
    payment_status: str = "finished",
    price_amount: float = 10.0,
    payment_id: str = "np-pay-1",
) -> dict:
    return {
        "payment_id": payment_id,
        "payment_status": payment_status,
        "order_id": order_id,
        "price_amount": price_amount,
        "price_currency": "usd",
    }


def _nowpayments_sign(secret: str, body: bytes) -> str:
    sorted_json = json.dumps(json.loads(body), separators=(",", ":"), sort_keys=True)
    return hmac.new(secret.encode(), sorted_json.encode(), hashlib.sha512).hexdigest()


class _FakeNowPaymentsResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def json(self) -> dict:
        return self._payload


class _RecordingNowPaymentsClient:
    calls: list[dict] = []

    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self) -> "_RecordingNowPaymentsClient":
        return self

    async def __aexit__(self, *exc_info) -> bool:
        return False

    async def post(self, url, *, json, headers) -> _FakeNowPaymentsResponse:
        _RecordingNowPaymentsClient.calls.append({"url": url, "json": json, "headers": headers})
        return _FakeNowPaymentsResponse(
            {
                "payment_id": "np-fake-1",
                "pay_address": "fake-crypto-address",
                "price_amount": json["price_amount"],
                "pay_currency": json["pay_currency"],
                "order_id": json["order_id"],
            }
        )


@pytest.mark.asyncio
async def test_card_checkout_returns_signed_form_with_encoded_ref(client: AsyncClient) -> None:
    init_data, shop_id = await _bootstrap(client, 6001)

    r = await client.post(
        "/api/billing/checkout/card",
        json={"plan_code": "basic", "period": "month"},
        headers={HEADER: init_data},
    )
    assert r.status_code == 200, r.text
    form = r.json()["form"]

    parsed = parse_ref(form["orderReference"])
    assert parsed.shop_id == shop_id
    assert parsed.plan_code == "basic"
    assert parsed.period == "month"

    msg = ";".join(
        [
            form["merchantAccount"],
            form["merchantDomainName"],
            form["orderReference"],
            str(form["orderDate"]),
            form["amount"],
            form["currency"],
            form["productName"][0],
            "1",
            form["productPrice"][0],
        ]
    )
    expected_signature = hmac.new(TEST_WFP_SECRET.encode(), msg.encode(), hashlib.md5).hexdigest()
    assert form["merchantSignature"] == expected_signature


@pytest.mark.asyncio
async def test_card_checkout_year_period_applies_ten_percent_discount(client: AsyncClient) -> None:
    init_data, _shop_id = await _bootstrap(client, 6002)

    async with db.async_session() as session:
        plan = await session.scalar(select(Plan).where(Plan.code == "basic"))
        assert plan is not None
        plan_price_uah = plan.price_uah

    r = await client.post(
        "/api/billing/checkout/card",
        json={"plan_code": "basic", "period": "year"},
        headers={HEADER: init_data},
    )
    assert r.status_code == 200, r.text
    form = r.json()["form"]

    expected = (plan_price_uah * 12 * Decimal("0.90")).quantize(Decimal("0.01"))
    assert Decimal(form["amount"]) == expected


@pytest.mark.asyncio
async def test_wfp_callback_valid_signature_activates_subscription(client: AsyncClient) -> None:
    _init_data, shop_id = await _bootstrap(client, 6003)
    sub_before = await _get_subscription(shop_id)

    order_ref = build_ref(shop_id, "basic", "month")
    payload = _wfp_callback_payload(order_ref=order_ref, rec_token="rec-abc-123")

    r = await client.post("/webhook/wayforpay", json=payload)
    assert r.status_code == 200, r.text

    sub_after = await _get_subscription(shop_id)
    assert sub_after.status == SubStatus.active
    assert sub_after.provider == SubProvider.card
    assert sub_after.auto_renew is True
    assert sub_after.external_sub_id == "rec-abc-123"
    assert sub_after.current_period_end > sub_before.current_period_end


@pytest.mark.asyncio
async def test_wfp_callback_duplicate_does_not_extend_period_twice(client: AsyncClient) -> None:
    """Регресія (Стадія 5c): WFP може доставити той самий callback повторно
    (ретрай) — orderReference однаковий має продовжити період лише один раз,
    і ОБИДВІ відповіді мають бути валідним підписаним "accept"."""
    _init_data, shop_id = await _bootstrap(client, 6012)

    order_ref = build_ref(shop_id, "basic", "month")
    payload = _wfp_callback_payload(order_ref=order_ref, rec_token="rec-dup-1")

    r1 = await client.post("/webhook/wayforpay", json=payload)
    assert r1.status_code == 200, r1.text
    sub_after_first = await _get_subscription(shop_id)

    r2 = await client.post("/webhook/wayforpay", json=payload)
    assert r2.status_code == 200, r2.text
    sub_after_second = await _get_subscription(shop_id)

    assert sub_after_second.current_period_end == sub_after_first.current_period_end
    assert sub_after_second.external_sub_id == "rec-dup-1"

    async with db.async_session() as session:
        payments_count = await session.scalar(
            select(func.count(Payment.id)).where(Payment.shop_id == shop_id)
        )
    assert payments_count == 1

    for r in (r1, r2):
        body = r.json()
        assert body["status"] == "accept"
        assert body["orderReference"] == order_ref
        msg = ";".join([body["orderReference"], body["status"], str(body["time"])])
        expected_signature = hmac.new(
            TEST_WFP_SECRET.encode(), msg.encode(), hashlib.md5
        ).hexdigest()
        assert body["signature"] == expected_signature


@pytest.mark.asyncio
async def test_wfp_callback_invalid_signature_does_not_activate(client: AsyncClient) -> None:
    _init_data, shop_id = await _bootstrap(client, 6004)

    order_ref = build_ref(shop_id, "basic", "month")
    payload = _wfp_callback_payload(order_ref=order_ref, tamper=True)

    r = await client.post("/webhook/wayforpay", json=payload)
    assert r.status_code == 400

    sub = await _get_subscription(shop_id)
    assert sub.status == SubStatus.trial


@pytest.mark.asyncio
async def test_crypto_checkout_encodes_ref_in_order_id(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _RecordingNowPaymentsClient.calls.clear()
    monkeypatch.setattr(httpx, "AsyncClient", _RecordingNowPaymentsClient)

    init_data, shop_id = await _bootstrap(client, 6005)

    r = await client.post(
        "/api/billing/checkout/crypto",
        json={"plan_code": "pro", "period": "year"},
        headers={HEADER: init_data},
    )
    assert r.status_code == 200, r.text

    assert len(_RecordingNowPaymentsClient.calls) == 1
    sent = _RecordingNowPaymentsClient.calls[0]["json"]
    parsed = parse_ref(sent["order_id"])
    assert parsed.shop_id == shop_id
    assert parsed.plan_code == "pro"
    assert parsed.period == "year"


@pytest.mark.asyncio
async def test_nowpayments_ipn_valid_finished_activates_subscription(client: AsyncClient) -> None:
    _init_data, shop_id = await _bootstrap(client, 6006)
    sub_before = await _get_subscription(shop_id)

    order_id = build_ref(shop_id, "basic", "month")
    payload = _nowpayments_ipn_payload(order_id=order_id)
    body = json.dumps(payload).encode()
    signature = _nowpayments_sign(TEST_NOWPAYMENTS_IPN_SECRET, body)

    r = await client.post(
        "/webhook/nowpayments",
        content=body,
        headers={"Content-Type": "application/json", "x-nowpayments-sig": signature},
    )
    assert r.status_code == 200, r.text

    sub_after = await _get_subscription(shop_id)
    assert sub_after.status == SubStatus.active
    assert sub_after.provider == SubProvider.crypto
    assert sub_after.auto_renew is False
    assert sub_after.current_period_end > sub_before.current_period_end


@pytest.mark.asyncio
async def test_nowpayments_ipn_duplicate_does_not_extend_period_twice(client: AsyncClient) -> None:
    """Регресія (Стадія 5c): NOWPayments може доставити той самий IPN
    повторно — той самий payment_id має продовжити період лише один раз."""
    _init_data, shop_id = await _bootstrap(client, 6014)

    order_id = build_ref(shop_id, "basic", "month")
    payload = _nowpayments_ipn_payload(order_id=order_id, payment_id="np-dup-1")
    body = json.dumps(payload).encode()
    signature = _nowpayments_sign(TEST_NOWPAYMENTS_IPN_SECRET, body)
    headers = {"Content-Type": "application/json", "x-nowpayments-sig": signature}

    r1 = await client.post("/webhook/nowpayments", content=body, headers=headers)
    assert r1.status_code == 200, r1.text
    sub_after_first = await _get_subscription(shop_id)

    r2 = await client.post("/webhook/nowpayments", content=body, headers=headers)
    assert r2.status_code == 200, r2.text
    sub_after_second = await _get_subscription(shop_id)

    assert sub_after_second.current_period_end == sub_after_first.current_period_end

    async with db.async_session() as session:
        payments_count = await session.scalar(
            select(func.count(Payment.id)).where(Payment.shop_id == shop_id)
        )
    assert payments_count == 1


@pytest.mark.asyncio
async def test_nowpayments_ipn_invalid_signature_does_not_activate(client: AsyncClient) -> None:
    _init_data, shop_id = await _bootstrap(client, 6007)

    order_id = build_ref(shop_id, "basic", "month")
    payload = _nowpayments_ipn_payload(order_id=order_id)
    body = json.dumps(payload).encode()

    r = await client.post(
        "/webhook/nowpayments",
        content=body,
        headers={"Content-Type": "application/json", "x-nowpayments-sig": "0" * 128},
    )
    assert r.status_code == 400

    sub = await _get_subscription(shop_id)
    assert sub.status == SubStatus.trial


@pytest.mark.asyncio
async def test_nowpayments_ipn_not_finished_status_does_not_activate(client: AsyncClient) -> None:
    _init_data, shop_id = await _bootstrap(client, 6008)

    order_id = build_ref(shop_id, "basic", "month")
    payload = _nowpayments_ipn_payload(order_id=order_id, payment_status="waiting")
    body = json.dumps(payload).encode()
    signature = _nowpayments_sign(TEST_NOWPAYMENTS_IPN_SECRET, body)

    r = await client.post(
        "/webhook/nowpayments",
        content=body,
        headers={"Content-Type": "application/json", "x-nowpayments-sig": signature},
    )
    assert r.status_code == 200  # валідний підпис, просто ще не фінальний статус

    sub = await _get_subscription(shop_id)
    assert sub.status == SubStatus.trial


@pytest.mark.asyncio
async def test_wfp_callback_isolation_resolves_correct_shop(client: AsyncClient) -> None:
    _init_a, shop_a = await _bootstrap(client, 6009, "Шоп А")
    _init_b, shop_b = await _bootstrap(client, 6010, "Шоп Б")

    sub_b_before = await _get_subscription(shop_b)

    order_ref = build_ref(shop_a, "basic", "month")
    payload = _wfp_callback_payload(order_ref=order_ref)
    r = await client.post("/webhook/wayforpay", json=payload)
    assert r.status_code == 200

    sub_a_after = await _get_subscription(shop_a)
    sub_b_after = await _get_subscription(shop_b)
    assert sub_a_after.status == SubStatus.active
    assert sub_b_after.status == SubStatus.trial
    assert sub_b_after.current_period_end == sub_b_before.current_period_end


@pytest.mark.asyncio
async def test_record_payment_only_called_from_webhooks_not_checkout(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[object] = []
    original = SubscriptionService.record_payment

    async def _spy(self, *args, **kwargs):
        calls.append(args)
        return await original(self, *args, **kwargs)

    monkeypatch.setattr(SubscriptionService, "record_payment", _spy)

    init_data, shop_id = await _bootstrap(client, 6011)

    r_card = await client.post(
        "/api/billing/checkout/card",
        json={"plan_code": "basic", "period": "month"},
        headers={HEADER: init_data},
    )
    assert r_card.status_code == 200, r_card.text
    assert calls == []

    _RecordingNowPaymentsClient.calls.clear()
    monkeypatch.setattr(httpx, "AsyncClient", _RecordingNowPaymentsClient)
    r_crypto = await client.post(
        "/api/billing/checkout/crypto",
        json={"plan_code": "basic", "period": "month"},
        headers={HEADER: init_data},
    )
    assert r_crypto.status_code == 200, r_crypto.text
    assert calls == []

    order_ref = build_ref(shop_id, "basic", "month")
    payload = _wfp_callback_payload(order_ref=order_ref)
    r_webhook = await client.post("/webhook/wayforpay", json=payload)
    assert r_webhook.status_code == 200, r_webhook.text
    assert len(calls) == 1
