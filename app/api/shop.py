"""
SkladBase — налаштування магазину (Стадія 4b: вебхук на сайт).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.deps import require_owner
from app.models import Membership, Shop
from app.services.shop import set_webhook

router = APIRouter(prefix="/api/shop", tags=["shop"])


class WebhookIn(BaseModel):
    url: str


class WebhookOut(BaseModel):
    webhook_url: str
    webhook_secret: str


@router.post("/webhook", response_model=WebhookOut)
async def configure_webhook(
    payload: WebhookIn,
    membership: Membership = Depends(require_owner),
    session: AsyncSession = Depends(get_session),
) -> WebhookOut:
    shop = await session.get(Shop, membership.shop_id)
    assert shop is not None
    secret = await set_webhook(session, shop, payload.url)
    return WebhookOut(webhook_url=payload.url, webhook_secret=secret)
