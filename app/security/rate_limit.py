"""
SkladBase — власний in-memory rate limiter для чутливих ендпоінтів (Стадія 8):
публічний каталог, вебхуки платежів/Telegram, bootstrap нового магазину.

Sliding window per (лімітер, client_ip), без зовнішніх залежностей (slowapi
тут надмірний для одного процесу). Для горизонтального масштабування (кілька
інстансів) знадобиться розподілений лічильник (Redis) — поза скоупом MVP.
"""
from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status

_registry: dict[str, "InMemoryRateLimiter"] = {}


class InMemoryRateLimiter:
    def __init__(self, name: str, *, max_requests: int, window_seconds: float) -> None:
        if name in _registry:
            raise ValueError(f"лімітер з ім'ям {name!r} вже зареєстрований")
        self.name = name
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        _registry[name] = self

    def hit(self, key: str) -> bool:
        """Записує спробу під `key` і повертає True, якщо вона в межах ліміту."""
        now = time.monotonic()
        bucket = self._hits[key]
        while bucket and now - bucket[0] > self.window_seconds:
            bucket.popleft()
        if len(bucket) >= self.max_requests:
            return False
        bucket.append(now)
        return True

    def reset(self) -> None:
        self._hits.clear()


def reset_all() -> None:
    """Для тестів: кожен тест має починати з чистого стану лімітерів."""
    for limiter in _registry.values():
        limiter.reset()


def client_ip(request: Request) -> str:
    """За трастед-проксі (`ProxyHeadersMiddleware`) `request.client` —
    вже реальний клієнт, не nginx/Cloudflare: middleware переписує scope
    раніше за будь-яку залежність."""
    return request.client.host if request.client else "unknown"


def rate_limited(limiter: InMemoryRateLimiter):
    """FastAPI-залежність: 429, якщо клієнт (за IP) перевищив ліміт для
    цього лімітера. Виконується ДО тіла ендпоінта (дешевше за перевірку
    підпису/бізнес-логіки на кожен зайвий запит)."""

    async def _dependency(request: Request) -> None:
        if not limiter.hit(client_ip(request)):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Занадто багато запитів, спробуйте пізніше",
            )

    return _dependency
