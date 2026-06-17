"""
Stage 8 — hardening, окрім аудиту ізоляції (той у `tests/test_isolation.py`).

Криетрії:
  2. фото: Content-Length перевіряється ДО читання тіла -> 413 без повної
     буферизації файлу в памʼяті; нема заголовка -> capped-read зупиняється,
     не вичитуючи необмежений потік повністю.
  4. IntegrityError у catalog: підписується як "SKU" лише якщо це справді
     `uq_variant_shop_sku`, інакше — загальна помилка без оманливого тексту.
  5. rate limiting: /api/public/{slug}, вебхуки платежів, /webhook/telegram,
     bootstrap нового магазину -> 429 після перевищення ліміту.
  6. секрети at rest: у БД лише `*_encrypted`, ніколи plaintext; ключі не
     потрапляють у логи.
  7. необроблений виняток -> 500 без стектрейсу/внутрішніх деталей у тілі
     відповіді; ключові події (платіж, протермінування) логуються структуровано.
"""
from __future__ import annotations

from http import HTTPStatus

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app import db
from app.main import app
from app.models import Plan, Shop, SubProvider, Subscription
from app.services import media
from app.services.catalog import _is_sku_conflict
from app.services.shop import generate_api_key, set_webhook
from app.services.subscriptions import SubscriptionService
from tests.conftest import make_init_data

HEADER = "X-Telegram-Init-Data"


async def _bootstrap(client: AsyncClient, tg_id: int, name: str = "Тест") -> tuple[str, int]:
    init_data = make_init_data(tg_id, first_name=name)
    r = await client.get("/api/me", headers={HEADER: init_data})
    assert r.status_code == 200
    return init_data, r.json()["shop_id"]


# --------------------------------------------------------------------------- #
#  2. Фото: Content-Length ДО читання тіла, capped read                       #
# --------------------------------------------------------------------------- #
class _InfiniteStream:
    """Імітує необмежений потік (chunked-запит без Content-Length) — щоб
    довести, що `read_capped` зупиняється і НЕ читає його цілком."""

    def __init__(self, chunk: bytes) -> None:
        self._chunk = chunk
        self.reads = 0

    async def read(self, _n: int) -> bytes:
        self.reads += 1
        if self.reads > 10_000:  # запобіжник, щоб тест не завис, якщо cap не спрацював
            return b""
        return self._chunk


@pytest.mark.asyncio
async def test_read_capped_stops_without_buffering_unbounded_stream() -> None:
    stream = _InfiniteStream(b"x" * 1024)

    with pytest.raises(media.MediaError) as exc_info:
        await media.read_capped(stream, max_bytes=4096)  # type: ignore[arg-type]

    assert exc_info.value.status_code == HTTPStatus.REQUEST_ENTITY_TOO_LARGE
    assert stream.reads <= 6  # зупинились одразу після перевищення ліміту


