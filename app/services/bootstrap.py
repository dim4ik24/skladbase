"""
Перший вхід нового tg_id у систему (фіча 1 з ROADMAP, Стадія 1).

Створює Shop + Membership(owner), гарантує наявність системних шаблонів і
тарифів, засіює демо-каталог і стартує 7-денний тріал. Викликається лише
з `deps.resolve_membership`, коли для tg_id з валідованого initData ще
нема Membership.
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import MemberRole, Membership, Shop
from app.security.initdata import TelegramUser
from app.seed import seed_demo_catalog, seed_plans, seed_system_templates
from app.services.subscriptions import SubscriptionService


async def bootstrap_shop(session: AsyncSession, user: TelegramUser) -> Membership:
    await seed_system_templates(session)
    await seed_plans(session)

    shop_name = f"Магазин {user.first_name}".strip() or "Мій магазин"
    shop = Shop(owner_tg_id=user.id, name=shop_name, slug=f"shop-{user.id}")
    session.add(shop)
    await session.flush()

    membership = Membership(
        shop_id=shop.id,
        tg_id=user.id,
        display_name=user.first_name or None,
        role=MemberRole.owner,
    )
    session.add(membership)
    await session.flush()

    await seed_demo_catalog(session, shop)
    await SubscriptionService(session).start_trial(shop)

    await session.commit()
    return membership
