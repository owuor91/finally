"""Watchlist REST endpoints. Mutations also (de)register the ticker with the
live market data source so prices start/stop streaming for it."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.db import add_watchlist_ticker, list_watchlist, remove_watchlist_ticker
from app.market import PriceCache

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])


class WatchlistRequest(BaseModel):
    ticker: str


def _view(ticker: str, cache: PriceCache) -> dict[str, Any]:
    update = cache.get(ticker)
    if update is not None:
        return update.to_dict()
    return {
        "ticker": ticker,
        "price": None,
        "previous_price": None,
        "timestamp": None,
        "change": None,
        "change_percent": None,
        "direction": None,
    }


def _watchlist(cache: PriceCache) -> list[dict[str, Any]]:
    return [_view(t, cache) for t in list_watchlist()]


@router.get("")
def get_watchlist(request: Request) -> list[dict[str, Any]]:
    return _watchlist(request.app.state.price_cache)


@router.post("")
async def add(body: WatchlistRequest, request: Request) -> list[dict[str, Any]]:
    ticker = body.ticker.upper().strip()
    add_watchlist_ticker(ticker)
    await request.app.state.data_source.add_ticker(ticker)
    return _watchlist(request.app.state.price_cache)


@router.delete("/{ticker}")
async def remove(ticker: str, request: Request) -> list[dict[str, Any]]:
    ticker = ticker.upper().strip()
    remove_watchlist_ticker(ticker)
    await request.app.state.data_source.remove_ticker(ticker)
    return _watchlist(request.app.state.price_cache)
