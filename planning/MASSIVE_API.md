# Massive API — Research Notes

Massive (formerly Polygon.io — rebranded October 2025) is the real-market-data provider for FinAlly. This document covers what the API offers for our two needs: **live/near-real-time prices for a batch of tickers** and **end-of-day prices**. Used to design [MARKET_INTERFACE.md](MARKET_INTERFACE.md).

## Auth & SDK

- Sign up at massive.com, get an API key → `MASSIVE_API_KEY`.
- Official Python client: `pip install massive` (PyPI, MIT license, Python 3.9+).
- Old `polygon-api-client` package and `api.polygon.io` host still work — the new client defaults to `api.massive.com` but is backward compatible. Method names are unchanged from the Polygon-era client.

```python
from massive import RESTClient

client = RESTClient(api_key="...")  # or reads POLYGON_API_KEY / MASSIVE_API_KEY env var
```

## Endpoint 1: Batch snapshot (our "live price" source)

**`GET /v2/snapshot/locale/us/markets/stocks/tickers`** via `client.get_snapshot_all(market_type="stocks", tickers=[...])`

- Takes a list of tickers, returns latest trade/quote/day-aggregate for each in **one call** — this is why we poll instead of hitting a per-ticker endpoint in a loop.
- Response per ticker (`results[]`): `ticker`, `day` (o/h/l/c/v for the current session so far), `prevDay` (previous session's OHLCV), `lastTrade` (price `p`, size `s`, timestamp `t`), `lastQuote`, `todaysChange`, `todaysChangePerc`, `updated`.
- There's also a newer unified endpoint, `GET /v3/snapshot` (`client.list_universal_snapshots(type="stocks", ticker_any_of=[...])`, up to 250 tickers per call), which returns a similar shape (`last_trade`, `session`, `market_status`) across asset classes. `get_snapshot_all` is simpler and sufficient for stocks-only — that's what we use.
- Data recency depends on plan: Advanced/Business = real-time, Starter/Developer = 15-min delayed, Basic = end-of-day only.

```python
snapshot = client.get_snapshot_all(market_type="stocks", tickers=["AAPL", "GOOGL", "MSFT"])
for s in snapshot:
    price = s.last_trade.price if s.last_trade else s.day.close
    prev_close = s.prev_day.close
```

## Endpoint 2: Previous close / end-of-day

Two options depending on whether we want one ticker or the whole market:

- **`GET /v2/aggs/ticker/{ticker}/prev`** via `client.get_previous_close_agg(ticker)` — previous session's OHLCV for a single ticker. Fields: `o`, `h`, `l`, `c`, `v`, `vw`, `t` (ms timestamp).
- **`GET /v2/aggs/grouped/locale/us/market/stocks/{date}`** via `client.get_grouped_daily_aggs(date)` — OHLCV for **every** US ticker on one date, one call. `results[]` fields: `T` (ticker), `o`/`h`/`l`/`c`, `v`, `vw`, `n` (trade count), `t`.

For our watchlist (≤ a few dozen tickers), the batch snapshot's `prevDay` field already gives us previous close for free — we don't need a separate EOD call in normal operation. `get_previous_close_agg` / `get_grouped_daily_aggs` are documented here for completeness (e.g. a future "market closed" fallback) but aren't in FinAlly's initial call path.

## Rate limits

| Plan | Snapshot recency | Calls/min |
|---|---|---|
| Free (Basic) | End-of-day only | 5/min |
| Starter/Developer | 15-min delayed | plan-dependent, still modest |
| Advanced/Business | Real-time | high |

FinAlly targets the **free tier** by default (students won't all buy paid plans), so:

- Poll `get_snapshot_all` on an interval, not per-request. 5 calls/min → 1 call every 15s is the safe default, configurable via `poll_interval` for anyone on a paid plan.
- One call covers the entire watchlist regardless of ticker count (up to the API's per-call ticker limit), so watchlist size doesn't change the rate-limit math.

## Errors & edge cases

- Unknown ticker in a snapshot request → that ticker comes back with an error/empty entry in `results[]` rather than failing the whole call; the rest of the batch still returns.
- Outside market hours, `last_trade` may be null/stale — fall back to `day.close` / `prevDay.close`.
- Network/auth errors raise from the `massive` client — wrap the poll loop so one bad tick doesn't kill the background task (log and retry next interval).
