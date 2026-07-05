# Backend (API + Trading) — Summary

**Status:** Complete. 115 tests pass (73 market + 21 db + 21 new), ruff-clean.
Verified end-to-end against the live simulator via lifespan.

## What Was Built

The FastAPI app and trading logic wiring the market-data and db layers together.

| File | Purpose |
|------|---------|
| `app/main.py` | The `app` FastAPI instance. Owns the single `PriceCache` + market data source, runs the 30s snapshot loop, mounts all routers + static files. |
| `app/portfolio/service.py` | `execute_trade()` and `build_portfolio()` — plain functions, the single validated trade path. |
| `app/routes/portfolio.py` | `/api/portfolio`, `/api/portfolio/trade`, `/api/portfolio/history`. |
| `app/routes/watchlist.py` | `/api/watchlist` GET/POST, `/api/watchlist/{ticker}` DELETE. |
| `app/routes/…` + `/api/health` (in main) | health check. |

## Shared instances (for the LLM engineer)

`app/main.py` constructs, at module level, the **single** source of truth:

```python
price_cache = PriceCache()
data_source = create_market_data_source(price_cache)
```

`lifespan` calls `data_source.start(list_watchlist())`, then sets them on
`app.state.price_cache` / `app.state.data_source`. **In a request handler, get the
cache with `request.app.state.price_cache`.** The chat route should do the same
and pass it into `execute_trade(...)`.

## Trade + valuation functions (call these directly from chat)

```python
from app.portfolio import execute_trade, build_portfolio

# Fills at the current cached price. Returns the inserted trade row.
# Raises ValueError with a user-facing message on any validation failure
# (bad side, qty <= 0, no price, insufficient cash/shares). Catch it and put
# the message in the chat reply.
execute_trade(ticker: str, side: str, quantity: float,
              cache: PriceCache, user_id="default") -> dict
# -> {"id","user_id","ticker","side","quantity","price","executed_at"}

# Portfolio context for the LLM prompt AND the GET /api/portfolio response.
build_portfolio(cache: PriceCache, user_id="default") -> dict
```

`build_portfolio` return shape:

```json
{
  "cash_balance": 9619.98,
  "positions": [
    {
      "ticker": "AAPL", "quantity": 2, "avg_cost": 190.01,
      "current_price": 191.30, "market_value": 382.60,
      "cost_basis": 380.02, "unrealized_pnl": 2.58,
      "unrealized_pnl_percent": 0.68
    }
  ],
  "positions_value": 382.60,
  "total_value": 10002.58,
  "total_unrealized_pnl": 2.58
}
```

`execute_trade` already applies the position/cash update, appends the trade,
and records a `portfolio_snapshots` row. Do NOT re-implement any of that in the
chat route — one message from the LLM with N trades = N calls to `execute_trade`,
collecting ValueErrors into the response so the model can tell the user.

`current_price` falls back to `avg_cost` if the cache has no price yet (so
valuation never divides by a missing price). Watchlist add/remove for AI actions:
`add_watchlist_ticker(t)` + `await data_source.add_ticker(t)` (and the remove pair).

## API endpoints (request / response)

### `GET /api/portfolio`
→ 200, the `build_portfolio` shape above.

### `POST /api/portfolio/trade`
Body: `{"ticker": "AAPL", "quantity": 5, "side": "buy"}`
→ 200 with the updated portfolio (same shape as GET /api/portfolio).
→ 400 `{"detail": "Insufficient cash: …"}` on validation failure.

### `GET /api/portfolio/history`
→ 200 `[{"total_value": 10000.0, "recorded_at": "2026-…Z"}, …]`, oldest first (P&L chart order).

### `GET /api/watchlist`
→ 200, list of ticker views (order = watchlist order). Each is the
`PriceUpdate.to_dict()` shape; fields are `null` before the first price arrives:
```json
{"ticker":"AAPL","price":190.01,"previous_price":190.01,"timestamp":1751.._,
 "change":0.0,"change_percent":0.0,"direction":"flat"}
```

### `POST /api/watchlist`
Body: `{"ticker": "PYPL"}` (case-insensitive; upper-cased server-side).
Adds to db + registers with the data source so prices start streaming.
→ 200 with the updated watchlist array.

### `DELETE /api/watchlist/{ticker}`
Removes from db + data source + price cache.
→ 200 with the updated watchlist array.

### `GET /api/health` → 200 `{"status": "ok"}`

### `GET /api/stream/prices` — unchanged, provided by the market team's `create_stream_router`.

## Deviations from PLAN.md §8 (frontend, please note)

- **No `FRONTEND_SUMMARY.md` existed at build time**, so responses follow PLAN §8
  literally. Flag any mismatch and I'll adjust.
- `GET /api/portfolio` returns the richer object above (PLAN lists the fields loosely;
  this includes per-position `market_value`/`cost_basis` and portfolio `positions_value`).
- `POST`/`DELETE` on watchlist and `POST /trade` **return the updated resource**
  (watchlist array / portfolio) rather than 201/204 — one round-trip for the UI.
- `/api/portfolio/history` items are trimmed to `{total_value, recorded_at}` (the two
  fields the P&L chart needs), not the full snapshot row.

## Tests

`backend/tests/portfolio/test_service.py` (13) — buy/sell, weighted-avg cost,
sell-to-zero deletes the row, sell at a loss, all validation errors, P&L math,
price fallback. `backend/tests/routes/test_routes.py` (8) — TestClient without
lifespan, injecting a seeded `PriceCache` + fake async source onto `app.state`
(the real simulator never starts in tests). Added `httpx` to the `dev` extra
(required by `fastapi.testclient`).

```bash
cd backend
uv run --extra dev pytest -q
uv run --extra dev ruff check app tests
```
