"""
Stage 0 acceptance tests.

Criteria:
  1. GET /health -> HTTP 200
  2. All tables from Base.metadata can be created (schema is self-consistent)
  3. State machine guard in SubscriptionService rejects disallowed transitions
"""
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import create_async_engine

from app.main import app
from app.models import Base, SubStatus
from app.services.subscriptions import SubscriptionError, SubscriptionService

EXPECTED_TABLES = {
    "shops",
    "memberships",
    "product_templates",
    "products",
    "variants",
    "reservations",
    "stock_movements",
    "orders",
    "order_items",
    "plans",
    "subscriptions",
    "payments",
    "promo_codes",
    "promo_redemptions",
}


@pytest.mark.asyncio
async def test_health_returns_200():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        r = await client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_schema_creates_all_tables():
    """Base.metadata.create_all must produce every expected table."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with engine.connect() as conn:
        tables = set(
            await conn.run_sync(lambda c: inspect(c).get_table_names())
        )
    await engine.dispose()
    missing = EXPECTED_TABLES - tables
    assert not missing, f"Missing tables after create_all: {missing}"


def test_subscription_state_machine_rejects_invalid_transition():
    """expired -> canceled is not an allowed transition."""
    from unittest.mock import MagicMock

    sub = MagicMock()
    sub.status = SubStatus.expired

    svc = SubscriptionService(session=MagicMock())
    with pytest.raises(SubscriptionError):
        svc._transition(sub, SubStatus.canceled)
