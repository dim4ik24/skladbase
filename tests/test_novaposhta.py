"""
Клієнт Нова Пошта (app/services/novaposhta.py) — ping/track, без живого API.

httpx замокано через monkeypatch.setattr(httpx, "AsyncClient", ...) — той самий
патерн, що й tests/test_stage4b.py для вихідного вебхука.

Criteria:
  1. ping: success=true -> True; success=false -> False; мережевий збій -> False
  2. track: success=true -> список data; success=false -> NovaPoshtaError
  3. track батчить документи по 100 за виклик (ліміт НП API)
  4. track: мережевий збій -> NovaPoshtaError
  5. запит має правильні modelName/calledMethod/methodProperties
"""
from __future__ import annotations

import httpx
import pytest

from app.services import novaposhta


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def json(self) -> dict:
        return self._payload


class _RecordingAsyncClient:
    """Записує POST-запити й повертає задану відповідь замість реального HTTP."""

    calls: list[dict] = []
    response_payload: dict = {"success": True, "data": []}

    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self) -> "_RecordingAsyncClient":
        return self

    async def __aexit__(self, *exc_info) -> bool:
        return False

    async def post(self, url, *, json) -> _FakeResponse:
        _RecordingAsyncClient.calls.append({"url": url, "json": json})
        return _FakeResponse(_RecordingAsyncClient.response_payload)


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
