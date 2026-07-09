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
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app import db
from app.api import orders as orders_api
from app.config import settings
from app.main import app
from app.models import Base, Role
from app.security import rate_limit as rate_limit_module

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
    monkeypatch.setattr(settings, "RUN_SCHEDULER", False)
    monkeypatch.setattr(orders_api, "notifier", _noop_notifier)
    rate_limit_module.reset_all()  # лімітери — модульні синглтони, спільні між тестами

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
    start_param: str | None = None,
) -> str:
    """Будує query-string initData, підписаний так само, як це робить Telegram.

    `start_param` — те саме поле, що Telegram підставляє при відкритті TMA
    через `?startapp=...`; включається у підписаний data_check_string, як
    і в реальному initData (deep-link інвайти, Стадія 2а)."""
    fields = {
        "query_id": "AAFakeQueryId",
        "user": json.dumps({"id": tg_id, "first_name": first_name}, separators=(",", ":")),
        "auth_date": str(auth_date if auth_date is not None else int(time.time())),
    }
    if start_param is not None:
        fields["start_param"] = start_param
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    fields["hash"] = "0" * 64 if tamper_hash else computed_hash
    return urlencode(fields)


async def get_system_role_id(shop_id: int, name: str) -> int:
    """Id системної ролі шопу за назвою ("Власник"/"Менеджер") — bootstrap
    створює обидві разом із магазином. Тести, що вставляють Membership напряму
    в БД, мусять вказати role_id (non-nullable FK) — ця функція знаходить
    правильний, замість того щоб кожен тест-файл повторював той самий select."""
    async with db.async_session() as s:
        role_id = await s.scalar(
            select(Role.id).where(Role.shop_id == shop_id, Role.name == name)
        )
    assert role_id is not None, f"system role {name!r} missing for shop {shop_id}"
    return role_id
