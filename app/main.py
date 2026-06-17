from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import db
from app.api import (
    billing,
    catalog,
    finance,
    inventory,
    me,
    orders,
    payment_webhooks,
    public,
    shop,
    telegram,
)
from app.config import settings
from app.scheduler import create_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    scheduler = create_scheduler() if settings.RUN_SCHEDULER else None
    if scheduler is not None:
        scheduler.start()

    yield

    if scheduler is not None:
        scheduler.shutdown(wait=False)
    await db.engine.dispose()


app = FastAPI(title="SkladBase", lifespan=lifespan)
app.include_router(me.router)
app.include_router(finance.router)
app.include_router(catalog.router)
app.include_router(orders.router)
app.include_router(public.router)
app.include_router(shop.router)
app.include_router(billing.router)
app.include_router(telegram.router)
app.include_router(payment_webhooks.router)
app.include_router(inventory.router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
