"""FinAlly FastAPI application.

Owns the single PriceCache + market data source (shared by the SSE stream,
portfolio valuation, and trade execution). Runs a 30s portfolio-snapshot loop.
Serves the built frontend from ./static (mounted last so /api/* wins).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.db import init_db, insert_snapshot, list_watchlist
from app.market import PriceCache, create_market_data_source, create_stream_router
from app.portfolio import build_portfolio
from app.routes import chat, portfolio, watchlist

logger = logging.getLogger(__name__)

SNAPSHOT_INTERVAL_SECONDS = 30

# Single source of truth: producers write, SSE + portfolio + trades read.
price_cache = PriceCache()
data_source = create_market_data_source(price_cache)


async def _snapshot_loop() -> None:
    """Record total portfolio value every 30s (PLAN §7)."""
    while True:
        await asyncio.sleep(SNAPSHOT_INTERVAL_SECONDS)
        try:
            insert_snapshot(build_portfolio(price_cache)["total_value"])
        except Exception:  # noqa: BLE001 - a bad snapshot must not kill the loop
            logger.exception("snapshot loop failed")


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    init_db()
    await data_source.start(list_watchlist())
    app.state.price_cache = price_cache
    app.state.data_source = data_source
    snapshot_task = asyncio.create_task(_snapshot_loop())
    try:
        yield
    finally:
        snapshot_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await snapshot_task
        await data_source.stop()


app = FastAPI(title="FinAlly", lifespan=lifespan)

app.include_router(create_stream_router(price_cache))
app.include_router(portfolio.router)
app.include_router(watchlist.router)
app.include_router(chat.router)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


# Mounted last so it never shadows /api/*. Absent in local dev (built into the
# container image), so guard it.
if Path("static").is_dir():
    app.mount("/", StaticFiles(directory="static", html=True), name="static")
