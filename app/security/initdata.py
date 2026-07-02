"""
Валідація Telegram WebApp `initData`.

Алгоритм (офіційний, https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app):
  1. secret_key = HMAC_SHA256(key=b"WebAppData", msg=bot_token)
  2. data_check_string = відсортовані за ключем "key=value" пари (крім "hash"),
     зʼєднані через "\n"
  3. очікуваний hash = HMAC_SHA256(key=secret_key, msg=data_check_string).hexdigest()
  4. порівняти з отриманим "hash" константним за часом порівнянням

shop_id у системі ЗАВЖДИ виводиться з tg_id, здобутого тут — ніколи з тіла
чи параметрів запиту (CLAUDE.md, інваріант №1).
"""
from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qsl

DEFAULT_MAX_AGE = timedelta(hours=24)


class InitDataError(Exception):
    """Невалідний, нерозбірливий або протермінований initData."""


@dataclass(frozen=True)
class TelegramUser:
    id: int
    first_name: str
    last_name: str | None = None
    username: str | None = None
    language_code: str | None = None
    is_premium: bool = False


@dataclass(frozen=True)
class InitData:
    user: TelegramUser
    auth_date: datetime
    query_id: str | None = None
    start_param: str | None = None


def _expected_hash(data_check_string: str, bot_token: str) -> str:
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    return hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()


def validate_init_data(
    raw: str,
    bot_token: str,
    *,
    max_age: timedelta = DEFAULT_MAX_AGE,
) -> InitData:
    """Перевіряє підпис і свіжість `raw` (query-string initData з Telegram WebApp).

    Кидає InitDataError за будь-якої невідповідності — викликач (deps.py)
    перетворює це на HTTP 401.
    """
    if not bot_token:
        raise InitDataError("BOT_TOKEN не налаштований")
    if not raw:
        raise InitDataError("initData відсутній")

    fields = dict(parse_qsl(raw, keep_blank_values=True, strict_parsing=False))

    received_hash = fields.pop("hash", None)
    if not received_hash:
        raise InitDataError("hash відсутній у initData")

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    expected = _expected_hash(data_check_string, bot_token)
    if not hmac.compare_digest(expected, received_hash):
        raise InitDataError("невалідний підпис initData")

    auth_date_raw = fields.get("auth_date")
    if not auth_date_raw:
        raise InitDataError("auth_date відсутній у initData")
    try:
        auth_date = datetime.fromtimestamp(int(auth_date_raw), tz=UTC)
    except (ValueError, OverflowError, OSError) as exc:
        raise InitDataError("auth_date некоректний") from exc

    if datetime.now(UTC) - auth_date > max_age:
        raise InitDataError("initData протермінований")

    user_raw = fields.get("user")
    if not user_raw:
        raise InitDataError("user відсутній у initData")
    try:
        user_data = json.loads(user_raw)
    except json.JSONDecodeError as exc:
        raise InitDataError("user — невалідний JSON") from exc

    try:
        user = TelegramUser(
            id=int(user_data["id"]),
            first_name=user_data.get("first_name", ""),
            last_name=user_data.get("last_name"),
            username=user_data.get("username"),
            language_code=user_data.get("language_code"),
            is_premium=bool(user_data.get("is_premium", False)),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise InitDataError("user — некоректна структура") from exc

    return InitData(
        user=user,
        auth_date=auth_date,
        query_id=fields.get("query_id"),
        start_param=fields.get("start_param"),
    )
