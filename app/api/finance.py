from __future__ import annotations

from fastapi import APIRouter, Depends

from app.deps import require_owner
from app.models import Membership

router = APIRouter(prefix="/api/finance", tags=["finance"])


@router.get("/summary")
async def finance_summary(
    membership: Membership = Depends(require_owner),
) -> dict:
    return {"shop_id": membership.shop_id, "revenue_uah": "0.00"}
