"""
Stage 9a — прод-готовність: Postgres-конфіг, довіра до X-Forwarded-For за
проксі, і те, що web-процес не піднімає планувальник коли RUN_SCHEDULER=False
(той живе окремо в `app/worker.py`).
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine

import app.main as main_module
from app import db
from app.config import settings
from app.main import app as fastapi_app
from app.main import lifespan
from app.models import Shop
from app.security.proxy_headers import ProxyHeadersMiddleware
from tests.conftest import make_init_data

HEADER = "X-Telegram-Init-Data"


# --------------------------------------------------------------------------- #
#  Postgres: DATABASE_URL=postgresql+asyncpg резолвиться без хардкоду драйвера #
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_database_url_resolves_postgres_asyncpg_dialect() -> None:
    """`db.py` не хардкодить sqlite — той самий код шляху працює і для
    postgresql+asyncpg:// (реального коннекту тут не робимо, лише резолв
    діалекту/драйвера, щоб тест не залежав від живого Postgres)."""
    engine = create_async_engine("postgresql+asyncpg://user:pass@localhost:5432/skladbase")
    try:
        assert engine.dialect.name == "postgresql"
        assert engine.dialect.driver == "asyncpg"
    finally:
        await engine.dispose()


# --------------------------------------------------------------------------- #
#  ProxyHeadersMiddleware: довіра лише настроєним проксі                      #
# --------------------------------------------------------------------------- #
async def _noop_receive() -> dict:
    return {"type": "http.disconnect"}


async def _noop_send(_message: dict) -> None:
    pass


@pytest.mark.asyncio
async def test_proxy_middleware_rewrites_client_from_trusted_proxy() -> None:
    captured: dict[str, tuple[str, int]] = {}

    async def downstream(scope: dict, receive: object, send: object) -> None:
        captured["client"] = scope["client"]

    middleware = ProxyHeadersMiddleware(downstream, trusted_proxies=frozenset({"127.0.0.1"}))
    scope = {
        "type": "http",
        "client": ("127.0.0.1", 12345),
        "headers": [(b"x-forwarded-for", b"203.0.113.7, 127.0.0.1")],
    }
    await middleware(scope, _noop_receive, _noop_send)

    assert captured["client"] == ("203.0.113.7", 12345)


@pytest.mark.asyncio
async def test_proxy_middleware_ignores_header_from_untrusted_peer() -> None:
    captured: dict[str, tuple[str, int]] = {}

    async def downstream(scope: dict, receive: object, send: object) -> None:
        captured["client"] = scope["client"]

    middleware = ProxyHeadersMiddleware(downstream, trusted_proxies=frozenset({"127.0.0.1"}))
    scope = {
        "type": "http",
        "client": ("203.0.113.5", 555),  # не у списку довірених проксі
        "headers": [(b"x-forwarded-for", b"9.9.9.9")],
    }
    await middleware(scope, _noop_receive, _noop_send)

    assert captured["client"] == ("203.0.113.5", 555)  # заголовок ігнорується


# --------------------------------------------------------------------------- #
#  Інтеграція: лімітер ключиться по клієнтському IP з X-Forwarded-For,        #
#  а не по фіксованому IP тест-транспорта (= проксі)                          #
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_public_catalog_rate_limit_keys_by_forwarded_ip(client: AsyncClient) -> None:
    init_data = make_init_data(99001)
    r = await client.get("/api/me", headers={HEADER: init_data})
    assert r.status_code == 200
    shop_id = r.json()["shop_id"]

    async with db.async_session() as session:
        shop = await session.get(Shop, shop_id)
        assert shop is not None
        shop.public_catalog_enabled = True
        slug = shop.slug
        await session.commit()

    from app.api.public import _public_catalog_limiter

    statuses_a = []
    for _ in range(_public_catalog_limiter.max_requests + 1):
        r = await client.get(
            f"/api/public/{slug}", headers={"X-Forwarded-For": "203.0.113.9"}
        )
        statuses_a.append(r.status_code)

    assert statuses_a[:-1] == [200] * _public_catalog_limiter.max_requests
    assert statuses_a[-1] == 429

    # Тест-транспорт завжди підключається з того самого IP (= "проксі"). Якби
    # лімітер ключився по ньому, а не по X-Forwarded-For, цей запит теж був
    # би 429 — він не такий, отже ключ дійсно клієнтський IP.
    r_other_client = await client.get(
        f"/api/public/{slug}", headers={"X-Forwarded-For": "198.51.100.4"}
    )
    assert r_other_client.status_code == 200


# --------------------------------------------------------------------------- #
#  Lifespan: web-процес з RUN_SCHEDULER=False не піднімає планувальник         #
# --------------------------------------------------------------------------- #
class _FakeScheduler:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def start(self) -> None:
        self.calls.append("start")

    def shutdown(self, wait: bool = False) -> None:
        self.calls.append("shutdown")


@pytest.mark.asyncio
async def test_lifespan_skips_scheduler_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fail_if_called() -> _FakeScheduler:
        raise AssertionError("create_scheduler() не має викликатись при RUN_SCHEDULER=False")

    monkeypatch.setattr(main_module, "create_scheduler", _fail_if_called)
    monkeypatch.setattr(settings, "RUN_SCHEDULER", False)

    async with lifespan(fastapi_app):
        pass


@pytest.mark.asyncio
async def test_lifespan_starts_and_stops_scheduler_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeScheduler()
    monkeypatch.setattr(main_module, "create_scheduler", lambda: fake)
    monkeypatch.setattr(settings, "RUN_SCHEDULER", True)

    async with lifespan(fastapi_app):
        assert fake.calls == ["start"]

    assert fake.calls == ["start", "shutdown"]
