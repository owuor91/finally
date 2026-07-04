# Market Data Backend — Detailed Design

Consolidated implementation design for `backend/market/`, synthesizing [MARKET_INTERFACE.md](MARKET_INTERFACE.md), [MARKET_SIMULATOR.md](MARKET_SIMULATOR.md), and [MASSIVE_API.md](MASSIVE_API.md) into one buildable spec, plus the FastAPI wiring that connects the module to the rest of the app (lifespan startup, the SSE endpoint, config, and tests). See [PLAN.md](PLAN.md) §6–8 for the product-level requirements this implements.

## 1. Goals & non-goals

**Goals**
- One async interface (`MarketDataSource`) with two implementations — `SimulatorDataSource` (default) and `MassiveDataSource` (real data, opt-in via `MASSIVE_API_KEY`) — selected once at process startup.
- A single in-memory `PriceCache` that both implementations write into and every consumer (SSE stream, trade execution, portfolio valuation) reads from. Consumers never branch on which source is active.
- Correlated, realistic-looking simulated price action with occasional shock events.
- A resilient Massive REST poller that respects free-tier rate limits and survives transient API failures without killing the background task.

**Non-goals**
- No WebSocket market data (REST polling only for Massive; SSE only for our own client-facing stream).
- No per-ticker historical backfill beyond what `prevDay`/`day` snapshot fields give us for free.
- No multi-source aggregation (Massive vs. simulator is exclusive, not blended).

## 2. Module layout

```
backend/market/
├── __init__.py
├── models.py          # PriceUpdate
├── interface.py        # MarketDataSource (ABC)
├── cache.py            # PriceCache
├── simulator.py        # SimulatorDataSource + GBMSimulator (GBM)
├── massive_client.py    # MassiveDataSource (REST poller)
├── factory.py          # create_market_data_source()
└── seed_prices.py       # SEED_PRICES, GBM_PARAMS, CORRELATION
```

`backend/market/` has no dependency on FastAPI, the database, or the LLM layer — it is a standalone async data module. The app wires it in at startup (§8) and reads from it in routes (§9).

## 3. Data model — `models.py`

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class PriceUpdate:
    ticker: str
    price: float
    previous_price: float
    timestamp: str    # ISO 8601, UTC
    direction: str     # "up" | "down" | "flat"
```

Immutable and source-agnostic — both the simulator and the Massive client produce exactly this shape. Direction is precomputed once per update rather than derived repeatedly by consumers:

```python
def direction_of(price: float, previous_price: float) -> str:
    if price > previous_price:
        return "up"
    if price < previous_price:
        return "down"
    return "flat"
```

## 4. The interface — `interface.py`

```python
from abc import ABC, abstractmethod

class MarketDataSource(ABC):
    @abstractmethod
    async def start(self, tickers: list[str]) -> None: ...

    @abstractmethod
    async def stop(self) -> None: ...

    @abstractmethod
    async def add_ticker(self, ticker: str) -> None: ...

    @abstractmethod
    async def remove_ticker(self, ticker: str) -> None: ...
```

Both implementations write into a shared `PriceCache` rather than returning data from these methods — `start()` launches a background `asyncio.Task` that keeps writing until `stop()` cancels it. This is the key design decision that makes the two sources interchangeable: nothing about "how" a price is produced leaks past this boundary.

`add_ticker`/`remove_ticker` mutate the running background loop's ticker set in place; they do not restart `start()`.

## 5. The shared cache — `cache.py`

```python
import threading
from .models import PriceUpdate

class PriceCache:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._prices: dict[str, PriceUpdate] = {}
        self._version = 0

    def set(self, update: PriceUpdate) -> None:
        with self._lock:
            self._prices[update.ticker] = update
            self._version += 1

    def get(self, ticker: str) -> PriceUpdate | None:
        return self._prices.get(ticker)

    def get_all(self) -> dict[str, PriceUpdate]:
        with self._lock:
            return dict(self._prices)

    def remove(self, ticker: str) -> None:
        with self._lock:
            self._prices.pop(ticker, None)
            self._version += 1

    @property
    def version(self) -> int:
        return self._version
