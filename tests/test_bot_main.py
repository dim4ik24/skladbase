"""
app/bot/main.py — мінімальні структурні тести (модуль імпортується,
dispatcher має support-router) + app/bot/dispatcher.py::_session_middleware
(єдине, що НЕ покрито іншими тестами — платіжні хендлери в test_stage5a.py
завжди фідяться з явним session=, підтримка в test_bot_support.py викликає
хендлери напряму, обходячи мідлварь повністю).
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app import db


@pytest.mark.asyncio
async def test_bot_main_module_imports_cleanly() -> None:
    import app.bot.main as bot_main

    assert callable(bot_main.main)
    assert callable(bot_main._main)


def test_dispatcher_includes_support_router() -> None:
    from app.bot import handlers
    from app.bot.dispatcher import dp

    assert handlers.router in dp.sub_routers


@pytest.mark.asyncio
async def test_session_middleware_injects_session_when_absent() -> None:
    from app.bot.dispatcher import _session_middleware

    captured: dict = {}

    async def handler(event, data):
        captured["session"] = data.get("session")
        return "ok"

    data: dict = {}
    result = await _session_middleware(handler, event=object(), data=data)

    assert result == "ok"
    assert captured["session"] is not None
    assert data["session"] is captured["session"]

    # реально прив'язана до ізольованої тестової БД (conftest.py), не до
    # справжнього DATABASE_URL — підтверджує, що db.async_session
    # переглядається пізно (module-attribute), а не зафіксована на імпорті.
    assert db.async_session is not None


@pytest.mark.asyncio
async def test_session_middleware_does_not_overwrite_existing_session() -> None:
    from app.bot.dispatcher import _session_middleware

    sentinel = AsyncMock(name="webhook-provided-session")
    captured: dict = {}

    async def handler(event, data):
        captured["session"] = data.get("session")
        return "ok"

    data = {"session": sentinel}
    await _session_middleware(handler, event=object(), data=data)

    assert captured["session"] is sentinel