@pytest.mark.asyncio
async def test_forged_content_length_rejected_before_reading_body(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Клієнт заявляє величезний Content-Length, але реально шле малий файл —
    запит має відхилятись по заявленому розміру (413), не дочитавши тіло."""
    from app.models import Product, Variant

    init_data, shop_id = await _bootstrap(client, 88001)
    async with db.async_session() as session:
        product = Product(shop_id=shop_id, name="Товар")
        session.add(product)
        await session.flush()
        variant = Variant(shop_id=shop_id, product_id=product.id, price=100)
        session.add(variant)
        await session.commit()
        variant_id = variant.id

    read_calls = 0
    original_read = media.read_capped

    async def _spy_read_capped(file: object, max_bytes: int) -> bytes:
        nonlocal read_calls
        read_calls += 1
        return await original_read(file, max_bytes)  # type: ignore[arg-type]

    monkeypatch.setattr(media, "read_capped", _spy_read_capped)

    request = client.build_request(
        "POST",
        f"/api/variants/{variant_id}/photo",
        files={"file": ("tiny.jpg", b"x" * 10, "image/jpeg")},
        headers={HEADER: init_data},
    )
    request.headers["content-length"] = str(50 * 1024 * 1024)  # 50 МБ, > лімиту
    r = await client.send(request)

    assert r.status_code == 413
    assert read_calls == 0  # до читання тіла не дійшло — відхилено по заголовку


# --------------------------------------------------------------------------- #
#  4. IntegrityError у catalog: лише SKU підписуємо як SKU                    #
# --------------------------------------------------------------------------- #
def test_is_sku_conflict_matches_sqlite_and_postgres_messages() -> None:
    sqlite_exc = IntegrityError(
        "INSERT INTO variants ...", {}, Exception("UNIQUE constraint failed: variants.shop_id, variants.sku")
    )
    postgres_exc = IntegrityError(
        "INSERT INTO variants ...",
        {},
        Exception('duplicate key value violates unique constraint "uq_variant_shop_sku"'),
    )
    unrelated_exc = IntegrityError(
        "INSERT INTO variants ...", {}, Exception("FOREIGN KEY constraint failed")
    )

    assert _is_sku_conflict(sqlite_exc) is True
    assert _is_sku_conflict(postgres_exc) is True
    assert _is_sku_conflict(unrelated_exc) is False


@pytest.mark.asyncio
async def test_non_sku_integrity_error_does_not_claim_sku(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    init_data, _shop_id = await _bootstrap(client, 88002)

    original_flush = AsyncSession.flush
    call_count = {"n": 0}

    async def _fake_flush(self: AsyncSession, *args: object, **kwargs: object) -> None:
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise IntegrityError(
                "INSERT INTO variants ...", {}, Exception("FOREIGN KEY constraint failed")
            )
        return await original_flush(self, *args, **kwargs)

    monkeypatch.setattr(AsyncSession, "flush", _fake_flush)

    payload = {"name": "Товар", "variants": [{"axis_values": {}, "price": "10"}]}
    r = await client.post("/api/products", json=payload, headers={HEADER: init_data})

    assert r.status_code == 409
    assert "SKU" not in r.json()["detail"]


# --------------------------------------------------------------------------- #
#  5. Rate limiting                                                           #
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_public_catalog_rate_limited(client: AsyncClient) -> None:
    _init_data, shop_id = await _bootstrap(client, 88101)
    async with db.async_session() as session:
        shop = await session.get(Shop, shop_id)
        assert shop is not None
        shop.public_catalog_enabled = True
        slug = shop.slug
        await session.commit()

    from app.api.public import _public_catalog_limiter

    statuses = []
    for _ in range(_public_catalog_limiter.max_requests + 1):
        r = await client.get(f"/api/public/{slug}")
        statuses.append(r.status_code)

    assert statuses[:-1] == [200] * _public_catalog_limiter.max_requests
    assert statuses[-1] == 429


@pytest.mark.asyncio
async def test_telegram_webhook_rate_limited(client: AsyncClient) -> None:
    from app.api.telegram import _telegram_webhook_limiter

    statuses = []
    for i in range(_telegram_webhook_limiter.max_requests + 1):
        r = await client.post("/webhook/telegram", json={"update_id": 10_000 + i})
        statuses.append(r.status_code)

    assert statuses[-1] == 429
    assert all(s == 200 for s in statuses[:-1])


@pytest.mark.asyncio
async def test_payment_webhooks_rate_limited(client: AsyncClient) -> None:
    from app.api.payment_webhooks import _nowpayments_limiter, _wayforpay_limiter

    statuses_wfp = []
    for _ in range(_wayforpay_limiter.max_requests + 1):
        r = await client.post("/webhook/wayforpay", json={})
        statuses_wfp.append(r.status_code)
    assert statuses_wfp[-1] == 429
    assert all(s == 400 for s in statuses_wfp[:-1])

    statuses_np = []
    for _ in range(_nowpayments_limiter.max_requests + 1):
        r = await client.post("/webhook/nowpayments", json={})
        statuses_np.append(r.status_code)
    assert statuses_np[-1] == 429
    assert all(s == 400 for s in statuses_np[:-1])


@pytest.mark.asyncio
async def test_bootstrap_path_rate_limited(client: AsyncClient) -> None:
    from app.deps import _bootstrap_limiter

    statuses = []
    base_tg_id = 9_000_000
    for i in range(_bootstrap_limiter.max_requests + 1):
        init_data = make_init_data(base_tg_id + i)
        r = await client.get("/api/me", headers={HEADER: init_data})
        statuses.append(r.status_code)

    assert statuses[:-1] == [200] * _bootstrap_limiter.max_requests
    assert statuses[-1] == 429


# --------------------------------------------------------------------------- #
#  6. Секрети at rest + не логуються                                          #
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_api_key_and_webhook_secret_stored_only_encrypted(
    client: AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    _init_data, shop_id = await _bootstrap(client, 88201)

    async with db.async_session() as session:
        shop = await session.get(Shop, shop_id)
        assert shop is not None
        with caplog.at_level("DEBUG"):
            plaintext_key = await generate_api_key(session, shop)
            plaintext_secret = await set_webhook(session, shop, "https://example.test/hook")

    async with db.async_session() as session:
        shop_row = await session.get(Shop, shop_id)
        assert shop_row is not None
        # у БД лише шифротекст, ніколи рівно plaintext
        assert shop_row.api_key_encrypted is not None
        assert shop_row.api_key_encrypted != plaintext_key
        assert plaintext_key not in shop_row.api_key_encrypted
        assert shop_row.webhook_secret_encrypted is not None
        assert shop_row.webhook_secret_encrypted != plaintext_secret
        assert plaintext_secret not in shop_row.webhook_secret_encrypted

    # plaintext-секрети ніколи не потрапляють у лог-рекорди генерації/ротації
    for record in caplog.records:
        assert plaintext_key not in record.getMessage()
        assert plaintext_secret not in record.getMessage()


# --------------------------------------------------------------------------- #
#  7. 500 без стектрейсу; структуровані логи ключових подій                   #
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_unhandled_exception_returns_generic_500_without_internal_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("boom — секретні внутрішні деталі, які НЕ мають піти клієнту")

    monkeypatch.setattr("app.deps.validate_init_data", _boom)

    init_data = make_init_data(88301)
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test"
    ) as raw_client:
        r = await raw_client.get("/api/me", headers={HEADER: init_data})

    assert r.status_code == 500
    body = r.text
    assert "boom" not in body
    assert "RuntimeError" not in body
    assert "Traceback" not in body
    assert "deps.py" not in body


@pytest.mark.asyncio
async def test_payment_recorded_and_expiry_are_logged_with_structured_fields(
    caplog: pytest.LogCaptureFixture,
) -> None:
    async with db.async_session() as session:
        shop = Shop(owner_tg_id=1, name="Т", slug="t-log-1")
        session.add(shop)
        await session.flush()

        plan = await session.scalar(select(Plan).where(Plan.code == "basic"))
        if plan is None:
            from app.seed import seed_plans

            await seed_plans(session)
            plan = await session.scalar(select(Plan).where(Plan.code == "basic"))
        assert plan is not None

        sub = Subscription(shop_id=shop.id)
        session.add(sub)
        await session.flush()

        svc = SubscriptionService(session)
        with caplog.at_level("INFO"):
            await svc.record_payment(
                sub,
                provider=SubProvider.stars,
                plan=plan,
                period=sub.period,
                amount=plan.price_uah,
                currency="XTR",
                transaction_id="charge-log-1",
                recurring_token=None,
                is_recurring=False,
                auto_renew=False,
            )
            await svc.expire(sub)
        await session.commit()

    events = [getattr(r, "event", None) for r in caplog.records]
    assert "payment_recorded" in events
    assert "subscription_expired" in events

    payment_record = next(r for r in caplog.records if getattr(r, "event", None) == "payment_recorded")
    assert payment_record.shop_id == shop.id
    assert payment_record.transaction_id == "charge-log-1"

    expiry_record = next(r for r in caplog.records if getattr(r, "event", None) == "subscription_expired")
    assert expiry_record.shop_id == shop.id