```

`threading.Lock` (not an `asyncio.Lock`) is deliberate: writes happen off the asyncio loop's synchronous hot path in a way that's cheap to make thread-safe regardless of whether a future data source runs its I/O in a thread (Massive's client does, via `asyncio.to_thread`). Reads (`get_all`) are O(n) dict copies, fine at watchlist scale (tens of tickers).

`version` is a change counter — bumped on every `set`/`remove`. Nothing currently reads it (the SSE endpoint just re-emits `get_all()` on a fixed cadence per PLAN.md §6), but it's cheap to keep for a future diffing optimization ("only emit if `version` changed since last tick"). Delete it if that need never materializes — don't build the diffing consumer preemptively.

## 6. Simulator — `simulator.py` + `seed_prices.py`

The default source. No external dependencies beyond `numpy` (for the Cholesky decomposition) and stdlib `asyncio`/`math`/`random`.

### 6.1 Why GBM

Geometric Brownian motion is the standard toy stock-price model: `dS = S·(μ dt + σ dW)` — drift `μ` plus volatility `σ` scaling a random shock. In log-return form (always positive, standard for this kind of sim):

```
price_new = price_old * exp((μ - σ²/2)·dt + σ·√dt·Z)
```

`Z` ~ N(0, 1). Rather than annualizing `μ`/`σ` and converting to a `dt` fraction of a trading year, params are tuned directly per 500ms tick — simpler, and the only thing that matters is "does it look right at this cadence."

### 6.2 Seed data — `seed_prices.py`

```python
SEED_PRICES = {
    "AAPL": 190.0, "GOOGL": 175.0, "MSFT": 420.0, "AMZN": 185.0,
    "TSLA": 250.0, "NVDA": 130.0, "META": 560.0, "JPM": 210.0,
    "V": 280.0, "NFLX": 700.0,
}

# Per-ticker GBM params, tuned per-tick (not annualized) for a lively
# look at 500ms cadence without runtime unit conversion.
GBM_PARAMS = {
    "AAPL":  {"drift": 0.00001, "vol": 0.0008, "group": "tech"},
    "GOOGL": {"drift": 0.00001, "vol": 0.0009, "group": "tech"},
    "MSFT":  {"drift": 0.00001, "vol": 0.0007, "group": "tech"},
    "AMZN":  {"drift": 0.00001, "vol": 0.0010, "group": "tech"},
    "TSLA":  {"drift": 0.00002, "vol": 0.0020, "group": "tech"},   # more volatile
    "NVDA":  {"drift": 0.00002, "vol": 0.0018, "group": "tech"},
    "META":  {"drift": 0.00001, "vol": 0.0012, "group": "tech"},
    "JPM":   {"drift": 0.00001, "vol": 0.0006, "group": "finance"},
    "V":     {"drift": 0.00001, "vol": 0.0006, "group": "finance"},
    "NFLX":  {"drift": 0.00001, "vol": 0.0014, "group": "tech"},
}

DEFAULT_PARAMS = {"drift": 0.0, "vol": 0.0010, "group": "other"}

CORRELATION = {
    ("tech", "tech"): 0.6,
    ("finance", "finance"): 0.5,
    ("tech", "finance"): 0.3,
    ("other", "other"): 0.0,
}
```

Unseen tickers added at runtime (`add_ticker`) get a random seed price in `$50–$300` and `DEFAULT_PARAMS` (mid-range vol, no drift, uncorrelated `"other"` group) — see §6.5.

### 6.3 Correlation matrix

Independent draws per ticker look wrong (real tech names move together). Build a symmetric correlation matrix from each ticker's `group`, decompose it with Cholesky, and multiply a vector of independent standard normals by the resulting lower-triangular matrix each tick to produce correlated draws:

```python
import numpy as np

def _pair_corr(group_a: str, group_b: str) -> float:
    if group_a == group_b:
        return CORRELATION.get((group_a, group_a), 0.0)
    return CORRELATION.get(
        (group_a, group_b), CORRELATION.get((group_b, group_a), 0.0)
    )

def build_corr_matrix(tickers: list[str]) -> np.ndarray:
    groups = [GBM_PARAMS.get(t, DEFAULT_PARAMS)["group"] for t in tickers]
    n = len(tickers)
    matrix = np.eye(n)
    for i in range(n):
        for j in range(i + 1, n):
            rho = _pair_corr(groups[i], groups[j])
            matrix[i, j] = matrix[j, i] = rho
    return matrix
```

A plain correlation matrix built this way is guaranteed positive-semidefinite here because all off-diagonal entries share one of three fixed values driven by only two groups' pairwise correlations — in general, arbitrary hand-picked correlations aren't guaranteed PSD, so if `GBM_PARAMS`/`CORRELATION` grow more groups later, validate with `np.linalg.cholesky` at startup and fall back to the identity matrix (independent draws) on `LinAlgError` rather than crashing.

### 6.4 `GBMSimulator`

```python
import math
import random

