from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import db
from app.api import finance, me


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    yield
    await db.engine.dispose()


app = FastAPI(title="SkladBase", lifespan=lifespan)
app.include_router(me.router)
app.include_router(finance.router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
