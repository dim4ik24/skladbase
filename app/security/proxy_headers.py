"""
SkladBase — довіра до X-Forwarded-For за nginx/Cloudflare (Стадія 9a).

Без цього `request.client.host` усередині застосунку завжди дорівнює IP
проксі (наприклад, 127.0.0.1 за nginx на тому самому хості), і
`rate_limit.client_ip()` рахує ВСІХ клієнтів за одним ключем — лімітер
блокує всіх або нікого.

Довіряємо заголовку лише якщо безпосередній peer (`scope["client"]`) — у
списку `trusted_proxies`: інакше будь-який зовнішній клієнт міг би сам
підставити довільний X-Forwarded-For і підмінити свій IP для лімітера.
Беремо ПЕРШИЙ IP у списку (найлівіший — оригінальний клієнт за конвенцією
X-Forwarded-For); довіряємо рівно одному рівню проксі.

Чистий ASGI-middleware (не Starlette BaseHTTPMiddleware) — лише переписує
`scope["client"]` до того, як запит дійде до роутів/залежностей; не читає
і не буферизує тіло запиту.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

Scope = dict[str, Any]
Receive = Callable[[], Awaitable[dict[str, Any]]]
Send = Callable[[dict[str, Any]], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]


class ProxyHeadersMiddleware:
    def __init__(self, app: ASGIApp, *, trusted_proxies: frozenset[str]) -> None:
        self.app = app
        self.trusted_proxies = trusted_proxies

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            client = scope.get("client")
            if client and client[0] in self.trusted_proxies:
                forwarded_for = _get_header(scope, b"x-forwarded-for")
                if forwarded_for:
                    real_ip = forwarded_for.split(",")[0].strip()
                    if real_ip:
                        scope["client"] = (real_ip, client[1])

        await self.app(scope, receive, send)


def _get_header(scope: Scope, name: bytes) -> str | None:
    for key, value in scope.get("headers", ()):
        if key == name:
            return value.decode("latin-1")
    return None
