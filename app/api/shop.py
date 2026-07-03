"""
SkladBase — налаштування магазину (Стадія 4b: вебхук на сайт) + shop
lifecycle (створення/видалення, app/services/shops.py).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.deps import require_owner, resolve_telegram_user
from app.models import Membership, Shop
from app.security.initdata import TelegramUser
from app.security.rate_limit import InMemoryRateLimiter, client_ip
from app.seed import clear_demo_catalog
from app.services import shops as shops_service
from app.services.media import MediaError, delete_photo, max_upload_bytes, read_capped, upload_photo
from app.services.shop import set_webhook

router = APIRouter(prefix="/api/shop", tags=["shop"])
shops_router = APIRouter(prefix="/api/shops", tags=["shop"])

# Створення магазину — найдешевший шлях для абʼюзу (масове штампування
# магазинів з однієї IP). Ліміт за IP, не за tg_id: multi-shop дозволяє
# кілька магазинів того самого tg_id, довіряти йому як ключу ліміту нема сенсу.
_shop_create_limiter = InMemoryRateLimiter("shop_bootstrap", max_requests=20, window_seconds=60)


class ShopCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class ShopCreateOut(BaseModel):
    shop_id: int


class ShopDeleteIn(BaseModel):
    confirm_name: str


@shops_router.post("", status_code=201, response_model=ShopCreateOut)
async def create_shop(
    payload: ShopCreateIn,
    request: Request,
    user: TelegramUser = Depends(resolve_telegram_user),
    session: AsyncSession = Depends(get_session),
) -> ShopCreateOut:
    if not _shop_create_limiter.hit(client_ip(request)):
        raise HTTPException(
            status_code=429,
            detail="Занадто багато нових магазинів з цієї IP, спробуйте пізніше",
        )
    membership = await shops_service.create_shop(session, user, payload.name)
    return ShopCreateOut(shop_id=membership.shop_id)


@router.delete("", status_code=204)
async def delete_shop(
    payload: ShopDeleteIn,
    membership: Membership = Depends(require_owner),
    session: AsyncSession = Depends(get_session),
) -> Response:
    shop = await session.get(Shop, membership.shop_id)
    assert shop is not None
    if payload.confirm_name != shop.name:
        raise HTTPException(status_code=400, detail="Назва не збігається")

    photo_urls = await shops_service.delete_shop(session, shop)
    for url in photo_urls:
        await delete_photo(url)

    return Response(status_code=204)


class WebhookIn(BaseModel):
    url: str


class WebhookOut(BaseModel):
    webhook_url: str
    webhook_secret: str


class ClearDemosOut(BaseModel):
    removed: int


class ShopProfileIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class ShopProfileOut(BaseModel):
    shop_name: str
    logo_url: str | None


@router.patch("", response_model=ShopProfileOut)
async def update_shop_profile(
    payload: ShopProfileIn,
    membership: Membership = Depends(require_owner),
    session: AsyncSession = Depends(get_session),
) -> ShopProfileOut:
    shop = await session.get(Shop, membership.shop_id)
    assert shop is not None
    shop.name = payload.name
    await session.commit()
    return ShopProfileOut(shop_name=shop.name, logo_url=shop.logo_url)


@router.post("/logo")
async def upload_shop_logo(
    file: UploadFile = File(...),
    membership: Membership = Depends(require_owner),
    session: AsyncSession = Depends(get_session),
) -> dict:
    shop = await session.get(Shop, membership.shop_id)
    assert shop is not None
    data = await read_capped(file, max_upload_bytes())
    try:
        url = await upload_photo(
            key_prefix=f"shops/{shop.id}/logo",
            content_type=file.content_type or "",
            data=data,
        )
    except MediaError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    shop.logo_url = url
    await session.commit()
    return {"logo_url": url}


@router.delete("/logo", status_code=204)
async def delete_shop_logo(
    membership: Membership = Depends(require_owner),
    session: AsyncSession = Depends(get_session),
) -> Response:
    shop = await session.get(Shop, membership.shop_id)
    assert shop is not None
    if shop.logo_url:
        await delete_photo(shop.logo_url)
    shop.logo_url = None
    await session.commit()
    return Response(status_code=204)


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


@router.post("/clear-demos", response_model=ClearDemosOut)
async def clear_demos(
    membership: Membership = Depends(require_owner),
    session: AsyncSession = Depends(get_session),
) -> ClearDemosOut:
    """Кнопка «Очистити приклади» — прибирає лише `is_demo` товари свого магазину."""
    shop = await session.get(Shop, membership.shop_id)
    assert shop is not None
    removed = await clear_demo_catalog(session, shop)
    return ClearDemosOut(removed=removed)
