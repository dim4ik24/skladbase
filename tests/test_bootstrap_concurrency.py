"""
Фікс: ідемпотентність bootstrap_shop під конкурентним першим входом.

При першому вході нового tg_id кілька паралельних запитів TMA можуть
одночасно дійти до bootstrap_shop, не побачивши чужого ще не закомітченого
Membership, і всі спробувати створити Shop з однаковим slug `shop-{tg_id}`
-> UniqueViolationError для тих, хто програв гонку (раніше -> 500).

ПРИМІТКА (як і в test_stage3.py): SQLite серіалізує записи на рівні
зʼєднання, тож двома реальними паралельними корутинами цю гонку не
відтворити надійно. Другий тест симулює саме результат гонки: форсує
перший `_find_membership` у програвшого повернути None (так само, як
було б до коміту переможця), а далі його `session.flush()` падає зі
СПРАВЖНІМ IntegrityError на unique(slug), бо переможець уже закомітив
Shop з тим самим slug — рекавері-гілка bootstrap_shop обробляє це без
винятку назовні.
"""
from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app import db
from app.models import Shop
from app.security.initdata import TelegramUser
from app.services import bootstrap as bootstrap_module
from app.services.bootstrap import bootstrap_shop


@pytest.mark.asyncio
async def test_bootstrap_shop_repeat_call_returns_same_membership_no_duplicate_shop() -> None:
    user = TelegramUser(id=9001, first_name="Перший")

    async with db.async_session() as session:
        membership_1 = await bootstrap_shop(session, user)
    async with db.async_session() as session:
        membership_2 = await bootstrap_shop(session, user)

    assert membership_1.id == membership_2.id
    assert membership_1.shop_id == membership_2.shop_id

    async with db.async_session() as session:
        shops_count = await session.scalar(
            select(func.count(Shop.id)).where(Shop.owner_tg_id == user.id)
        )
    assert shops_count == 1


@pytest.mark.asyncio
async def test_bootstrap_shop_recovers_from_lost_race_without_raising(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = TelegramUser(id=9002, first_name="Гонка")

    # Переможець гонки вже закомітив свій Shop+Membership для цього tg_id.
    async with db.async_session() as winner_session:
        winner_membership = await bootstrap_shop(winner_session, user)

    real_find_membership = bootstrap_module._find_membership
    calls = {"n": 0}

    async def flaky_find_membership(session, tg_id):
        calls["n"] += 1
        if calls["n"] == 1:
            return None  # як і бачив би лузер гонки до коміту переможця
        return await real_find_membership(session, tg_id)

    monkeypatch.setattr(bootstrap_module, "_find_membership", flaky_find_membership)

    async with db.async_session() as loser_session:
        loser_membership = await bootstrap_shop(loser_session, user)

    assert loser_membership.id == winner_membership.id
    assert calls["n"] == 2  # початкова перевірка (None) + рекавері після IntegrityError

    async with db.async_session() as session:
        shops_count = await session.scalar(
            select(func.count(Shop.id)).where(Shop.owner_tg_id == user.id)
        )
    assert shops_count == 1
