"""
SkladBase — явне створення і видалення магазину (shop lifecycle).

`create_shop` — єдиний шлях, яким узагалі виникає новий Shop (авто-bootstrap
на першому вході прибрано, app/deps.py::resolve_membership). Одна людина
може мати кілька своїх магазинів (multi-shop) — повторний виклик для того
самого tg_id ДОЗВОЛЕНИЙ, не дедуплікується.

`delete_shop` — каскадне видалення. SQLite-з'єднання цього проєкту НЕ
вмикає `PRAGMA foreign_keys` (app/db.py), тож задекларований у моделях
`ondelete="CASCADE"` сам по собі НЕ спрацює на SQLite (dev/тести) — видаляємо
явно, у порядку, що враховує `OrderItem.variant_id` (`ondelete="RESTRICT"`,
має піти першим, інакше на Postgres реально заблокує видалення Variant).
"""
from __future__ import annotations

import secrets

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Invite,
    MemberRole,
    Membership,
    Order,
    OrderItem,
    Payment,
    Product,
    ProductPhoto,
    ProductTemplate,
    PromoRedemption,
    Reservation,
    Shop,
    StockMovement,
    Subscription,
    Variant,
)
from app.security.initdata import TelegramUser
from app.seed import seed_demo_catalog, seed_plans, seed_system_templates
from app.services.subscriptions import SubscriptionService


def _generate_slug(tg_id: int) -> str:
    return f"shop-{tg_id}-{secrets.token_hex(4)}"


async def create_shop(session: AsyncSession, user: TelegramUser, name: str) -> Membership:
    """1:1 логіка колишнього bootstrap_shop (нова-магазин гілка), лише slug
    рандомізований — multi-shop дозволяє кілька магазинів того самого tg_id,
    детермінований `shop-{tg_id}` гарантовано конфліктував би на другому виклику."""
    await seed_system_templates(session)
    await seed_plans(session)

    shop = Shop(owner_tg_id=user.id, name=name, slug=_generate_slug(user.id))
    membership = Membership(
        shop=shop,
        tg_id=user.id,
        display_name=user.first_name or None,
        role=MemberRole.owner,
    )
    session.add_all([shop, membership])

    try:
        await session.flush()
    except IntegrityError:
        # Астрономічно малоймовірна колізія рандомного slug — одна спроба ще раз.
        await session.rollback()
        shop.slug = _generate_slug(user.id)
        session.add_all([shop, membership])
        await session.flush()

    await seed_demo_catalog(session, shop)
    await SubscriptionService(session).start_trial(shop)

    await session.commit()
    return membership


async def delete_shop(session: AsyncSession, shop: Shop) -> list[str]:
    """Видаляє магазин і все, що на нього посилається. Повертає R2-URL
    (фото товарів/варіантів, лого) — виклик прибирає їх з R2 best-effort
    ПІСЛЯ commit цієї функції: якщо R2-крок впаде, магазин у БД вже коректно
    видалений (лишаться лише осиротілі файли, не зламані дані живого магазину)."""
    shop_id = shop.id

    photo_urls: list[str] = list(
        (
            await session.scalars(
                select(ProductPhoto.url)
                .join(Product, ProductPhoto.product_id == Product.id)
                .where(Product.shop_id == shop_id)
            )
        ).all()
    )
    photo_urls += [
        url
        for url in (
            await session.scalars(select(Variant.photo_url).where(Variant.shop_id == shop_id))
        ).all()
        if url
    ]
    if shop.logo_url:
        photo_urls.append(shop.logo_url)

    order_ids = select(Order.id).where(Order.shop_id == shop_id).scalar_subquery()
    product_ids = select(Product.id).where(Product.shop_id == shop_id).scalar_subquery()

    # OrderItem.variant_id -> RESTRICT: має піти перед Variant.
    await session.execute(delete(OrderItem).where(OrderItem.order_id.in_(order_ids)))
    await session.execute(delete(Reservation).where(Reservation.shop_id == shop_id))
    await session.execute(delete(StockMovement).where(StockMovement.shop_id == shop_id))
    await session.execute(delete(Order).where(Order.shop_id == shop_id))
    await session.execute(delete(ProductPhoto).where(ProductPhoto.product_id.in_(product_ids)))
    await session.execute(delete(Variant).where(Variant.shop_id == shop_id))
    await session.execute(delete(Product).where(Product.shop_id == shop_id))
    await session.execute(delete(ProductTemplate).where(ProductTemplate.shop_id == shop_id))
    await session.execute(delete(Invite).where(Invite.shop_id == shop_id))
    await session.execute(delete(Payment).where(Payment.shop_id == shop_id))
    await session.execute(delete(PromoRedemption).where(PromoRedemption.shop_id == shop_id))
    await session.execute(delete(Subscription).where(Subscription.shop_id == shop_id))
    await session.execute(delete(Membership).where(Membership.shop_id == shop_id))
    await session.execute(delete(Shop).where(Shop.id == shop_id))

    await session.commit()
    return photo_urls