class GBMSimulator:
    def __init__(self, tickers: list[str]) -> None:
        self._tickers = list(tickers)
        self._prices = {
            t: SEED_PRICES.get(t, random.uniform(50, 300)) for t in self._tickers
        }
        self._chol = self._rebuild_cholesky()

    @property
    def prices(self) -> dict[str, float]:
        return dict(self._prices)

    def add_ticker(self, ticker: str) -> None:
        if ticker in self._prices:
            return
        self._tickers.append(ticker)
        self._prices[ticker] = SEED_PRICES.get(ticker, random.uniform(50, 300))
        self._chol = self._rebuild_cholesky()

    def remove_ticker(self, ticker: str) -> None:
        if ticker not in self._prices:
            return
        self._tickers.remove(ticker)
        del self._prices[ticker]
        self._chol = self._rebuild_cholesky()

    def tick(self) -> dict[str, float]:
        z = np.random.standard_normal(len(self._tickers))
        correlated_z = self._chol @ z
        for i, ticker in enumerate(self._tickers):
            params = GBM_PARAMS.get(ticker, DEFAULT_PARAMS)
            drift, vol = params["drift"], params["vol"]
            self._prices[ticker] *= math.exp(
                drift - 0.5 * vol**2 + vol * correlated_z[i]
            )
        self._maybe_shock()
        return dict(self._prices)

    def _rebuild_cholesky(self) -> np.ndarray:
        try:
            return np.linalg.cholesky(build_corr_matrix(self._tickers))
        except np.linalg.LinAlgError:
            return np.eye(len(self._tickers))

    def _maybe_shock(self) -> None:
        for ticker in self._tickers:
            if random.random() < 0.001:
                direction = random.choice([1, -1])
                magnitude = random.uniform(0.02, 0.05)
                self._prices[ticker] *= 1 + direction * magnitude
```

The Cholesky matrix is recomputed only when the ticker set changes (`add_ticker`/`remove_ticker`), not every tick — it's O(n³) and the ticker set changes rarely (watchlist edits) compared to ticks (every 500ms).

Shock events: per tick, per ticker, an independent ~0.1% chance of a sudden 2–5% jump, giving the demo occasional "notable move" moments without dominating normal price action.

### 6.5 `SimulatorDataSource`

Wraps `GBMSimulator` in the `MarketDataSource` interface:

```python
import asyncio
from datetime import datetime, timezone
from .cache import PriceCache
from .interface import MarketDataSource
from .models import PriceUpdate, direction_of
from .simulator_core import GBMSimulator  # or wherever GBMSimulator lives

class SimulatorDataSource(MarketDataSource):
    def __init__(self, price_cache: PriceCache, tick_interval: float = 0.5) -> None:
        self._cache = price_cache
        self._interval = tick_interval
        self._sim: GBMSimulator | None = None
        self._task: asyncio.Task | None = None

    async def start(self, tickers: list[str]) -> None:
        self._sim = GBMSimulator(tickers)
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def add_ticker(self, ticker: str) -> None:
        self._sim.add_ticker(ticker)

    async def remove_ticker(self, ticker: str) -> None:
        self._sim.remove_ticker(ticker)
        self._cache.remove(ticker)

    async def _run(self) -> None:
        while True:
            await asyncio.sleep(self._interval)
            prev_prices = self._sim.prices
            new_prices = self._sim.tick()
            now = datetime.now(timezone.utc).isoformat()
            for ticker, price in new_prices.items():
                prev = prev_prices[ticker]
                self._cache.set(PriceUpdate(
                    ticker=ticker,
                    price=price,
                    previous_price=prev,
                    timestamp=now,
                    direction=direction_of(price, prev),
                ))
```

Note `stop()` awaits the cancelled task to let cancellation actually propagate — fire-and-forget `.cancel()` alone doesn't guarantee the loop has stopped writing before `stop()` returns, which matters for clean shutdown/restart in tests.

Ticker validation in simulator mode: any well-formed ticker string is accepted — `add_ticker` assigns a random seed and joins the simulation immediately, no external round-trip.

### 6.6 Self-check

A minimal sanity test, not a full statistical suite — the only invariant that matters mechanically is that prices stay positive regardless of correlation/shock logic:

```python
def test_gbm_prices_stay_positive():
    sim = GBMSimulator(["AAPL", "TSLA"])
    for _ in range(1000):
        prices = sim.tick()
        assert all(p > 0 for p in prices.values())

