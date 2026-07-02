from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.deps import require_member
from app.models import Membership, Plan, Product, Shop, Subscription
from app.services.catalog import current_plan_limits

router = APIRouter(prefix="/api", tags=["me"])


@router.get("/me")
async def get_me(
    request: Request,
    membership: Membership = Depends(require_member),
    session: AsyncSession = Depends(get_session),
) -> dict:
    shop = await session.get(Shop, membership.shop_id)
    assert shop is not None

    subscription = await session.scalar(
        select(Subscription).where(Subscription.shop_id == shop.id)
    )
    plan_code = None
    if subscription is not None and subscription.plan_id is not None:
        plan = await session.get(Plan, subscription.plan_id)
        plan_code = plan.code if plan is not None else None

    limits = await current_plan_limits(shop.id, session)
    max_products = limits.get("max_products")

    products_count: int = (
        await session.scalar(
            select(func.count(Product.id)).where(
                Product.shop_id == shop.id, Product.archived.is_(False)
            )
        )
    ) or 0

    if max_products is None:
        active_count = products_count
    else:
        active_count = min(products_count, max_products)

    # Multi-shop (Стадія 3а): усі магазини цього tg_id, не лише активний —
    # той самий детермінований порядок (найменший id першим), що й
    # resolve_membership без X-Shop-Id.
    memberships = (
        await session.scalars(
            select(Membership)
            .where(Membership.tg_id == membership.tg_id)
            .order_by(Membership.id)
        )
    ).all()
    shops_by_id = {
        s.id: s
        for s in (
            await session.scalars(
                select(Shop).where(Shop.id.in_([m.shop_id for m in memberships]))
            )
        ).all()
    }
    shops = [
        {
            "shop_id": m.shop_id,
            "shop_name": shops_by_id[m.shop_id].name,
            "logo_url": shops_by_id[m.shop_id].logo_url,
            "role": m.role.value,
        }
        for m in memberships
    ]

    return {
        "shop_id": shop.id,
        "shop_name": shop.name,
        "shop_slug": shop.slug,
        "role": membership.role.value,
        "logo_url": shop.logo_url,
        "accent_color": shop.accent_color,
        # Зведення по підписці — фронту треба для тріал-банера/paywall/read-only.
        "status": subscription.status.value if subscription else None,
        "is_writable": subscription.is_writable if subscription else False,
        "trial_ends_at": subscription.trial_ends_at if subscription else None,
        "current_period_end": subscription.current_period_end if subscription else None,
        "plan_code": plan_code,
        # Free-plan slot info (FREE_PLAN_SPEC).
        "limits": limits,
        "products_count": products_count,
        "active_count": active_count,
        "max_products": max_products,
        # Deep-link інвайти: "joined" / "already_in_shop" / "invite_invalid" / None
        # (Стадія 3а: "already_member" більше не повертається — existing юзер
        # тепер приєднується як multi-shop, а не ігнорує інвайт).
        "invite_status": getattr(request.state, "invite_status", None),
        # Multi-shop (Стадія 3а): перемикач магазинів на фронті (X-Shop-Id).
        "shops": shops,
        "active_shop_id": membership.shop_id,
    }
