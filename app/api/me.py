from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.deps import require_member
from app.models import Membership, Plan, Product, Shop, Subscription
from app.services.catalog import current_plan_limits

router = APIRouter(prefix="/api", tags=["me"])


@router.get("/me")
async def get_me(
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
    }
