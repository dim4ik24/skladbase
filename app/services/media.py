"""
SkladBase — фото товарів: валідація, стиснення (Pillow), завантаження в
Cloudflare R2 (S3-сумісний, через aioboto3) (Стадія 2b).

Контроль вартості зберігання (ROADMAP, ризик "Вартість зберігання фото"):
ресайз до максимальної сторони 1024px і перекодування у WebP ~80% якості
ПЕРЕД завантаженням — оригінал у R2 ніколи не потрапляє.

Валідація типу/розміру відбувається ДО будь-якої обробки (Pillow) чи мережевого
виклику (R2) — невалідний вхід відхиляється одразу, без зайвої роботи.
"""
from __future__ import annotations

import io
import uuid
from http import HTTPStatus

import aioboto3
from PIL import Image, UnidentifiedImageError

from app.config import settings

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_DIMENSION = 1024
WEBP_QUALITY = 80


class MediaError(Exception):
    """Помилка завантаження фото з HTTP статус-кодом для API-шару."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _validate(content_type: str, data: bytes) -> None:
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise MediaError(
            HTTPStatus.BAD_REQUEST,
            f"Непідтримуваний тип файлу: '{content_type}'. Дозволено: jpeg, png, webp.",
        )

    max_bytes = settings.MAX_PHOTO_UPLOAD_MB * 1024 * 1024
    if len(data) > max_bytes:
        raise MediaError(
            HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
            f"Файл занадто великий: максимум {settings.MAX_PHOTO_UPLOAD_MB} МБ.",
        )


def _compress_to_webp(data: bytes) -> bytes:
    try:
        opened = Image.open(io.BytesIO(data))
        opened.load()
    except UnidentifiedImageError as exc:
        raise MediaError(HTTPStatus.BAD_REQUEST, "Файл не є валідним зображенням") from exc

    image = opened.convert("RGB")
    image.thumbnail((MAX_DIMENSION, MAX_DIMENSION))

    buffer = io.BytesIO()
    image.save(buffer, format="WEBP", quality=WEBP_QUALITY)
    return buffer.getvalue()


def _build_key(shop_id: int, variant_id: int) -> str:
    return f"shops/{shop_id}/{variant_id}/{uuid.uuid4()}.webp"


def _public_url(key: str) -> str:
    return f"{settings.R2_PUBLIC_URL.rstrip('/')}/{key}"


async def upload_variant_photo(
    *, shop_id: int, variant_id: int, content_type: str, data: bytes
) -> str:
    """Валідує, стискає у WebP і вантажить у R2. Повертає публічний URL."""
    _validate(content_type, data)
    compressed = _compress_to_webp(data)
    key = _build_key(shop_id, variant_id)

    session = aioboto3.Session()
    async with session.client(
        "s3",
        endpoint_url=f"https://{settings.R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
        aws_access_key_id=settings.R2_ACCESS_KEY,
        aws_secret_access_key=settings.R2_SECRET_KEY,
        region_name="auto",
    ) as s3:
        await s3.put_object(
            Bucket=settings.R2_BUCKET,
            Key=key,
            Body=compressed,
            ContentType="image/webp",
        )

    return _public_url(key)
