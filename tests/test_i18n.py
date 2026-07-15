"""
i18n Стадія 4 (бекенд): msg()/ServiceError відкладений рендер, мова запиту
з X-App-Language, мова бота з Telegram language_code / Shop.owner_language_code.

Не re-тестує повноту самих перекладів (за це відповідає
frontend/scripts/check-locales.mjs) — лише сам МЕХАНІЗМ: чи резолвиться
правильна мова, чи є коректний fallback на uk, чи tasks.py/handlers.py
справді дістають мову з правильного джерела.
"""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from httpx import AsyncClient

from app import db, tasks
from app.bot import handlers
from app.i18n import ServiceError, lang_from_telegram_code, msg
from app.models import MemberRole, Membership, Product, Role, Shop, Variant


# --------------------------------------------------------------------------- #
#  msg() — юніт
# --------------------------------------------------------------------------- #
def test_msg_returns_requested_language() -> None:
    assert msg("catalog.product_not_found", "en") == "Product not found"
    assert msg("catalog.product_not_found", "ru") == "Товар не найден"
    assert msg("catalog.product_not_found", "uk") == "Товар не знайдено"


def test_msg_falls_back_to_uk_for_unsupported_language() -> None:
    assert msg("catalog.product_not_found", "de") == msg("catalog.product_not_found", "uk")


def test_msg_defaults_to_uk_when_lang_omitted() -> None:
    assert msg("catalog.product_not_found") == "Товар не знайдено"


def test_msg_falls_back_to_raw_key_for_unknown_key() -> None:
    assert msg("does.not.exist", "en") == "does.not.exist"


def test_msg_interpolates_fmt_kwargs() -> None:
    assert msg("orders.variant_not_found", "en", variant_id=42) == "Variant 42 not found"


def test_msg_key_param_does_not_collide_with_fmt_key_kwarg() -> None:
    """template.key_required має плейсхолдер {key!r} — власний параметр
    msg()/ServiceError теж зветься `key`. Без positional-only (`/`) виклик
    msg("template.key_required", "en", key="") падав би з
    "got multiple values for argument 'key'" (реальний баг, зловлений mypy
    під час цієї стадії — app/i18n.py, ServiceError.__init__ докстрінг)."""
    text = msg("template.key_required", "en", key="")
    assert "''" in text


# --------------------------------------------------------------------------- #
#  ServiceError.detail(lang) — юніт
# --------------------------------------------------------------------------- #
def test_service_error_detail_renders_requested_language() -> None:
    err = ServiceError(404, "catalog.product_not_found")
    assert err.detail("en") == "Product not found"
    assert err.detail("ru") == "Товар не найден"
    assert err.detail() == "Товар не знайдено"


def test_service_error_raw_passthrough_ignores_lang() -> None:
    err = ServiceError(422, raw="НП: мережева помилка")
    assert err.detail("en") == "НП: мережева помилка"
    assert err.detail("uk") == "НП: мережева помилка"


def test_service_error_requires_exactly_one_of_key_or_raw() -> None:
    with pytest.raises(TypeError):
        ServiceError(400)
    with pytest.raises(TypeError):
        ServiceError(400, "catalog.product_not_found", raw="also raw")


# --------------------------------------------------------------------------- #
#  lang_from_telegram_code — юніт
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "code,expected",
    [
        (None, "uk"),
        ("", "uk"),
        ("uk", "uk"),
        ("en", "en"),
        ("en-US", "en"),
        ("ru", "ru"),
        ("ru-RU", "ru"),
        ("de", "uk"),
    ],
)
def test_lang_from_telegram_code(code: str | None, expected: str) -> None:
    assert lang_from_telegram_code(code) == expected


# --------------------------------------------------------------------------- #
#  X-App-Language -> HTTPException.detail (інтеграційно, публічний ендпоінт,
#  без auth — найпростіший шлях перевірити сам механізм заголовка)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_public_404_defaults_to_ukrainian_without_header(client: AsyncClient) -> None:
    response = await client.get("/api/public/does-not-exist")
    assert response.status_code == 404
    assert response.json()["detail"] == "Каталог не знайдено"


