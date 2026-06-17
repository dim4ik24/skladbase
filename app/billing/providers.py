"""
SkladBase — адаптери платіжних провайдерів.

Кожен адаптер:
  * create_checkout()      -> повертає посилання/інвойс для оплати
  * verify/parse_webhook() -> валідує колбек і повертає нормалізований результат,
                              який потім згодовується SubscriptionService.record_payment()

ВАЖЛИВО (анти-overselling/анти-fraud): підписку активуємо ТІЛЬКИ з вебхука
провайдера, ніколи не з відповіді клієнта/Mini App.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from decimal import Decimal

import httpx
from aiogram import Bot
from aiogram.types import LabeledPrice

# Telegram вимагає фіксований період підписки = 30 діб.
STARS_SUBSCRIPTION_PERIOD = 2592000  # секунд


@dataclass
class PaymentResult:
    """Нормалізований результат успішної оплати від будь-якого провайдера."""
    provider: str
    amount: Decimal
    currency: str
    external_id: str
    is_recurring: bool
    auto_renew: bool
    period: str          # "month" | "year"
    plan_code: str       # який план оплачено (з payload)
    raw: dict
    shop_id: int | None = None  # з payload інвойсу — який магазин оплачено


# --------------------------------------------------------------------------- #
#  1. Telegram Stars — нативне авто-продовження                               #
# --------------------------------------------------------------------------- #
class StarsProvider:
    """
    Recurring через subscription_period. Продовження прилітає автоматично
    окремим апдейтом successful_payment з is_recurring=True.
    Скасування: editUserStarSubscription(is_canceled=True).
    """

    def __init__(self, bot: Bot):
        self.bot = bot

    async def create_checkout(
        self, *, shop_id: int, plan_code: str, price_stars: int, title: str
    ) -> str:
        """Повертає invoice-link для Mini App (openInvoice) чи кнопки.

        `shop_id` кладеться у payload інвойсу — це єдиний детермінований спосіб
        потім (у `successful_payment`) зарахувати оплату саме цьому магазину,
        а не вгадувати його за tg_id платника (власник може мати кілька шопів)."""
        payload = json.dumps({"shop_id": shop_id, "plan": plan_code, "period": "month"})
        return await self.bot.create_invoice_link(
            title=title,
            description="Підписка SkladBase (продовжується щомісяця)",
            payload=payload,
            currency="XTR",                       # Telegram Stars
            prices=[LabeledPrice(label=title, amount=price_stars)],
            subscription_period=STARS_SUBSCRIPTION_PERIOD,
        )

    async def cancel(self, user_tg_id: int, charge_id: str) -> None:
        await self.bot.edit_user_star_subscription(
            user_id=user_tg_id,
            telegram_payment_charge_id=charge_id,
            is_canceled=True,
        )

    @staticmethod
    def parse_successful_payment(sp: object, payload_raw: str) -> PaymentResult:
        """sp = message.successful_payment (aiogram SuccessfulPayment)."""
        meta = json.loads(payload_raw) if payload_raw else {}
        is_recurring = bool(getattr(sp, "is_recurring", False))
        return PaymentResult(
            provider="stars",
            amount=Decimal(getattr(sp, "total_amount", 0)),       # у Stars
            currency="XTR",
            external_id=getattr(sp, "telegram_payment_charge_id", ""),
            is_recurring=is_recurring,
            auto_renew=True,                       # Stars сам продовжує
            period="month",
            plan_code=meta.get("plan", "basic"),
            shop_id=meta.get("shop_id"),
            raw={
                "is_first_recurring": getattr(sp, "is_first_recurring", False),
                "subscription_expiration_date": getattr(sp, "subscription_expiration_date", None),
            },
        )


# --------------------------------------------------------------------------- #
#  2. WayForPay — картка з токеном (авто-списання робимо ми)                  #
# --------------------------------------------------------------------------- #
class WayForPayProvider:
    """
    Перша оплата: regularBehavior + збереження recToken.
    Авто-списання: крон викликає charge() з recToken щомісяця/щороку.
    Підпис: HMAC-MD5 по ';'-joined полях (вимога WayForPay).
    """
    API = "https://api.wayforpay.com/api"

    def __init__(self, merchant: str, secret: str, domain: str):
        self.merchant = merchant
        self.secret = secret
        self.domain = domain

    def _sign(self, fields: list[str | int]) -> str:
        msg = ";".join(str(f) for f in fields)
        return hmac.new(self.secret.encode(), msg.encode(), hashlib.md5).hexdigest()

    async def create_checkout(
        self, *, order_ref: str, amount: Decimal, plan_code: str, period: str, product: str
    ) -> dict:
        """Повертає тіло форми для редіректу на сторінку оплати WayForPay."""
        order_date = int(__import__("time").time())
        sign = self._sign([
            self.merchant, self.domain, order_ref, order_date,
            f"{amount:.2f}", "UAH", product, "1", f"{amount:.2f}",
        ])
        return {
            "merchantAccount": self.merchant,
            "merchantDomainName": self.domain,
            "orderReference": order_ref,
            "orderDate": order_date,
            "amount": f"{amount:.2f}",
            "currency": "UAH",
            "productName": [product],
            "productCount": [1],
            "productPrice": [f"{amount:.2f}"],
            "regularBehavior": "preset",
            "regularMode": "monthly" if period == "month" else "yearly",
            "merchantSignature": sign,
        }

    async def charge_recurring(self, *, rec_token: str, order_ref: str, amount: Decimal) -> dict:
        """Авто-списання по збереженому токену (викликає крон)."""
        payload = {
            "requestType": "CHARGE",
            "merchantAccount": self.merchant,
            "merchantSignature": self._sign([self.merchant, order_ref, f"{amount:.2f}", "UAH"]),
            "orderReference": order_ref,
            "amount": f"{amount:.2f}",
            "currency": "UAH",
            "recToken": rec_token,
        }
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(self.API, json=payload)
            return r.json()

    def verify_callback(self, data: dict) -> bool:
        expected = self._sign([
            data["merchantAccount"], data["orderReference"], data["amount"],
            data["currency"], data["authCode"], data["cardPan"],
            data["transactionStatus"], data["reasonCode"],
        ])
        return hmac.compare_digest(expected, data.get("merchantSignature", ""))

    def parse_callback(self, data: dict, *, plan_code: str, period: str) -> PaymentResult:
        return PaymentResult(
            provider="card",
            amount=Decimal(str(data["amount"])),
            currency=data.get("currency", "UAH"),
            external_id=data.get("recToken") or data["orderReference"],
            is_recurring=False,
            auto_renew=True,           # ми зберегли recToken -> зможемо продовжувати
            period=period,
            plan_code=plan_code,
            raw=data,
        )

    def build_accept_response(self, order_ref: str) -> dict:
        """Підтвердження прийому колбека: WFP чекає у відповідь
        {orderReference, status, time, signature}, інакше вважає вебхук
        невручениим і повторює доставку."""
        ts = int(time.time())
        signature = self._sign([order_ref, "accept", ts])
        return {
            "orderReference": order_ref,
            "status": "accept",
            "time": ts,
            "signature": signature,
        }


# --------------------------------------------------------------------------- #
#  3. NOWPayments — крипта (РАЗОВО, без авто-списання)                        #
# --------------------------------------------------------------------------- #
class NowPaymentsProvider:
    """
    Авто-списання з гаманця неможливе -> auto_renew завжди False.
    Підходить для річної (та опц. місячної) підписки. Перед закінченням
    крон шле нагадування 'оплати ще раз'.
    IPN підписується HMAC-SHA512 по відсортованому JSON.
    """
    API = "https://api.nowpayments.io/v1"

    def __init__(self, api_key: str, ipn_secret: str):
        self.api_key = api_key
        self.ipn_secret = ipn_secret

    async def create_checkout(
        self, *, order_id: str, amount_usd: Decimal, plan_code: str, period: str, pay_currency: str = "usdttrc20"
    ) -> dict:
        payload = {
            "price_amount": float(amount_usd),
            "price_currency": "usd",
            "pay_currency": pay_currency,
            "order_id": order_id,
            "order_description": f"SkladBase {plan_code}/{period}",
        }
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(
                f"{self.API}/payment",
                json=payload,
                headers={"x-api-key": self.api_key},
            )
            return r.json()

    def verify_ipn(self, raw_body: bytes, signature: str) -> bool:
        sorted_json = json.dumps(json.loads(raw_body), separators=(",", ":"), sort_keys=True)
        expected = hmac.new(self.ipn_secret.encode(), sorted_json.encode(), hashlib.sha512).hexdigest()
        return hmac.compare_digest(expected, signature)

    def parse_ipn(self, data: dict, *, plan_code: str, period: str) -> PaymentResult | None:
        if data.get("payment_status") not in ("finished", "confirmed"):
            return None
        return PaymentResult(
            provider="crypto",
            amount=Decimal(str(data["price_amount"])),
            currency="USD",
            external_id=str(data["payment_id"]),
            is_recurring=False,
            auto_renew=False,           # крипта не авто-продовжується
            period=period,
            plan_code=plan_code,
            raw=data,
        )
