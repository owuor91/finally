"""Portfolio + trade REST endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.db import list_snapshots
from app.portfolio import build_portfolio, execute_trade

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


class TradeRequest(BaseModel):
    ticker: str
    quantity: float
    side: str


@router.get("")
def get_portfolio(request: Request) -> dict[str, Any]:
    return build_portfolio(request.app.state.price_cache)


@router.post("/trade")
def post_trade(body: TradeRequest, request: Request) -> dict[str, Any]:
    cache = request.app.state.price_cache
    try:
        execute_trade(body.ticker, body.side, body.quantity, cache)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return build_portfolio(cache)


@router.get("/history")
def get_history() -> list[dict[str, Any]]:
    return [
        {"total_value": s["total_value"], "recorded_at": s["recorded_at"]}
        for s in list_snapshots()
    ]
