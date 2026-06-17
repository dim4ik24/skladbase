"""
SkladBase — видача API-ключа магазину для server-to-server доступу з сайту
(Стадія 4, інваріант: per-shop API-ключ зберігається лише зашифрованим).

Plaintext повертається ВИКЛИКАЧУ ОДИН РАЗ (при генерації/ротації) — у БД
лишається тільки AES-256-GCM шифротекст (`api_key_encrypted`) і перші 8
символів відкритого ключа (`api_key_prefix`) для швидкого пошуку Shop без
розшифрування всіх рядків.
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
