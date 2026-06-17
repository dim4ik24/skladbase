"""
SkladBase — AES-256-GCM шифрування секретів at rest.

Зараз використовується для `Shop.api_key_encrypted` (Стадія 4: per-shop
API-ключ для серверного доступу з сайту). Ключ — `settings.ENCRYPTION_KEY`
(base64, рівно 32 байти -> AES-256).

Формат токена: base64url(nonce[12] || ciphertext) — `AESGCM.encrypt` сам
додає 16-байтний тег автентифікації в кінець ciphertext, тож зберігаємо
один блоб. Nonce генерується випадково на кожен викликом `encrypt()` —
однаковий plaintext завжди дає різний шифротекст.
"""
from __future__ import annotations

import base64
import binascii
import secrets

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import settings

_NONCE_SIZE = 12  # рекомендований NIST розмір nonce для AES-GCM


class CryptoError(Exception):
    """Невалідний ключ або токен (підроблений/пошкоджений шифротекст)."""


def _load_key() -> bytes:
    if not settings.ENCRYPTION_KEY:
        raise CryptoError("ENCRYPTION_KEY не налаштований")
    try:
        key = base64.b64decode(settings.ENCRYPTION_KEY)
    except binascii.Error as exc:
        raise CryptoError("ENCRYPTION_KEY — невалідний base64") from exc
    if len(key) != 32:
        raise CryptoError("ENCRYPTION_KEY має бути 32 байти (AES-256)")
    return key


def encrypt(plaintext: str) -> str:
    key = _load_key()
    nonce = secrets.token_bytes(_NONCE_SIZE)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext.encode(), None)
    return base64.urlsafe_b64encode(nonce + ciphertext).decode()


def decrypt(token: str) -> str:
    key = _load_key()
    try:
        raw = base64.urlsafe_b64decode(token)
    except binascii.Error as exc:
        raise CryptoError("невалідний токен") from exc
    if len(raw) <= _NONCE_SIZE:
        raise CryptoError("невалідний токен")

    nonce, ciphertext = raw[:_NONCE_SIZE], raw[_NONCE_SIZE:]
    try:
        plaintext = AESGCM(key).decrypt(nonce, ciphertext, None)
    except InvalidTag as exc:
        raise CryptoError("не вдалося розшифрувати — невалідний токен або ключ") from exc
    return plaintext.decode()
