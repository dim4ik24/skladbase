from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app import db
from app.api import (
    billing,
    catalog,
    finance,
    inventory,
    me,
    np,
    np_documents,
    orders,
    payment_webhooks,
    public,
    shop,
    team,
    telegram,
)
from app.config import settings
from app.scheduler import create_scheduler
from app.security.proxy_headers import ProxyHeadersMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # Прод: RUN_SCHEDULER=False тут — web-воркери не піднімають крони, інакше
    # кожна реплікa web-процесу запустила б свій AsyncIOScheduler і джоби
    # стрільнули б N разів. Планувальник живе окремим процесом — app/worker.py
    # (python -m app.worker), там RUN_SCHEDULER=True не потрібен — він і не
    # читає цей прапорець.
    scheduler = create_scheduler() if settings.RUN_SCHEDULER else None
    if scheduler is not None:
        scheduler.start()

    yield

    if scheduler is not None:
        scheduler.shutdown(wait=False)
    await db.engine.dispose()


app = FastAPI(title="SkladBase", lifespan=lifespan)
app.add_middleware(
    ProxyHeadersMiddleware,
    trusted_proxies=frozenset(
        ip.strip() for ip in settings.TRUSTED_PROXY_IPS.split(",") if ip.strip()
    ),
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(me.router)
app.include_router(finance.router)
app.include_router(catalog.router)
app.include_router(orders.router)
app.include_router(public.router)
app.include_router(shop.router)
app.include_router(team.router)
app.include_router(billing.router)
app.include_router(telegram.router)
app.include_router(payment_webhooks.router)
app.include_router(inventory.router)
app.include_router(np.router)
app.include_router(np_documents.router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


_tma_dist = Path(__file__).resolve().parent.parent / "frontend" / "app" / "dist"
if _tma_dist.is_dir():
    app.mount("/", StaticFiles(directory=_tma_dist, html=True), name="tma")
