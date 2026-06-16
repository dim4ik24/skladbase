from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.deps import require_member
from app.models import Membership, Shop

router = APIRouter(prefix="/api", tags=["me"])


@router.get("/me")
async def get_me(
    membership: Membership = Depends(require_member),
    session: AsyncSession = Depends(get_session),
) -> dict:
    shop = await session.get(Shop, membership.shop_id)
    assert shop is not None
    return {
        "shop_id": shop.id,
        "shop_name": shop.name,
        "shop_slug": shop.slug,
        "role": membership.role.value,
    }
