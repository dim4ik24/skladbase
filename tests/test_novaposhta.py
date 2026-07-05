"""
Клієнт Нова Пошта (app/services/novaposhta.py) — ping/track/довідники/
create_document, без живого API.

httpx замокано через monkeypatch.setattr(httpx, "AsyncClient", ...) — той самий
патерн, що й tests/test_stage4b.py для вихідного вебхука.

Criteria:
  1. ping: success=true -> True; success=false -> False; мережевий збій -> False
  2. track: success=true -> список data; success=false -> NovaPoshtaError
  3. track батчить документи по 100 за виклик (ліміт НП API)
  4. track: мережевий збій -> NovaPoshtaError
  5. запит має правильні modelName/calledMethod/methodProperties
  6. search_cities/get_warehouses мапують Ref/Description -> ref/name
  7. create_document: 5-кроковий ланцюг у правильному порядку з правильними
     полями (recipient Counterparty->ContactPerson, sender Counterparty
     getCounterparties->getCounterpartyContactPersons, InternetDocument/save)
  8. create_document: cod_amount=None -> без BackwardDeliveryData; заданий ->
     BackwardDeliveryData з RedeliveryString
  9. create_document: помилка на будь-якому кроці -> NovaPoshtaError, ланцюг
     не продовжується далі
"""
from __future__ import annotations

from decimal import Decimal

import httpx
import pytest

from app.services import novaposhta


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def json(self) -> dict:
        return self._payload


class _RecordingAsyncClient:
    """Записує POST-запити й повертає задану відповідь замість реального HTTP.

    response_by_key: (modelName, calledMethod) -> payload, для тестів, де
    один виклик робить ДЕКІЛЬКА НП-запитів з різними очікуваними відповідями
    (create_document). Якщо ключа нема — фолбек на response_payload."""

    calls: list[dict] = []
    response_payload: dict = {"success": True, "data": []}
    response_by_key: dict[tuple[str, str], dict] = {}

    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self) -> "_RecordingAsyncClient":
        return self

    async def __aexit__(self, *exc_info) -> bool:
        return False

    async def post(self, url, *, json) -> _FakeResponse:
        _RecordingAsyncClient.calls.append({"url": url, "json": json})
        key = (json.get("modelName"), json.get("calledMethod"))
        payload = _RecordingAsyncClient.response_by_key.get(key, _RecordingAsyncClient.response_payload)
        return _FakeResponse(payload)


class _FailingAsyncClient:
    """Симулює недосяжний НП API (таймаут/мережева помилка)."""

    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self) -> "_FailingAsyncClient":
        return self

    async def __aexit__(self, *exc_info) -> bool:
        return False

    async def post(self, url, *, json):
        raise httpx.ConnectTimeout("simulated timeout")


@pytest.fixture(autouse=True)
def _reset_recording_client():
    _RecordingAsyncClient.calls = []
    _RecordingAsyncClient.response_payload = {"success": True, "data": []}
    _RecordingAsyncClient.response_by_key = {}
    yield


@pytest.mark.asyncio
async def test_ping_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(httpx, "AsyncClient", _RecordingAsyncClient)
    _RecordingAsyncClient.response_payload = {"success": True, "data": [{"Description": "Київ"}]}

    assert await novaposhta.ping("test-key") is True
    call = _RecordingAsyncClient.calls[0]
    assert call["json"]["modelName"] == "Address"
    assert call["json"]["calledMethod"] == "getCities"
    assert call["json"]["apiKey"] == "test-key"


