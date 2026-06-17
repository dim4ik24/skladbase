from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import db
from app.api import billing, catalog, finance, me, orders, public, shop, telegram


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    yield
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


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
