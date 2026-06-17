"""
SkladBase — видача API-ключа і налаштування вебхука магазину (Стадія 4):
обидва секрети зберігаються лише зашифрованими (AES-256-GCM).

Plaintext повертається ВИКЛИКАЧУ ОДИН РАЗ (при генерації/ротації) — у БД
лишається тільки шифротекст.
"""
from __future__ import annotations

import secrets

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Shop
from app.security.crypto import encrypt

_PREFIX_LEN = 8


async def generate_api_key(session: AsyncSession, shop: Shop) -> str:
    """Видає новий ключ, перезаписуючи попередній (ротація — старий ключ одразу
    стає невалідним, бо `api_key_prefix`/`api_key_encrypted` перезаписуються)."""
    plaintext = secrets.token_urlsafe(32)
    shop.api_key_encrypted = encrypt(plaintext)
    shop.api_key_prefix = plaintext[:_PREFIX_LEN]
    await session.commit()
    return plaintext


async def set_webhook(session: AsyncSession, shop: Shop, url: str) -> str:
    """Налаштовує/ротує вебхук на сайт: повертає новий secret один раз —
    далі лише `webhook_secret_encrypted` зберігається в БД."""
    secret = secrets.token_urlsafe(32)
    shop.webhook_url = url
    shop.webhook_secret_encrypted = encrypt(secret)
    await session.commit()
    return secret
