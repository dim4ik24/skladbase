"""
SkladBase — клієнт Нова Пошта API (Фіча B1/B3): валідація ключа, трекінг ТТН,
довідники міст/відділень, створення накладних.

POST https://api.novaposhta.ua/v2.0/json/ з тілом
{"apiKey", "modelName", "calledMethod", "methodProperties"} -> {"success": bool, "data": [...]}.
Ключ ніколи не логується — передається лише в тілі запиту.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import httpx

_API_URL = "https://api.novaposhta.ua/v2.0/json/"
_TIMEOUT = 15
_TRACK_BATCH_SIZE = 100  # ліміт НП API на кількість документів за один запит getStatusDocuments
_SEARCH_LIMIT = 10

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


def _require_success(data: dict, step: str) -> list[dict]:
    if not data.get("success"):
        errors = data.get("errors") or data.get("errorCodes") or ["невідома помилка"]
        raise NovaPoshtaError(f"{step}: {', '.join(str(e) for e in errors)}")
    return data.get("data") or []


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


async def search_cities(api_key: str, query: str) -> list[dict]:
    """Топ-10 міст за FindByString (Address/getCities) -> [{ref, name}].

    Обрано getCities, не Address/searchSettlements: стабільна відповідь
    (Ref/Description), тоді як searchSettlements повертає інший formат
    (DeliveryCity замість Ref, data[0].Addresses[]) — легше зламати мовчки.
    Якщо якість пошуку виявиться слабкою на живому ключі — переглянути."""
    data = await _call(api_key, "Address", "getCities", {"FindByString": query, "Limit": _SEARCH_LIMIT})
    rows = _require_success(data, "getCities")
    return [{"ref": c["Ref"], "name": c["Description"]} for c in rows]


async def get_warehouses(api_key: str, city_ref: str) -> list[dict]:
    """Відділення міста (Address/getWarehouses) -> [{ref, name}] (назва вже
    включає номер і адресу — саме так НП віддає Description)."""
    data = await _call(api_key, "Address", "getWarehouses", {"CityRef": city_ref})
    rows = _require_success(data, "getWarehouses")
    return [{"ref": w["Ref"], "name": w["Description"]} for w in rows]


def _split_name(full_name: str) -> tuple[str, str]:
    """FirstName/LastName для Counterparty/ContactPerson save — НП вимагає
    окремі поля, у нас лише один рядок ПІБ з форми. Спліт по першому пробілу;
    без пробілу LastName дублює FirstName (приблизна евристика, не звірена
    з живим ключем)."""
    parts = full_name.strip().split(maxsplit=1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return full_name.strip(), full_name.strip()


@dataclass
class DocumentResult:
    ttn: str
    ref: str
    cost: Decimal
    estimated_delivery: str | None


async def create_document(
    api_key: str,
    *,
    sender_city_ref: str,
    sender_warehouse_ref: str,
    sender_phone: str,
    recipient_name: str,
    recipient_phone: str,
    recipient_city_ref: str,
    recipient_warehouse_ref: str,
    weight: float,
    description: str,
    cost: Decimal,
    cod_amount: Decimal | None,
) -> DocumentResult:
    """Створює накладну WarehouseWarehouse/Cash. П'ятикроковий ланцюг —
    НАЙМЕНШ звірена частина інтеграції (офіційні доки недоступні на момент
    написання, компільовано з незалежної пам'яті):

      1. Counterparty/save (PrivatePerson, CounterpartyProperty=Recipient)
         -> Ref одержувача.
      2. ContactPerson/save (CounterpartyRef з кроку 1) -> ContactRef
         одержувача. Явний окремий виклик, а не парсинг вкладеного
         ContactPerson з відповіді кроку 1 — форма тієї відповіді не
         підтверджена, явний save надійніший.
      3. Counterparty/getCounterparties (CounterpartyProperty=Sender) ->
         Ref відправника (перший результат — рахунок зазвичай один sender).
         НЕ кешується в Shop: тягнеться живим викликом щоразу.
      4. Counterparty/getCounterpartyContactPersons (Ref з кроку 3) ->
         ContactRef відправника (перший результат).
      5. InternetDocument/save зі зібраними Ref/ContactRef обох сторін.

    BackwardDeliveryData (накладений платіж) і сама ця послідовність —
    позначені як такі, що вимагають звірки при першому реальному підключенні
    ключа (так само, як PICKED_CODES/RETURNED_CODES вище)."""
    recipient_first, recipient_last = _split_name(recipient_name)

    recipient_data = _require_success(
        await _call(
            api_key,
            "Counterparty",
            "save",
            {
                "CityRef": recipient_city_ref,
                "FirstName": recipient_first,
                "LastName": recipient_last,
                "Phone": recipient_phone,
                "CounterpartyType": "PrivatePerson",
                "CounterpartyProperty": "Recipient",
            },
        ),
        "Counterparty/save (одержувач)",
    )
    recipient_ref = recipient_data[0]["Ref"]

    recipient_contact_data = _require_success(
        await _call(
            api_key,
            "ContactPerson",
            "save",
            {
                "CounterpartyRef": recipient_ref,
                "FirstName": recipient_first,
                "LastName": recipient_last,
                "Phone": recipient_phone,
            },
        ),
        "ContactPerson/save (одержувач)",
    )
    recipient_contact_ref = recipient_contact_data[0]["Ref"]

    sender_counterparties = _require_success(
        await _call(
            api_key,
            "Counterparty",
            "getCounterparties",
            {"CounterpartyProperty": "Sender", "Page": "1"},
        ),
        "Counterparty/getCounterparties (відправник)",
    )
    if not sender_counterparties:
        raise NovaPoshtaError("Не знайдено контрагента-відправника на цьому ключі НП")
    sender_ref = sender_counterparties[0]["Ref"]

    sender_contacts = _require_success(
        await _call(
            api_key,
            "Counterparty",
            "getCounterpartyContactPersons",
            {"Ref": sender_ref, "Page": "1"},
        ),
        "Counterparty/getCounterpartyContactPersons (відправник)",
    )
    if not sender_contacts:
        raise NovaPoshtaError("Не знайдено контактної особи відправника на цьому ключі НП")
    sender_contact_ref = sender_contacts[0]["Ref"]

    document_properties: dict = {
        "PayerType": "Recipient",
        "PaymentMethod": "Cash",
        "CargoType": "Parcel",
        "ServiceType": "WarehouseWarehouse",
        "SeatsAmount": "1",
        "Weight": str(weight),
        "Description": description,
        "Cost": str(cost),
        "CitySender": sender_city_ref,
        "SenderAddress": sender_warehouse_ref,
        "Sender": sender_ref,
        "ContactSender": sender_contact_ref,
        "SendersPhone": sender_phone,
        "CityRecipient": recipient_city_ref,
        "RecipientAddress": recipient_warehouse_ref,
        "Recipient": recipient_ref,
        "ContactRecipient": recipient_contact_ref,
        "RecipientsPhone": recipient_phone,
    }
    if cod_amount is not None:
        document_properties["BackwardDeliveryData"] = [
            {
                "PayerType": "Recipient",
                "CargoType": "Money",
                "RedeliveryString": str(cod_amount),
            }
        ]

    document_data = _require_success(
        await _call(api_key, "InternetDocument", "save", document_properties),
        "InternetDocument/save",
    )
    doc = document_data[0]
    return DocumentResult(
        ttn=doc["IntDocNumber"],
        ref=doc["Ref"],
        cost=Decimal(str(doc.get("CostOnSite", cost))),
        estimated_delivery=doc.get("EstimatedDeliveryDate"),
    )
