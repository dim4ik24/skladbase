"""
SkladBase — друкує валідно підписаний Telegram WebApp initData для
фіксованого тестового tg_id (Стадія 7a).

Призначення: значення для `VITE_DEV_INIT_DATA` у frontend/app/.env, щоб
фронтенд можна було розробляти поза реальним Telegram-клієнтом.

Підпис рахується тим самим BOT_TOKEN, що й бекенд (app/config.py, .env) —
та самою формулою, що й app/security/initdata.py. Якщо BOT_TOKEN порожній,
валідний initData згенерувати неможливо.

Запуск:
    python scripts/dev_initdata.py [tg_id]
"""
from __future__ import annotations

import hashlib
import hmac
import json
import sys
import time
from pathlib import Path
from urllib.parse import urlencode

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings

DEFAULT_TG_ID = 999999001


def build_init_data(tg_id: int, bot_token: str, *, first_name: str = "Dev") -> str:
    fields = {
        "query_id": "AADevQueryId",
        "user": json.dumps(
            {"id": tg_id, "first_name": first_name, "is_premium": False},
            separators=(",", ":"),
        ),
        "auth_date": str(int(time.time())),
    }
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


def main() -> None:
    if not settings.BOT_TOKEN:
        print(
            "BOT_TOKEN не налаштований у .env — підписати initData неможливо.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    tg_id = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_TG_ID
    print(build_init_data(tg_id, settings.BOT_TOKEN))


if __name__ == "__main__":
    main()
