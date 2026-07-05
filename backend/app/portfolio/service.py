"""Portfolio valuation and trade execution.

`execute_trade` is the ONE place trades are validated and applied — both the
REST route and the LLM chat route call it, so its ValueError messages are
written to be shown directly to the user.
"""

from __future__ import annotations

from typing import Any

from app.db import (
    DEFAULT_USER_ID,
    delete_position,
    get_or_create_profile,
    get_position,
    insert_snapshot,
    insert_trade,
    list_positions,
    update_cash_balance,
    upsert_position,
)
from app.market import PriceCache

_EPS = 1e-9  # treat residual share quantities below this as zero


def build_portfolio(cache: PriceCache, user_id: str = DEFAULT_USER_ID) -> dict[str, Any]:
    """Full portfolio view: cash, per-position P&L, and totals.

    Current price comes from the live cache; before a ticker's first price
    arrives it falls back to avg_cost so valuation never breaks.
    """
    profile = get_or_create_profile(user_id)
    cash = profile["cash_balance"]

    positions: list[dict[str, Any]] = []
    positions_value = 0.0
    total_cost_basis = 0.0

    for pos in list_positions(user_id):
        ticker = pos["ticker"]
        quantity = pos["quantity"]
        avg_cost = pos["avg_cost"]
        current_price = cache.get_price(ticker)
        if current_price is None:
            current_price = avg_cost

        market_value = quantity * current_price
        cost_basis = quantity * avg_cost
        pnl = market_value - cost_basis
        pnl_pct = (pnl / cost_basis * 100) if cost_basis else 0.0

        positions_value += market_value
        total_cost_basis += cost_basis
        positions.append(
            {
                "ticker": ticker,
                "quantity": quantity,
                "avg_cost": round(avg_cost, 2),
                "current_price": round(current_price, 2),
                "market_value": round(market_value, 2),
                "cost_basis": round(cost_basis, 2),
                "unrealized_pnl": round(pnl, 2),
                "unrealized_pnl_percent": round(pnl_pct, 2),
            }
        )

    total_value = cash + positions_value
    total_pnl = positions_value - total_cost_basis
    return {
        "cash_balance": round(cash, 2),
        "positions": positions,
        "positions_value": round(positions_value, 2),
        "total_value": round(total_value, 2),
        "total_unrealized_pnl": round(total_pnl, 2),
    }


def execute_trade(
    ticker: str,
    side: str,
    quantity: float,
    cache: PriceCache,
    user_id: str = DEFAULT_USER_ID,
) -> dict[str, Any]:
    """Execute a market order at the current cached price. Returns the trade row.

    Raises ValueError (message safe to surface to the user) on any validation
    failure: bad side, non-positive quantity, no price, insufficient cash/shares.
    Updates positions (weighted-avg cost on buy, quantity reduction on sell),
    cash, the trades log, and records a portfolio snapshot.
    """
    ticker = ticker.upper().strip()
    side = side.lower().strip()

    if side not in ("buy", "sell"):
        raise ValueError(f"Invalid side '{side}': must be 'buy' or 'sell'.")
    if quantity <= 0:
        raise ValueError("Quantity must be greater than zero.")

    price = cache.get_price(ticker)
    if price is None:
        raise ValueError(f"No live price available for {ticker}.")

    profile = get_or_create_profile(user_id)
    cash = profile["cash_balance"]
    position = get_position(ticker, user_id)

    if side == "buy":
        cost = quantity * price
        if cost > cash:
            raise ValueError(
                f"Insufficient cash: {ticker} buy costs ${cost:,.2f}, "
                f"available ${cash:,.2f}."
            )
        if position:
            old_qty = position["quantity"]
            new_qty = old_qty + quantity
            new_avg = (old_qty * position["avg_cost"] + quantity * price) / new_qty
        else:
            new_qty = quantity
            new_avg = price
        upsert_position(ticker, new_qty, new_avg, user_id)
        update_cash_balance(cash - cost, user_id)
    else:  # sell
        held = position["quantity"] if position else 0.0
        if held < quantity:
            raise ValueError(
                f"Insufficient shares: cannot sell {quantity} {ticker}, "
                f"only {held} held."
            )
        proceeds = quantity * price
        remaining = held - quantity
        if remaining <= _EPS:
            delete_position(ticker, user_id)
        else:
            upsert_position(ticker, remaining, position["avg_cost"], user_id)
        update_cash_balance(cash + proceeds, user_id)

    trade = insert_trade(ticker, side, quantity, price, user_id)
    insert_snapshot(build_portfolio(cache, user_id)["total_value"], user_id)
    return trade