def test_add_remove_ticker_updates_state():
    sim = GBMSimulator(["AAPL"])
    sim.add_ticker("PYPL")
    assert "PYPL" in sim.prices
    sim.remove_ticker("AAPL")
    assert "AAPL" not in sim.prices
```

## 7. Massive API client — `massive_client.py`

The optional real-data source, active whenever `MASSIVE_API_KEY` is set. Background reference: [MASSIVE_API.md](MASSIVE_API.md).

### 7.1 Endpoint choice

`client.get_snapshot_all(market_type="stocks", tickers=[...])` — one call returns latest trade/quote/day-aggregate for the whole watchlist, which is why we poll on an interval instead of hitting a per-ticker endpoint in a loop. Response per ticker gives us everything needed:

- `last_trade.price` — current price (may be null outside market hours or on some plans)
- `day.close` — fallback current price if `last_trade` is unavailable
- `prev_day.close` — previous session close, used as `previous_price`

```python
price = s.last_trade.price if s.last_trade else s.day.close
prev_close = s.prev_day.close
```

### 7.2 Rate limits drive the poll interval

| Plan | Recency | Calls/min | Default poll interval |
|---|---|---|---|
| Free (Basic) | End-of-day only | 5/min | 15s |
| Starter/Developer | 15-min delayed | plan-dependent | 15s (configurable) |
| Advanced/Business | Real-time | high | 2–5s (configurable) |

One call covers the entire watchlist regardless of size (up to the API's per-call ticker cap), so watchlist growth doesn't change the rate-limit math — only ticker *count against the cap* would, which is far beyond a personal watchlist's scale.

### 7.3 `MassiveDataSource`

```python
import asyncio
import logging
from datetime import datetime, timezone
from massive import RESTClient
from .cache import PriceCache
from .interface import MarketDataSource
from .models import PriceUpdate, direction_of

logger = logging.getLogger(__name__)

