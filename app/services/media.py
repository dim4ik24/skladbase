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
from fastapi import UploadFile
from PIL import Image, UnidentifiedImageError

from app.config import settings
from app.i18n import ServiceError

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_DIMENSION = 1024
WEBP_QUALITY = 80
_READ_CHUNK_SIZE = 64 * 1024


class MediaError(ServiceError):
    """Помилка завантаження фото з HTTP статус-кодом для API-шару. Текст
    рендериться на межі API-шару через .detail(lang) — див. app/i18n.py."""


def _validate(content_type: str, data: bytes) -> None:
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise MediaError(
            HTTPStatus.BAD_REQUEST,
            "media.unsupported_type",
            content_type=content_type,
        )

    max_bytes = settings.MAX_PHOTO_UPLOAD_MB * 1024 * 1024
    if len(data) > max_bytes:
        raise MediaError(
            HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
            "media.file_too_large",
            max_mb=settings.MAX_PHOTO_UPLOAD_MB,
        )


def _compress_to_webp(data: bytes) -> bytes:
    try:
        opened = Image.open(io.BytesIO(data))
        opened.load()
    except UnidentifiedImageError as exc:
        raise MediaError(HTTPStatus.BAD_REQUEST, "media.invalid_image") from exc

    image = opened.convert("RGB")
    image.thumbnail((MAX_DIMENSION, MAX_DIMENSION))

    buffer = io.BytesIO()
    image.save(buffer, format="WEBP", quality=WEBP_QUALITY)
    return buffer.getvalue()


def _build_key(key_prefix: str) -> str:
    return f"{key_prefix}/{uuid.uuid4()}.webp"


def _public_url(key: str) -> str:
    return f"{settings.R2_PUBLIC_URL.rstrip('/')}/{key}"


def _r2_client():
    """aioboto3 S3-клієнт для R2 (context manager)."""
    session = aioboto3.Session()
    return session.client(
        "s3",
        endpoint_url=f"https://{settings.R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
        aws_access_key_id=settings.R2_ACCESS_KEY,
        aws_secret_access_key=settings.R2_SECRET_KEY,
        region_name="auto",
    )


def max_upload_bytes() -> int:
    return settings.MAX_PHOTO_UPLOAD_MB * 1024 * 1024


def _too_large_error() -> MediaError:
    return MediaError(
        HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
        "media.file_too_large",
        max_mb=settings.MAX_PHOTO_UPLOAD_MB,
    )


async def read_capped(file: UploadFile, max_bytes: int) -> bytes:
    """Читає `file` по чанках, обриваючи ОДРАЗУ як перевищено `max_bytes` —
    замість того, щоб спершу прочитати в памʼять потенційно величезне тіло
    і лише потім перевірити розмір (ROADMAP, відкладено зі Стадії 2b)."""
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(_READ_CHUNK_SIZE)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise _too_large_error()
        chunks.append(chunk)
    return b"".join(chunks)


async def upload_photo(*, key_prefix: str, content_type: str, data: bytes) -> str:
    """Валідує, стискає у WebP і вантажить у R2. Повертає публічний URL.

    `key_prefix` визначає шлях в R2: для варіантів — `shops/{shop_id}/{variant_id}`,
    для галереї товару — `shops/{shop_id}/products/{product_id}`.
    """
    _validate(content_type, data)
    compressed = _compress_to_webp(data)
    key = _build_key(key_prefix)

    async with _r2_client() as s3:
        await s3.put_object(
            Bucket=settings.R2_BUCKET,
            Key=key,
            Body=compressed,
            ContentType="image/webp",
        )

    return _public_url(key)


async def upload_variant_photo(
    *, shop_id: int, variant_id: int, content_type: str, data: bytes
) -> str:
    """Валідує, стискає у WebP і вантажить у R2. Повертає публічний URL."""
    return await upload_photo(
        key_prefix=f"shops/{shop_id}/{variant_id}",
        content_type=content_type,
        data=data,
    )


async def delete_photo(url: str) -> None:
    """Best-effort видалення об'єкта з R2.

    Витягує R2-ключ з публічного URL, викликає delete_object. Всі помилки
    ігноруються — R2-orphan прибирається best-effort, не критичний шлях.
    """
    base = settings.R2_PUBLIC_URL.rstrip("/") + "/"
    if not url.startswith(base):
        return
    key = url[len(base):]
    try:
        async with _r2_client() as s3:
            await s3.delete_object(Bucket=settings.R2_BUCKET, Key=key)
    except Exception:
        pass
