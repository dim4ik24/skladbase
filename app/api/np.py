"""
SkladBase — інтеграція з Нова Пошта (Фіча B1): зберігання ключа магазину.

Ключ ВАЛІДУЄТЬСЯ (ping) перед збереженням і НІКОЛИ не повертається назад —
лише {"connected": bool}. Owner-only (require_owner), як і решта секретів
магазину (webhook, website API key, app/api/shop.py).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.deps import require_owner
from app.models import Membership, Shop
from app.security.crypto import encrypt
from app.services.novaposhta import ping

router = APIRouter(prefix="/api/shop/np-key", tags=["novaposhta"])


class NpKeyIn(BaseModel):
    api_key: str


class NpKeyStatusOut(BaseModel):
    connected: bool


@router.put("", response_model=NpKeyStatusOut)
async def set_np_key(
    payload: NpKeyIn,
    membership: Membership = Depends(require_owner),
    session: AsyncSession = Depends(get_session),
) -> NpKeyStatusOut:
    if not await ping(payload.api_key):
        raise HTTPException(status_code=422, detail="Ключ не пройшов перевірку")

    shop = await session.get(Shop, membership.shop_id)
    assert shop is not None
    shop.np_api_key_encrypted = encrypt(payload.api_key)
    await session.commit()
    return NpKeyStatusOut(connected=True)


@router.delete("", status_code=204)
async def delete_np_key(
    membership: Membership = Depends(require_owner),
    session: AsyncSession = Depends(get_session),
) -> Response:
    shop = await session.get(Shop, membership.shop_id)
    assert shop is not None
    shop.np_api_key_encrypted = None
    await session.commit()
    return Response(status_code=204)


@router.get("", response_model=NpKeyStatusOut)
async def get_np_key_status(
    membership: Membership = Depends(require_owner),
    session: AsyncSession = Depends(get_session),
) -> NpKeyStatusOut:
    shop = await session.get(Shop, membership.shop_id)
    assert shop is not None
    return NpKeyStatusOut(connected=shop.np_api_key_encrypted is not None)