@pytest.mark.asyncio
async def test_ping_invalid_key_returns_false(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(httpx, "AsyncClient", _RecordingAsyncClient)
    _RecordingAsyncClient.response_payload = {"success": False, "errors": ["Invalid API key"]}

    assert await novaposhta.ping("bad-key") is False


@pytest.mark.asyncio
async def test_ping_network_error_returns_false(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(httpx, "AsyncClient", _FailingAsyncClient)

    assert await novaposhta.ping("test-key") is False


@pytest.mark.asyncio
async def test_track_returns_data_list(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(httpx, "AsyncClient", _RecordingAsyncClient)
    _RecordingAsyncClient.response_payload = {
        "success": True,
        "data": [{"Number": "20450000000000", "StatusCode": "9", "Status": "Отримано"}],
    }

    result = await novaposhta.track("test-key", ["20450000000000"])
    assert result == [{"Number": "20450000000000", "StatusCode": "9", "Status": "Отримано"}]

    call = _RecordingAsyncClient.calls[0]
    assert call["json"]["modelName"] == "TrackingDocument"
    assert call["json"]["calledMethod"] == "getStatusDocuments"
    assert call["json"]["methodProperties"]["Documents"] == [{"DocumentNumber": "20450000000000"}]


@pytest.mark.asyncio
async def test_track_batches_over_100_documents(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(httpx, "AsyncClient", _RecordingAsyncClient)
    _RecordingAsyncClient.response_payload = {"success": True, "data": []}

    ttns = [f"ttn-{i}" for i in range(150)]
    await novaposhta.track("test-key", ttns)

    assert len(_RecordingAsyncClient.calls) == 2
    assert len(_RecordingAsyncClient.calls[0]["json"]["methodProperties"]["Documents"]) == 100
    assert len(_RecordingAsyncClient.calls[1]["json"]["methodProperties"]["Documents"]) == 50


@pytest.mark.asyncio
async def test_track_raises_on_success_false(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(httpx, "AsyncClient", _RecordingAsyncClient)
    _RecordingAsyncClient.response_payload = {"success": False, "errors": ["Invalid ttn"]}

    with pytest.raises(novaposhta.NovaPoshtaError):
        await novaposhta.track("test-key", ["bad-ttn"])


@pytest.mark.asyncio
async def test_track_raises_on_network_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(httpx, "AsyncClient", _FailingAsyncClient)

    with pytest.raises(novaposhta.NovaPoshtaError):
        await novaposhta.track("test-key", ["ttn"])


# --------------------------------------------------------------------------- #
#  Довідники: міста / відділення
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_search_cities_maps_ref_and_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(httpx, "AsyncClient", _RecordingAsyncClient)
    _RecordingAsyncClient.response_payload = {
        "success": True,
        "data": [{"Ref": "city-ref-1", "Description": "Київ"}],
    }

    result = await novaposhta.search_cities("test-key", "Киї")
    assert result == [{"ref": "city-ref-1", "name": "Київ"}]

    call = _RecordingAsyncClient.calls[0]
    assert call["json"]["modelName"] == "Address"
    assert call["json"]["calledMethod"] == "getCities"
    assert call["json"]["methodProperties"]["FindByString"] == "Киї"


@pytest.mark.asyncio
async def test_get_warehouses_maps_ref_and_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(httpx, "AsyncClient", _RecordingAsyncClient)
    _RecordingAsyncClient.response_payload = {
        "success": True,
        "data": [{"Ref": "wh-ref-1", "Description": "Відділення №1: вул. Шевченка, 1"}],
    }

    result = await novaposhta.get_warehouses("test-key", "city-ref-1")
    assert result == [{"ref": "wh-ref-1", "name": "Відділення №1: вул. Шевченка, 1"}]

    call = _RecordingAsyncClient.calls[0]
    assert call["json"]["modelName"] == "Address"
    assert call["json"]["calledMethod"] == "getWarehouses"
    assert call["json"]["methodProperties"]["CityRef"] == "city-ref-1"


# --------------------------------------------------------------------------- #
#  create_document: 5-кроковий ланцюг
# --------------------------------------------------------------------------- #
_HAPPY_PATH_RESPONSES: dict[tuple[str, str], dict] = {
    ("Counterparty", "save"): {"success": True, "data": [{"Ref": "recipient-ref"}]},
    ("ContactPerson", "save"): {"success": True, "data": [{"Ref": "recipient-contact-ref"}]},
    ("Counterparty", "getCounterparties"): {"success": True, "data": [{"Ref": "sender-ref"}]},
    ("Counterparty", "getCounterpartyContactPersons"): {
        "success": True,
        "data": [{"Ref": "sender-contact-ref"}],
    },
    ("InternetDocument", "save"): {
        "success": True,
        "data": [
            {
                "IntDocNumber": "20450000000001",
                "Ref": "doc-ref",
                "CostOnSite": 75,
                "EstimatedDeliveryDate": "2026-07-06",
            }
        ],
    },
}


async def _call_create_document(cod_amount: Decimal | None = Decimal("450")) -> novaposhta.DocumentResult:
    return await novaposhta.create_document(
        "test-key",
        sender_city_ref="sender-city-ref",
        sender_warehouse_ref="sender-wh-ref",
        sender_phone="380501112233",
        recipient_name="Іван Петренко",
        recipient_phone="380671112233",
        recipient_city_ref="rec-city-ref",
        recipient_warehouse_ref="rec-wh-ref",
        weight=0.5,
        description="Футболка",
        cost=Decimal("450"),
        cod_amount=cod_amount,
    )


@pytest.mark.asyncio
async def test_create_document_happy_path_chains_calls_in_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(httpx, "AsyncClient", _RecordingAsyncClient)
    _RecordingAsyncClient.response_by_key = dict(_HAPPY_PATH_RESPONSES)

    result = await _call_create_document()

    assert result.ttn == "20450000000001"
    assert result.ref == "doc-ref"
    assert result.cost == Decimal("75")
    assert result.estimated_delivery == "2026-07-06"

    methods = [(c["json"]["modelName"], c["json"]["calledMethod"]) for c in _RecordingAsyncClient.calls]
    assert methods == [
        ("Counterparty", "save"),
        ("ContactPerson", "save"),
        ("Counterparty", "getCounterparties"),
        ("Counterparty", "getCounterpartyContactPersons"),
        ("InternetDocument", "save"),
    ]

    recipient_save = _RecordingAsyncClient.calls[0]["json"]["methodProperties"]
    assert recipient_save["FirstName"] == "Іван"
    assert recipient_save["LastName"] == "Петренко"
    assert recipient_save["CounterpartyType"] == "PrivatePerson"
    assert recipient_save["CounterpartyProperty"] == "Recipient"

    contact_save = _RecordingAsyncClient.calls[1]["json"]["methodProperties"]
    assert contact_save["CounterpartyRef"] == "recipient-ref"

    sender_contacts_call = _RecordingAsyncClient.calls[3]["json"]["methodProperties"]
    assert sender_contacts_call["Ref"] == "sender-ref"

    doc_save = _RecordingAsyncClient.calls[4]["json"]["methodProperties"]
    assert doc_save["Recipient"] == "recipient-ref"
    assert doc_save["ContactRecipient"] == "recipient-contact-ref"
    assert doc_save["Sender"] == "sender-ref"
    assert doc_save["ContactSender"] == "sender-contact-ref"
    assert doc_save["CitySender"] == "sender-city-ref"
    assert doc_save["SenderAddress"] == "sender-wh-ref"
    assert doc_save["CityRecipient"] == "rec-city-ref"
    assert doc_save["RecipientAddress"] == "rec-wh-ref"
    assert doc_save["PaymentMethod"] == "Cash"
    assert doc_save["CargoType"] == "Parcel"
    assert doc_save["ServiceType"] == "WarehouseWarehouse"


@pytest.mark.asyncio
async def test_create_document_with_cod_sets_backward_delivery_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(httpx, "AsyncClient", _RecordingAsyncClient)
    _RecordingAsyncClient.response_by_key = dict(_HAPPY_PATH_RESPONSES)

    await _call_create_document(cod_amount=Decimal("450"))

    doc_save = _RecordingAsyncClient.calls[-1]["json"]["methodProperties"]
    assert doc_save["BackwardDeliveryData"] == [
        {"PayerType": "Recipient", "CargoType": "Money", "RedeliveryString": "450"}
    ]


@pytest.mark.asyncio
async def test_create_document_without_cod_omits_backward_delivery_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(httpx, "AsyncClient", _RecordingAsyncClient)
    _RecordingAsyncClient.response_by_key = dict(_HAPPY_PATH_RESPONSES)

    await _call_create_document(cod_amount=None)

    doc_save = _RecordingAsyncClient.calls[-1]["json"]["methodProperties"]
    assert "BackwardDeliveryData" not in doc_save


@pytest.mark.asyncio
async def test_create_document_fails_fast_on_recipient_save_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(httpx, "AsyncClient", _RecordingAsyncClient)
    _RecordingAsyncClient.response_by_key = {
        ("Counterparty", "save"): {"success": False, "errors": ["Invalid phone number"]},
    }

    with pytest.raises(novaposhta.NovaPoshtaError, match="Invalid phone number"):
        await _call_create_document()

    # ланцюг не продовжився далі першого кроку, що впав
    assert len(_RecordingAsyncClient.calls) == 1


@pytest.mark.asyncio
async def test_create_document_fails_when_no_sender_counterparty_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(httpx, "AsyncClient", _RecordingAsyncClient)
    responses = dict(_HAPPY_PATH_RESPONSES)
    responses[("Counterparty", "getCounterparties")] = {"success": True, "data": []}
    _RecordingAsyncClient.response_by_key = responses

    with pytest.raises(novaposhta.NovaPoshtaError, match="відправника"):
        await _call_create_document()

    # не дійшло до getCounterpartyContactPersons/InternetDocument
    assert len(_RecordingAsyncClient.calls) == 3
