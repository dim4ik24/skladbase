"""
SkladBase — клієнт Нова Пошта API (Фіча B1): валідація ключа + трекінг ТТН.

POST https://api.novaposhta.ua/v2.0/json/ з тілом
{"apiKey", "modelName", "calledMethod", "methodProperties"} -> {"success": bool, "data": [...]}.
Ключ ніколи не логується — передається лише в тілі запиту.
"""
from __future__ import annotations

import httpx

_API_URL = "https://api.novaposhta.ua/v2.0/json/"
_TIMEOUT = 15
_TRACK_BATCH_SIZE = 100  # ліміт НП API на кількість документів за один запит getStatusDocuments

# StatusCode за getStatusDocuments (TrackingDocument). Офіційний
# devcenter.novaposhta.ua недоступний для прямої звірки (HTTP 530 на момент
# написання) — компільовано з незалежних community-джерел (createit.com,
# стаття саме про polling StatusCode кроном + кілька open-source обгорток
# НП API), що узгоджуються між собою в головному. Звір при першому реальному
# підключенні ключа й скоригуй за потреби.
PICKED_CODES = frozenset({9, 10, 11})        # отримано одержувачем (в т.ч. накладений платіж)
RETURNED_CODES = frozenset({102, 103, 108})  # відмова одержувача / повернення відправнику


class NovaPoshtaError(Exception):
    """Мережевий збій або відповідь НП API з success=false."""


async def _call(api_key: str, model_name: str, called_method: str, method_properties: dict) -> dict:
    payload = {
        "apiKey": api_key,
        "modelName": model_name,
        "calledMethod": called_method,
        "methodProperties": method_properties,
    }
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.post(_API_URL, json=payload)
            return response.json()
    except httpx.HTTPError as exc:
        raise NovaPoshtaError(f"НП API недоступний: {exc}") from exc


async def ping(api_key: str) -> bool:
    """Легкий запит без побічних ефектів — перевіряє, що ключ валідний."""
    try:
        data = await _call(api_key, "Address", "getCities", {"Limit": 1})
    except NovaPoshtaError:
        return False
    return bool(data.get("success"))


async def track(api_key: str, ttns: list[str]) -> list[dict]:
    """Статуси документів за списком ТТН, батчами по 100 (ліміт НП API).

    Кидає NovaPoshtaError на мережевий збій чи success=false — викликач
    (крон) ловить це на рівні магазину, щоб один поганий ключ не валив цикл."""
    results: list[dict] = []
    for i in range(0, len(ttns), _TRACK_BATCH_SIZE):
        batch = ttns[i : i + _TRACK_BATCH_SIZE]
        data = await _call(
            api_key,
            "TrackingDocument",
            "getStatusDocuments",
            {"Documents": [{"DocumentNumber": ttn} for ttn in batch]},
        )
        if not data.get("success"):
            raise NovaPoshtaError(f"getStatusDocuments: {data.get('errors')}")
        results.extend(data.get("data") or [])
    return results
