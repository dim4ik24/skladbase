"""Спільні фікстури для тестів: ізольована in-memory БД на кожен тест +
хелпер для побудови валідно підписаного Telegram initData."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from collections.abc import AsyncGenerator
from urllib.parse import urlencode

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app import db
from app.api import orders as orders_api
from app.config import settings
from app.main import app
from app.models import Base

TEST_BOT_TOKEN = "123456:TEST-BOT-TOKEN"
TEST_ENCRYPTION_KEY = base64.b64encode(secrets.token_bytes(32)).decode()


async def _noop_notifier(tg_id: int, text: str) -> None:
    """За замовчуванням нотифікації — no-op у тестах: BOT_TOKEN тут фейковий
    (потрібен лише для HMAC initData), реальний Telegram API недосяжний."""


@pytest.fixture(autouse=True)
async def _isolated_db(monkeypatch: pytest.MonkeyPatch) -> AsyncGenerator[None, None]:
    test_engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    test_session = async_sessionmaker(test_engine, expire_on_commit=False)

    monkeypatch.setattr(db, "engine", test_engine)
    monkeypatch.setattr(db, "async_session", test_session)
    monkeypatch.setattr(settings, "BOT_TOKEN", TEST_BOT_TOKEN)
    monkeypatch.setattr(settings, "ENCRYPTION_KEY", TEST_ENCRYPTION_KEY)
    monkeypatch.setattr(orders_api, "notifier", _noop_notifier)

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield

    await test_engine.dispose()


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


def make_init_data(
    tg_id: int,
    *,
    first_name: str = "Тест",
    auth_date: int | None = None,
    bot_token: str = TEST_BOT_TOKEN,
    tamper_hash: bool = False,
) -> str:
    """Будує query-string initData, підписаний так само, як це робить Telegram."""
    fields = {
        "query_id": "AAFakeQueryId",
        "user": json.dumps({"id": tg_id, "first_name": first_name}, separators=(",", ":")),
        "auth_date": str(auth_date if auth_date is not None else int(time.time())),
    }
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    fields["hash"] = "0" * 64 if tamper_hash else computed_hash
    return urlencode(fields)