class MassiveDataSource(MarketDataSource):
    def __init__(
        self, api_key: str, price_cache: PriceCache, poll_interval: float = 15.0
    ) -> None:
        self._client = RESTClient(api_key=api_key)
        self._cache = price_cache
        self._interval = poll_interval
        self._tickers: list[str] = []
        self._task: asyncio.Task | None = None

    async def start(self, tickers: list[str]) -> None:
        self._tickers = list(tickers)
        await self._poll_once()
        self._task = asyncio.create_task(self._poll_loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def add_ticker(self, ticker: str) -> None:
        # Validate before joining the poll set, so a bad ticker from
        # POST /api/watchlist surfaces as a 400 instead of silently
        # polling forever for data that will never arrive.
        snapshot = await asyncio.to_thread(
            self._client.get_snapshot_all, market_type="stocks", tickers=[ticker]
        )
        if not snapshot or getattr(snapshot[0], "error", None):
            raise ValueError(f"unknown or unsupported ticker: {ticker}")
        self._tickers.append(ticker)
        self._apply_snapshot(snapshot)

    async def remove_ticker(self, ticker: str) -> None:
        if ticker in self._tickers:
            self._tickers.remove(ticker)
        self._cache.remove(ticker)

    async def _poll_loop(self) -> None:
        while True:
            await asyncio.sleep(self._interval)
            try:
                await self._poll_once()
            except Exception:
                logger.exception("massive poll failed, retrying next interval")

    async def _poll_once(self) -> None:
        if not self._tickers:
            return
        snapshot = await asyncio.to_thread(
            self._client.get_snapshot_all, market_type="stocks", tickers=self._tickers
        )
        self._apply_snapshot(snapshot)

    def _apply_snapshot(self, snapshot) -> None:
        now = datetime.now(timezone.utc).isoformat()
        for s in snapshot:
            if getattr(s, "error", None):
                logger.warning("snapshot error for %s: %s", s.ticker, s.error)
                continue
            price = s.last_trade.price if s.last_trade else s.day.close
            prev = s.prev_day.close
            self._cache.set(PriceUpdate(
                ticker=s.ticker,
                price=price,
                previous_price=prev,
                timestamp=now,
                direction=direction_of(price, prev),
            ))
```

Key points:

- `RESTClient` is synchronous, so every call runs via `asyncio.to_thread` to avoid blocking the event loop for the duration of the HTTP round-trip.
- `_poll_loop` wraps each cycle in `try/except Exception` — one bad tick (network blip, transient 5xx, auth hiccup) logs and retries next interval rather than killing the background task. This is the single most important resilience property of this class: the simulator has no external dependency to fail, but Massive does, and the poll loop must survive it indefinitely.
- `add_ticker` does a single-ticker snapshot call synchronously before joining the poll set, so `POST /api/watchlist` can return `400` for a bad ticker immediately instead of that ticker silently never updating.
- Unknown ticker in a batch snapshot comes back as an error/empty entry in `results[]` per-ticker rather than failing the whole call — `_apply_snapshot` logs and skips those instead of crashing the poll.
- Outside market hours, `last_trade` may be null — falls back to `day.close`, and `prev_day.close` is always the anchor for `previous_price`/direction regardless of session state.

## 8. Factory & startup wiring — `factory.py`

```python
import os
from .cache import PriceCache
from .interface import MarketDataSource
from .simulator import SimulatorDataSource
from .massive_client import MassiveDataSource

def create_market_data_source(cache: PriceCache) -> MarketDataSource:
    api_key = os.environ.get("MASSIVE_API_KEY", "").strip()
    if api_key:
        return MassiveDataSource(api_key=api_key, price_cache=cache)
    return SimulatorDataSource(price_cache=cache)
```

This is the **only** place in the backend that branches on `MASSIVE_API_KEY`. Every other consumer of market data goes through `PriceCache`/`MarketDataSource` and is oblivious to which implementation is live.

### 8.1 FastAPI lifespan integration

One `PriceCache` + one `MarketDataSource` per process, created in the app's lifespan context and attached to `app.state` so route handlers can reach it without a global:

```python
# backend/main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
from .market.cache import PriceCache
from .market.factory import create_market_data_source
from .db import get_default_watchlist_tickers  # from db/ init+seed

@asynccontextmanager
async def lifespan(app: FastAPI):
    cache = PriceCache()
    source = create_market_data_source(cache)
    tickers = await get_default_watchlist_tickers()
    await source.start(tickers)

    app.state.price_cache = cache
    app.state.market_data_source = source
    try:
        yield
    finally:
        await source.stop()

app = FastAPI(lifespan=lifespan)
```

`get_default_watchlist_tickers()` reads the current watchlist from SQLite (already seeded with the 10 default tickers per PLAN.md §7 by the time lifespan runs, since DB init happens lazily on first access — call it explicitly here during startup rather than waiting for the first HTTP request, so the market data loop and the DB agree on the initial ticker set).

## 9. Consuming the cache — SSE stream and other routes

### 9.1 `GET /api/stream/prices`

```python
import asyncio
import json
from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

router = APIRouter()

@router.get("/api/stream/prices")
async def stream_prices(request: Request):
    cache = request.app.state.price_cache

    async def event_generator():
        while True:
            if await request.is_disconnected():
                break
            updates = cache.get_all()
            yield {
                "event": "prices",
                "data": json.dumps({
                    ticker: {
                        "price": u.price,
                        "previous_price": u.previous_price,
                        "timestamp": u.timestamp,
                        "direction": u.direction,
                    }
                    for ticker, u in updates.items()
                }),
            }
            await asyncio.sleep(0.5)

    return EventSourceResponse(event_generator())
```

Per PLAN.md §6, the server pushes updates for **all** known tickers at a fixed ~500ms cadence — a broadcast, not a per-ticker diff — so the endpoint just re-reads `cache.get_all()` every tick rather than tracking `cache.version` per connection. `EventSourceResponse` (from `sse-starlette`) handles the `text/event-stream` framing; the frontend consumes it with the native `EventSource` API, which has built-in reconnection.

### 9.2 Watchlist mutation routes call through the source, not just the DB

Adding/removing a ticker has to update three things together: the DB row, the running market data loop, and (implicitly) the cache. Route handlers own that sequencing — the market module only exposes the primitives:

```python
@router.post("/api/watchlist")
async def add_to_watchlist(body: AddTickerRequest, request: Request):
    source: MarketDataSource = request.app.state.market_data_source
    try:
        await source.add_ticker(body.ticker)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await db.insert_watchlist_ticker(body.ticker)
    return {"ticker": body.ticker}

@router.delete("/api/watchlist/{ticker}")
async def remove_from_watchlist(ticker: str, request: Request):
    source: MarketDataSource = request.app.state.market_data_source
    await source.remove_ticker(ticker)
    await db.delete_watchlist_ticker(ticker)
    return {"ticker": ticker}
```

In simulator mode `add_ticker` never raises (any well-formed ticker is accepted); in Massive mode it raises `ValueError` for a ticker the API doesn't recognize, which the route translates to `400` — this is the validation path called out in MARKET_INTERFACE.md §Ticker validation.

### 9.3 Trade execution and portfolio valuation

Both read the same cache, synchronously, no `await`:

```python
def current_price(cache: PriceCache, ticker: str) -> float:
    update = cache.get(ticker)
    if update is None:
        raise HTTPException(status_code=400, detail=f"no price available for {ticker}")
    return update.price
```

Trade execution (`POST /api/portfolio/trade`) and portfolio valuation (`GET /api/portfolio`, the 30s snapshot task) both call this helper — market orders fill instantly at whatever `cache.get(ticker).price` currently holds, per PLAN.md's "market orders only" simplification.

## 10. Configuration

Env vars consumed by this module (see PLAN.md §5 for the full list):

| Var | Effect on `backend/market/` |
|---|---|
| `MASSIVE_API_KEY` | Unset/empty → `SimulatorDataSource`. Set → `MassiveDataSource`, polling at `poll_interval` (default 15s, override via a `MASSIVE_POLL_INTERVAL` env var if we want it configurable without a code change). |
| `LLM_MOCK` | No effect here — LLM-only flag, listed for completeness since it's in the same `.env`. |

No market-data-specific env var is required beyond `MASSIVE_API_KEY` — the simulator needs no configuration to run.

## 11. Testing strategy

Maps to PLAN.md §12's "Market data" bullet under backend unit tests.

**Simulator (`test_simulator.py`)**
- `GBMSimulator.tick()` keeps all prices positive over many iterations (§6.6).
- `add_ticker`/`remove_ticker` update both `prices` and trigger a Cholesky rebuild (assert no exception, and that the new ticker set is reflected).
- `SimulatorDataSource.start()`/`stop()` round-trip cleanly — start, let it tick a few times, stop, assert the background task is done and no further cache writes occur after stop.

**Massive client (`test_massive_client.py`)**
- Mock `RESTClient.get_snapshot_all` to return a canned snapshot list; assert `_apply_snapshot` writes the expected `PriceUpdate`s into the cache, including the `last_trade` → `day.close` fallback path and the `prev_day.close` → `previous_price` mapping.
- Mock a snapshot entry with `error` set; assert it's skipped without raising and other tickers in the same batch still get written.
- Mock `get_snapshot_all` raising (network error) inside `_poll_loop`; assert the loop logs and continues rather than propagating (task still alive after the failing tick).
- `add_ticker` with a mocked error-only snapshot response raises `ValueError` and does not mutate `self._tickers`.

**Interface conformance (`test_interface_conformance.py`)**
- Both implementations satisfy `MarketDataSource`'s abstract contract (trivially enforced by the ABC itself, but a parametrized test running the same start/add/remove/stop sequence against both — with Massive's HTTP calls mocked — guards against behavioral drift between the two).

**Cache (`test_cache.py`)**
- `set`/`get`/`get_all`/`remove` behave as a plain dict would, plus `version` increments on every mutating call.
- Thread-safety isn't practically testable in a unit test, but a quick concurrent-writer smoke test (multiple threads calling `set` in a loop, assert final state has no corruption) is cheap insurance.

These are unit tests within `backend/`, not part of the Playwright E2E suite in `test/` — the E2E suite exercises the whole stack with `LLM_MOCK=true` and the real simulator running (the simulator has no external dependency, so it runs as-is in E2E rather than being mocked).

## 12. Summary of source-of-truth documents

This document is the implementation-ready synthesis; for background and rationale on individual pieces, the originals remain the reference:

- [MARKET_INTERFACE.md](MARKET_INTERFACE.md) — interface/cache/factory design and the single-branch-point rule.
- [MARKET_SIMULATOR.md](MARKET_SIMULATOR.md) — GBM math, correlation, shock events.
- [MASSIVE_API.md](MASSIVE_API.md) — Massive endpoint research, rate limits, error shapes.
- [REVIEW.md](REVIEW.md) — prior review pass on those three docs (private-attribute fix, missing logger fix, self-check wording fix) — all three fixes are already incorporated into the code in this document.
