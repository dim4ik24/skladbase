"""
Нова Пошта — зберігання ключа магазину (app/api/np.py).

ping() підмінюється монкіпатчем на рівні модуля app.api.np (як notifier у
bot/notify.py) — живий НП API у тестах не викликаємо.

Criteria:
  1. PUT з валідним ключем (ping True) -> {"connected": true}, у БД ШИФРОВАНИЙ
     ключ (не plaintext), decrypt повертає оригінал
  2. PUT з невалідним ключем (ping False) -> 422, у БД нічого не збережено
  3. GET -> {"connected": bool}, ключ НІКОЛИ не повертається
  4. DELETE -> 204, після цього GET -> {"connected": false}
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient

from app import db
from app.api import np as np_module
from app.models import Shop
from app.security.crypto import decrypt
from tests.conftest import make_init_data

HEADER = "X-Telegram-Init-Data"


async def _bootstrap(client: AsyncClient, tg_id: int, name: str = "Тест") -> tuple[str, int]:
    init_data = make_init_data(tg_id, first_name=name)
    r = await client.get("/api/me", headers={HEADER: init_data})
    assert r.status_code == 200
    return init_data, r.json()["shop_id"]


async def _get_shop(shop_id: int) -> Shop:
    async with db.async_session() as session:
        shop = await session.get(Shop, shop_id)
    assert shop is not None
    return shop


@pytest.mark.asyncio
async def test_put_valid_key_stores_encrypted(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(np_module, "ping", lambda api_key: _true())
    init_data, shop_id = await _bootstrap(client, 90001)

    r = await client.put(
        "/api/shop/np-key", json={"api_key": "np-live-key-123"}, headers={HEADER: init_data}
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"connected": True}

    shop = await _get_shop(shop_id)
    assert shop.np_api_key_encrypted is not None
    assert shop.np_api_key_encrypted != "np-live-key-123"  # не plaintext
    assert decrypt(shop.np_api_key_encrypted) == "np-live-key-123"


@pytest.mark.asyncio
async def test_put_invalid_key_returns_422_and_saves_nothing(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(np_module, "ping", lambda api_key: _false())
    init_data, shop_id = await _bootstrap(client, 90002)

    r = await client.put(
        "/api/shop/np-key", json={"api_key": "bad-key"}, headers={HEADER: init_data}
    )
    assert r.status_code == 422

    shop = await _get_shop(shop_id)
    assert shop.np_api_key_encrypted is None


@pytest.mark.asyncio
async def test_get_status_never_exposes_key(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(np_module, "ping", lambda api_key: _true())
    init_data, _shop_id = await _bootstrap(client, 90003)

    r0 = await client.get("/api/shop/np-key", headers={HEADER: init_data})
    assert r0.status_code == 200
    assert r0.json() == {"connected": False}

    await client.put(
        "/api/shop/np-key", json={"api_key": "np-live-key-456"}, headers={HEADER: init_data}
    )

    r1 = await client.get("/api/shop/np-key", headers={HEADER: init_data})
    assert r1.status_code == 200
    body = r1.json()
    assert body == {"connected": True}
    assert "api_key" not in body
    assert "np_api_key_encrypted" not in body


@pytest.mark.asyncio
async def test_delete_clears_key(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(np_module, "ping", lambda api_key: _true())
    init_data, shop_id = await _bootstrap(client, 90004)

    await client.put(
        "/api/shop/np-key", json={"api_key": "np-live-key-789"}, headers={HEADER: init_data}
    )

    r = await client.delete("/api/shop/np-key", headers={HEADER: init_data})
    assert r.status_code == 204

    shop = await _get_shop(shop_id)
    assert shop.np_api_key_encrypted is None

    r2 = await client.get("/api/shop/np-key", headers={HEADER: init_data})
    assert r2.json() == {"connected": False}


async def _true() -> bool:
    return True


async def _false() -> bool:
    return False
