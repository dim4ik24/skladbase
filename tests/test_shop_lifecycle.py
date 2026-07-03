"""
Shop lifecycle: явний онбординг (POST /api/shops) замість авто-bootstrap +
видалення магазину (DELETE /api/shop).

Сценарії:
  1. новий юзер без інвайта -> 404 no_shop, магазин НЕ створюється.
  2. POST /api/shops -> Shop + Membership(owner) + demo-каталог + 7-денний
     тріал; повторний виклик тим самим tg_id -> ДОЗВОЛЕНИЙ (multi-shop).
  3. новий юзер + валідний invite-токен -> joined, без авто-bootstrap.
  4. DELETE /api/shop: confirm_name, каскад по всіх shop-scoped таблицях,
     best-effort R2-видалення (мок).
  5. DELETE не-owner -> 403.
  6. Manager видаленого (єдиного) магазину -> 404 no_shop на наступному вході.
  7. Multi-shop: dead X-Shop-Id (видалений магазин) -> 403 "Немає доступу"
     (НЕ no_shop — інші membership'и є), без заголовка -> живий магазин.

R2-клієнт мокається (aioboto3.Session), реальний R2 не зачіпається.
"""
from __future__ import annotations

from datetime import UTC, timedelta
from decimal import Decimal

import aioboto3
import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app import db
from app.config import settings
from app.models import (
    Invite,
    MemberRole,
    Membership,
    MovementType,
    Order,
    OrderItem,
    OrderSource,
    OrderStatus,
    Product,
    ProductPhoto,
    ProductTemplate,
    Reservation,
    Shop,
    StockMovement,
    Subscription,
    SubStatus,
    Variant,
    utcnow,
)
from app.services.subscriptions import TRIAL_DAYS
from tests.conftest import make_init_data

HEADER = "X-Telegram-Init-Data"


# --------------------------------------------------------------------------- #
#  R2 mock (той самий патерн, що test_product_photos.py)
# --------------------------------------------------------------------------- #
class _FakeS3Client:
    calls: list[dict] = []

    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self) -> "_FakeS3Client":
        return self

    async def __aexit__(self, *exc_info) -> bool:
        return False

    async def put_object(self, **kwargs) -> dict:
        _FakeS3Client.calls.append({"op": "put", **kwargs})
        return {}

    async def delete_object(self, **kwargs) -> dict:
        _FakeS3Client.calls.append({"op": "delete", **kwargs})
        return {}


class _FakeR2Session:
    def __init__(self, *args, **kwargs) -> None:
        pass

    def client(self, *args, **kwargs) -> _FakeS3Client:
        return _FakeS3Client()


@pytest.fixture(autouse=True)
def _patch_r2(monkeypatch: pytest.MonkeyPatch) -> None:
    _FakeS3Client.calls.clear()
    monkeypatch.setattr(aioboto3, "Session", _FakeR2Session)
    monkeypatch.setattr(settings, "R2_PUBLIC_URL", "https://cdn.example.test")
    monkeypatch.setattr(settings, "R2_ACCOUNT_ID", "test-account")
    monkeypatch.setattr(settings, "R2_ACCESS_KEY", "test-access-key")
    monkeypatch.setattr(settings, "R2_SECRET_KEY", "test-secret-key")
    monkeypatch.setattr(settings, "R2_BUCKET", "test-bucket")


