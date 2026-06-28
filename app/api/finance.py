from __future__ import annotations

from fastapi import APIRouter

from app.deps import require_permission
from app.models import Membership

router = APIRouter(prefix="/api/finance", tags=["finance"])


@router.get("/summary")
async def finance_summary(
    membership: Membership = require_permission("can_view_finance"),
) -> dict:
    return {"shop_id": membership.shop_id, "revenue_uah": "0.00"}