@pytest.mark.asyncio
async def test_public_404_respects_x_app_language_header(client: AsyncClient) -> None:
    response = await client.get(
        "/api/public/does-not-exist", headers={"X-App-Language": "en"}
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Catalog not found"

    response_ru = await client.get(
        "/api/public/does-not-exist", headers={"X-App-Language": "ru"}
    )
    assert response_ru.json()["detail"] == "Каталог не найден"


@pytest.mark.asyncio
async def test_public_404_unsupported_language_falls_back_to_ukrainian(
    client: AsyncClient,
) -> None:
    response = await client.get(
        "/api/public/does-not-exist", headers={"X-App-Language": "fr"}
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Каталог не знайдено"


# --------------------------------------------------------------------------- #
#  Бот: support-флоу бере мову з live message.from_user.language_code
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_cmd_start_uses_telegram_language_code(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "MINI_APP_URL", "")
    message = MagicMock()
    message.from_user = MagicMock(language_code="en")
    message.answer = AsyncMock()

    await handlers.cmd_start(message)

    text = message.answer.call_args.args[0]
    assert text == "Welcome to SkladBase! Tap the button below to open the app."


@pytest.mark.asyncio
async def test_admin_reply_translates_for_english_target_user() -> None:
    """Обгортка "💬 Відповідь підтримки:" перекладається за мовою ЮЗЕРА
    (SupportTarget.lang, знятою при вхідному зверненні), НЕ адміна — сам
    текст відповіді (вільний ввід адміна) лишається як є."""
    from app.config import settings

    handlers.support_map.clear()
    handlers.support_map[701] = handlers.SupportTarget(2002, "Test", "en")
    reply_to = MagicMock(message_id=701)
    admin_message = MagicMock()
    admin_message.from_user = MagicMock(id=settings.ADMIN_TG_ID, language_code="uk")
    admin_message.text = "Try updating the app"
    admin_message.caption = None
    admin_message.reply_to_message = reply_to
    bot = AsyncMock()

    try:
        await handlers.admin_reply(admin_message, bot)
    finally:
        handlers.support_map.clear()

    bot.send_message.assert_awaited_once_with(
        2002, "💬 Support reply:\nTry updating the app"
    )


# --------------------------------------------------------------------------- #
#  Крон (app/tasks.py): мова з Shop.owner_language_code — немає live Update
# --------------------------------------------------------------------------- #
async def _make_shop(tg_id: int, *, owner_language_code: str = "uk") -> int:
    async with db.async_session() as session:
        shop = Shop(
            owner_tg_id=tg_id,
            name="Test Shop",
            slug=f"shop-{uuid4().hex[:8]}",
            owner_language_code=owner_language_code,
        )
        session.add(shop)
        await session.flush()
        role = Role(shop_id=shop.id, name="Власник", is_system=True)
        session.add(role)
        await session.flush()
        session.add(
            Membership(shop_id=shop.id, tg_id=tg_id, role=MemberRole.owner, role_id=role.id)
        )
        await session.commit()
        return shop.id


class _StubNotifier:
    def __init__(self) -> None:
        self.calls: list[tuple[int, str]] = []

    async def __call__(self, tg_id: int, text: str) -> None:
        self.calls.append((tg_id, text))


@pytest.mark.asyncio
async def test_low_stock_scan_uses_shop_owner_language_code() -> None:
    shop_id = await _make_shop(7101, owner_language_code="en")
    async with db.async_session() as session:
        product = Product(shop_id=shop_id, name="Widget")
        session.add(product)
        await session.flush()
        variant = Variant(
            shop_id=shop_id,
            product_id=product.id,
            sku=f"SKU-{uuid4().hex[:8]}",
            price=Decimal("10"),
            on_hand=2,
            low_stock_threshold=3,
        )
        session.add(variant)
        await session.commit()

    stub = _StubNotifier()
    async with db.async_session() as session:
        count = await tasks.low_stock_scan(session, stub)

    assert count == 1
    assert len(stub.calls) == 1
    tg_id, text = stub.calls[0]
    assert tg_id == 7101
    assert text == '📦 “Widget” is running low — 2 units left.'


@pytest.mark.asyncio
async def test_low_stock_scan_default_ukrainian_shop() -> None:
    shop_id = await _make_shop(7102)  # default owner_language_code="uk"
    async with db.async_session() as session:
        product = Product(shop_id=shop_id, name="Штука")
        session.add(product)
        await session.flush()
        variant = Variant(
            shop_id=shop_id,
            product_id=product.id,
            sku=f"SKU-{uuid4().hex[:8]}",
            price=Decimal("10"),
            on_hand=1,
            low_stock_threshold=3,
        )
        session.add(variant)
        await session.commit()

    stub = _StubNotifier()
    async with db.async_session() as session:
        await tasks.low_stock_scan(session, stub)

    assert stub.calls[0][1] == "📦 «Штука» закінчується — залишилось 1 одиниця."