# --------------------------------------------------------------------------- #
#  Helpers
# --------------------------------------------------------------------------- #
async def _create_shop(client: AsyncClient, init_data: str, name: str = "Магазин") -> int:
    r = await client.post("/api/shops", headers={HEADER: init_data}, json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()["shop_id"]


async def _create_invite(client: AsyncClient, owner_init_data: str) -> dict:
    r = await client.post("/api/team/invites", headers={HEADER: owner_init_data})
    assert r.status_code == 201, r.text
    return r.json()


# --------------------------------------------------------------------------- #
#  1. Немає авто-bootstrap                                                    #
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_new_user_without_invite_gets_no_shop_404(client: AsyncClient) -> None:
    init_data = make_init_data(50001, first_name="Новий")
    r = await client.get("/api/me", headers={HEADER: init_data})
    assert r.status_code == 404

    async with db.async_session() as session:
        shops = (await session.scalars(select(Shop).where(Shop.owner_tg_id == 50001))).all()
    assert shops == []


@pytest.mark.asyncio
async def test_new_user_with_dead_invite_token_gets_no_shop_404(client: AsyncClient) -> None:
    """Мертвий/чужий-формату invite-токен для НОВОГО юзера — раніше все одно
    створював магазин (invite_status="invite_invalid"); тепер авто-bootstrap-у
    нема взагалі, тож теж 404, а не тихе створення."""
    init_data = make_init_data(50002, first_name="Новий", start_param="invite_does-not-exist")
    r = await client.get("/api/me", headers={HEADER: init_data})
    assert r.status_code == 404

    async with db.async_session() as session:
        shops = (await session.scalars(select(Shop).where(Shop.owner_tg_id == 50002))).all()
    assert shops == []


# --------------------------------------------------------------------------- #
#  2. POST /api/shops                                                         #
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_post_shops_creates_owner_demo_catalog_and_trial(client: AsyncClient) -> None:
    init_data = make_init_data(50010, first_name="Власник")
    r = await client.post("/api/shops", headers={HEADER: init_data}, json={"name": "Мій магазин"})
    assert r.status_code == 201, r.text
    shop_id = r.json()["shop_id"]

    r_me = await client.get("/api/me", headers={HEADER: init_data})
    assert r_me.status_code == 200
    body = r_me.json()
    assert body["shop_id"] == shop_id
    assert body["shop_name"] == "Мій магазин"
    assert body["role"] == "owner"

    async with db.async_session() as session:
        membership = await session.scalar(
            select(Membership).where(Membership.shop_id == shop_id, Membership.tg_id == 50010)
        )
        demo_products = (
            await session.scalars(
                select(Product).where(Product.shop_id == shop_id, Product.is_demo.is_(True))
            )
        ).all()
        subscription = await session.scalar(
            select(Subscription).where(Subscription.shop_id == shop_id)
        )

    assert membership is not None
    assert membership.role == MemberRole.owner
    assert len(demo_products) > 0
    assert subscription is not None
    assert subscription.status == SubStatus.trial
    assert subscription.trial_ends_at is not None

    trial_ends_at = subscription.trial_ends_at
    if trial_ends_at.tzinfo is None:
        trial_ends_at = trial_ends_at.replace(tzinfo=UTC)
    expected_end = utcnow() + timedelta(days=TRIAL_DAYS)
    assert abs((trial_ends_at - expected_end).total_seconds()) < 60


@pytest.mark.asyncio
async def test_post_shops_repeat_call_allowed_multi_shop(client: AsyncClient) -> None:
    init_data = make_init_data(50020, first_name="Мульти")

    shop_a = await _create_shop(client, init_data, "Магазин А")
    shop_b = await _create_shop(client, init_data, "Магазин Б")

    assert shop_a != shop_b

    async with db.async_session() as session:
        memberships = (
            await session.scalars(select(Membership).where(Membership.tg_id == 50020))
        ).all()
    assert {m.shop_id for m in memberships} == {shop_a, shop_b}
    assert all(m.role == MemberRole.owner for m in memberships)


@pytest.mark.asyncio
async def test_post_shops_rejects_blank_name(client: AsyncClient) -> None:
    init_data = make_init_data(50030)
    r = await client.post("/api/shops", headers={HEADER: init_data}, json={"name": ""})
    assert r.status_code == 422


# --------------------------------------------------------------------------- #
#  3. Invite-гілка для нового юзера далі працює                               #
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_new_user_with_valid_invite_joins_without_bootstrap(client: AsyncClient) -> None:
    owner_init = make_init_data(50040, first_name="Власник")
    owner_shop_id = await _create_shop(client, owner_init, "Магазин запрошень")
    invite = await _create_invite(client, owner_init)

    joiner_init = make_init_data(50041, first_name="Приєднався", start_param=f"invite_{invite['token']}")
    r = await client.get("/api/me", headers={HEADER: joiner_init})
    assert r.status_code == 200
    body = r.json()
    assert body["invite_status"] == "joined"
    assert body["shop_id"] == owner_shop_id
    assert body["role"] == "manager"

    async with db.async_session() as session:
        # Приєднання по інвайту НЕ створює власний Shop для joiner'а.
        own_shops = (await session.scalars(select(Shop).where(Shop.owner_tg_id == 50041))).all()
    assert own_shops == []


# --------------------------------------------------------------------------- #
#  4. DELETE /api/shop                                                        #
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_delete_shop_wrong_confirm_name_returns_400(client: AsyncClient) -> None:
    init_data = make_init_data(50050, first_name="Видаляльник")
    await _create_shop(client, init_data, "Точна Назва")

    r = await client.request(
        "DELETE", "/api/shop", headers={HEADER: init_data}, json={"confirm_name": "Неправильно"}
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_delete_shop_requires_owner_403(client: AsyncClient) -> None:
    owner_init = make_init_data(50060, first_name="Власник")
    shop_id = await _create_shop(client, owner_init, "Магазин")

    async with db.async_session() as session:
        session.add(Membership(shop_id=shop_id, tg_id=50061, role=MemberRole.manager))
        await session.commit()
    manager_init = make_init_data(50061, first_name="Менеджер")

    r = await client.request(
        "DELETE", "/api/shop", headers={HEADER: manager_init}, json={"confirm_name": "Магазин"}
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_delete_shop_cascades_everything_and_calls_r2_delete(client: AsyncClient) -> None:
    owner_init = make_init_data(50070, first_name="Власник")
    shop_id = await _create_shop(client, owner_init, "Повний магазин")

    async with db.async_session() as session:
        shop = await session.get(Shop, shop_id)
        assert shop is not None
        shop.logo_url = "https://cdn.example.test/shops/logo.webp"

        template = ProductTemplate(shop_id=shop_id, name="Кастомний", field_schema={})
        session.add(template)
        await session.flush()

        product = Product(shop_id=shop_id, name="Товар", template_id=template.id)
        session.add(product)
        await session.flush()

        photo = ProductPhoto(product_id=product.id, url="https://cdn.example.test/shops/photo.webp")
        session.add(photo)

        variant = Variant(
            shop_id=shop_id,
            product_id=product.id,
            price=Decimal("100"),
            on_hand=10,
            photo_url="https://cdn.example.test/shops/variant.webp",
        )
        session.add(variant)
        await session.flush()

        order = Order(
            shop_id=shop_id, source=OrderSource.website, status=OrderStatus.fulfilled,
            total=Decimal("100"),
        )
        session.add(order)
        await session.flush()

        session.add(OrderItem(order_id=order.id, variant_id=variant.id, qty=1, price_at_order=Decimal("100")))
        session.add(Reservation(shop_id=shop_id, variant_id=variant.id, order_id=order.id, qty=1))
        session.add(
            StockMovement(shop_id=shop_id, variant_id=variant.id, order_id=order.id, type=MovementType.sale, delta=-1)
        )
        invite = Invite(
            shop_id=shop_id, token="lifecycle-test-token", created_by_tg_id=50070,
            expires_at=utcnow() + timedelta(hours=48),
        )
        session.add(invite)
        await session.commit()

        product_id, variant_id, order_id, template_id = product.id, variant.id, order.id, template.id

    r = await client.request(
        "DELETE", "/api/shop", headers={HEADER: owner_init}, json={"confirm_name": "Повний магазин"}
    )
    assert r.status_code == 204

    async with db.async_session() as session:
        assert await session.get(Shop, shop_id) is None
        assert await session.get(Product, product_id) is None
        assert await session.get(Variant, variant_id) is None
        assert await session.get(Order, order_id) is None
        assert await session.get(ProductTemplate, template_id) is None
        assert (
            await session.scalar(select(Membership).where(Membership.shop_id == shop_id))
        ) is None
        assert (
            await session.scalar(select(Subscription).where(Subscription.shop_id == shop_id))
        ) is None
        assert (await session.scalar(select(Invite).where(Invite.shop_id == shop_id))) is None
        assert (
            await session.scalar(select(OrderItem).where(OrderItem.order_id == order_id))
        ) is None
        assert (
            await session.scalar(select(Reservation).where(Reservation.shop_id == shop_id))
        ) is None
        assert (
            await session.scalar(select(StockMovement).where(StockMovement.shop_id == shop_id))
        ) is None
        assert (
            await session.scalar(select(ProductPhoto).where(ProductPhoto.product_id == product_id))
        ) is None

    delete_calls = [c for c in _FakeS3Client.calls if c["op"] == "delete"]
    # лого + фото товару + фото варіанта = 3 R2-об'єкти
    assert len(delete_calls) == 3


# --------------------------------------------------------------------------- #
#  5/6. Після видалення: single-shop manager -> no_shop; multi-shop -> access #
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_manager_of_deleted_single_shop_gets_no_shop(client: AsyncClient) -> None:
    owner_init = make_init_data(50080, first_name="Власник")
    shop_id = await _create_shop(client, owner_init, "Магазин на видалення")

    async with db.async_session() as session:
        session.add(Membership(shop_id=shop_id, tg_id=50081, role=MemberRole.manager))
        await session.commit()
    manager_init = make_init_data(50081, first_name="Менеджер")

    r = await client.request(
        "DELETE", "/api/shop", headers={HEADER: owner_init},
        json={"confirm_name": "Магазин на видалення"},
    )
    assert r.status_code == 204

    r_manager = await client.get("/api/me", headers={HEADER: manager_init})
    assert r_manager.status_code == 404


@pytest.mark.asyncio
async def test_multi_shop_dead_shop_id_is_403_not_no_shop(client: AsyncClient) -> None:
    """Множинний власник: X-Shop-Id видаленого магазину -> 403 "Немає доступу"
    (НЕ no_shop — інші membership'и є). Без заголовка -> живий магазин."""
    init_data = make_init_data(50090, first_name="Мульти")
    shop_a = await _create_shop(client, init_data, "Живий магазин")
    shop_b = await _create_shop(client, init_data, "Магазин на видалення")

    r = await client.request(
        "DELETE", "/api/shop", headers={HEADER: init_data, "X-Shop-Id": str(shop_b)},
        json={"confirm_name": "Магазин на видалення"},
    )
    assert r.status_code == 204

    r_dead = await client.get(
        "/api/me", headers={HEADER: init_data, "X-Shop-Id": str(shop_b)}
    )
    assert r_dead.status_code == 403

    r_live = await client.get("/api/me", headers={HEADER: init_data})
    assert r_live.status_code == 200
    assert r_live.json()["shop_id"] == shop_a
