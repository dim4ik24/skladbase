"""
Перший вхід нового tg_id у систему (фіча 1 з ROADMAP, Стадія 1).

Створює Shop + Membership(owner), гарантує наявність системних шаблонів і
тарифів, засіює демо-каталог і стартує 7-денний тріал. Викликається лише
з `deps.resolve_membership`, коли для tg_id з валідованого initData ще
нема Membership.

Ідемпотентність під конкурентним першим входом: кілька паралельних запитів
з тим самим tg_id (типово кілька запитів TMA одразу при відкритті) можуть
одночасно дійти сюди, не побачивши чужого ще не закомітченого Membership.
Усі намагаються створити Shop з однаковим slug `shop-{tg_id}` — переможець
гонки комітить Shop+Membership, решта ловлять `IntegrityError` на
unique(slug) при `flush()`, відкочуються і повертають вже створений
переможцем Membership — той самий приймом, що `create_website_order`
використовує для замовлень.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import MemberRole, Membership, Shop
from app.security.initdata import TelegramUser
from app.seed import seed_demo_catalog, seed_plans, seed_system_templates
from app.services.subscriptions import SubscriptionService


async def _find_membership(session: AsyncSession, tg_id: int) -> Membership | None:
    return await session.scalar(select(Membership).where(Membership.tg_id == tg_id))


async def bootstrap_shop(session: AsyncSession, user: TelegramUser) -> Membership:
    existing = await _find_membership(session, user.id)
    if existing is not None:
        return existing

    await seed_system_templates(session)
    await seed_plans(session)

    shop_name = f"Магазин {user.first_name}".strip() or "Мій магазин"
    shop = Shop(owner_tg_id=user.id, name=shop_name, slug=f"shop-{user.id}")
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
        await session.rollback()
        existing = await _find_membership(session, user.id)
        if existing is not None:
            return existing
        raise

    await seed_demo_catalog(session, shop)
    await SubscriptionService(session).start_trial(shop)

    await session.commit()
    return membership
