"""
SkladBase — owner-only зведення продажів/виручки (REST API над
`services/analytics.py`). Тільки читання: жодних змін залишку/інвентаря,
жодного виклику `inventory.py`.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.deps import require_owner
from app.models import Membership
from app.services import analytics as analytics_service

router = APIRouter(prefix="/api/analytics", tags=["analytics"])

Period = Literal["today", "7d", "30d", "all"]


class TopProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    product_id: int
    name: str
    units_sold: int
    revenue: Decimal


class AnalyticsSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    period: str
    units_sold: int
    revenue: Decimal
    sales_count: int
    top_products: list[TopProductOut]


@router.get("/summary", response_model=AnalyticsSummaryOut)
async def get_analytics_summary(
    period: Period = "7d",
    membership: Membership = Depends(require_owner),
    session: AsyncSession = Depends(get_session),
) -> analytics_service.AnalyticsSummary:
    return await analytics_service.get_summary(session, shop_id=membership.shop_id, period=period)
