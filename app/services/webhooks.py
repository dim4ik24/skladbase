"""
SkladBase — вихідний вебхук на сайт магазину при зміні залишків (Стадія 4b).

Best-effort: сайт власника може бути недоступний/повільним — це НЕ повинно
валити замовлення. Тому будь-яка мережева помилка/таймаут тут лише логується,
жодний виняток не пробивається до викликача. Через це функцію викликають
ПІСЛЯ commit транзакції, що змінила склад, — ніколи всередині неї.

Підпис: `X-Signature: HMAC-SHA256(webhook_secret, body)` — той самий принцип,
що й вхідні вебхуки білінгу (`app/billing/providers.py`), але навпаки: тут МИ
підписуємо вихідний запит, щоб сайт міг перевірити автентичність.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging

import httpx

from app.models import Shop, Variant
from app.security.crypto import CryptoError, decrypt

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(3.0)


def _build_payload(variants: list[Variant]) -> dict:
    return {
        "variants": [
            {
                "variant_id": variant.id,
                "available": variant.available,
                "in_stock": variant.available > 0,
            }
            for variant in variants
        ]
    }


async def dispatch_stock_changed(shop: Shop, variants: list[Variant]) -> None:
    """Сповіщає `shop.webhook_url` про зміну залишків. Якщо вебхук не
    налаштований або список варіантів порожній — нічого не робить."""
    if not shop.webhook_url or not shop.webhook_secret_encrypted or not variants:
        return

    try:
        secret = decrypt(shop.webhook_secret_encrypted)
    except CryptoError:
        logger.warning("shop %s: невалідний webhook_secret, вебхук не відправлено", shop.id)
        return

    body = json.dumps(_build_payload(variants), separators=(",", ":")).encode()
    signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            await client.post(
                shop.webhook_url,
                content=body,
                headers={"Content-Type": "application/json", "X-Signature": signature},
            )
    except httpx.HTTPError:
        logger.warning(
            "shop %s: вебхук %s не вдався", shop.id, shop.webhook_url, exc_info=True
        )
