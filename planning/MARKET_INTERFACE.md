# Market Data Interface — Design

One Python interface, two implementations (simulator, Massive), selected by `MASSIVE_API_KEY` at startup. Everything downstream (SSE stream, portfolio valuation, trades) reads from a shared cache and never knows which source is running. Background for the Massive side: [MASSIVE_API.md](MASSIVE_API.md). Simulator internals: [MARKET_SIMULATOR.md](MARKET_SIMULATOR.md).

## Layout

```
backend/market/
├── __init__.py
├── models.py       # PriceUpdate
├── interface.py    # MarketDataSource (ABC)
├── cache.py        # PriceCache
├── simulator.py     # SimulatorDataSource (GBM)
├── massive_client.py # MassiveDataSource (REST poller)
└── factory.py       # create_market_data_source()
```

## `models.py`

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class PriceUpdate:
    ticker: str
    price: float
    previous_price: float
    timestamp: str   # ISO 8601
    direction: str    # "up" | "down" | "flat"
```

## `interface.py`

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

Both implementations write into the same `PriceCache` instance rather than returning data — `start()` kicks off a background loop (asyncio task) that keeps writing until `stop()`.

## `cache.py`

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

    @property
    def version(self) -> int:
        return self._version
```

The SSE endpoint (`/api/stream/prices`) polls `cache.version` and re-emits `get_all()` when it changes — it's the single point every consumer (streaming, trade execution, portfolio valuation) reads from.

## `factory.py`

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

This is the only place that branches on `MASSIVE_API_KEY`. Nothing else in the backend checks the env var.

## `massive_client.py` (sketch — see MASSIVE_API.md for endpoint details)

```python
import asyncio
import logging
from datetime import datetime, timezone
from massive import RESTClient
from .cache import PriceCache
from .interface import MarketDataSource
from .models import PriceUpdate

logger = logging.getLogger(__name__)

class MassiveDataSource(MarketDataSource):
    def __init__(self, api_key: str, price_cache: PriceCache, poll_interval: float = 15.0) -> None:
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

    async def add_ticker(self, ticker: str) -> None:
        self._tickers.append(ticker)

    async def remove_ticker(self, ticker: str) -> None:
        self._tickers.remove(ticker)

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
        snapshots = await asyncio.to_thread(
            self._client.get_snapshot_all, market_type="stocks", tickers=self._tickers
        )
        now = datetime.now(timezone.utc).isoformat()
        for s in snapshots:
            price = s.last_trade.price if s.last_trade else s.day.close
            prev = s.prev_day.close
            self._cache.set(PriceUpdate(
                ticker=s.ticker, price=price, previous_price=prev,
                timestamp=now, direction="up" if price > prev else "down" if price < prev else "flat",
            ))
```

`RESTClient` is synchronous, so the poll runs via `asyncio.to_thread` to avoid blocking the event loop.

## `simulator.py`

`SimulatorDataSource` implements the same four methods but runs a ~500ms `asyncio` loop doing GBM math instead of an HTTP call. Full design in [MARKET_SIMULATOR.md](MARKET_SIMULATOR.md).

## Ticker validation

- **Simulator mode**: any well-formed ticker is accepted — `add_ticker` assigns a random seed price ($50-$300) and it joins the simulation.
- **Massive mode**: an unknown ticker's snapshot entry comes back as an error (see MASSIVE_API.md § Errors). `add_ticker` should do one snapshot call for the new ticker alone and raise if it errors, so `POST /api/watchlist` / trade validation can return `400` before the ticker is added.

## Startup wiring

```python
cache = PriceCache()
source = create_market_data_source(cache)
await source.start(default_watchlist_tickers)
```

One `PriceCache` + one `MarketDataSource` per process (single-user app, no per-request instantiation).
