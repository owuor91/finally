# Market Simulator — Design

The default data source (no `MASSIVE_API_KEY` needed). Generates plausible-looking live prices for an arbitrary ticker set using geometric Brownian motion (GBM), with correlated moves and occasional shock events for visual drama. Implements the same `MarketDataSource` interface described in [MARKET_INTERFACE.md](MARKET_INTERFACE.md).

## Why GBM

GBM is the standard toy model for a stock price: `dS = S * (μ dt + σ dW)` — drift `μ` (average trend) plus volatility `σ` scaling a random shock `dW`. It's one line per tick, always stays positive, and produces a realistic-looking random walk without needing real market data.

Per tick, in log-return form (avoids negative prices, standard for this kind of sim):

```
price_new = price_old * exp((μ - σ²/2) * dt + σ * sqrt(dt) * Z)
```

where `Z` is a standard normal draw and `dt` is the tick interval in years (`0.5s / (252 * 6.5 * 3600)` if you want annualized params, or just pick per-tick `μ`/`σ` directly — see below).

## Seed data

```python
# seed_prices.py
SEED_PRICES = {
    "AAPL": 190.0, "GOOGL": 175.0, "MSFT": 420.0, "AMZN": 185.0,
    "TSLA": 250.0, "NVDA": 130.0, "META": 560.0, "JPM": 210.0,
    "V": 280.0, "NFLX": 700.0,
}

# Per-ticker GBM params, tuned per-tick (not annualized) so the sim looks
# lively at a 500ms cadence without needing unit conversion at runtime.
GBM_PARAMS = {
    "AAPL": {"drift": 0.00001, "vol": 0.0008, "group": "tech"},
    "TSLA": {"drift": 0.00002, "vol": 0.0020, "group": "tech"},  # more volatile
    "JPM":  {"drift": 0.00001, "vol": 0.0006, "group": "finance"},
    # ...
}

CORRELATION = {
    ("tech", "tech"): 0.6,
    ("finance", "finance"): 0.5,
    ("tech", "finance"): 0.3,
}
```

Unseen tickers added at runtime (`add_ticker`) get a random seed price in `$50-$300` and default (mid-range) drift/vol — see [MARKET_INTERFACE.md](MARKET_INTERFACE.md) § Ticker validation.

## Correlated moves

Independent random draws per ticker look wrong — real tech stocks move together. Build a correlation matrix from each ticker's `group`, take its Cholesky decomposition, and multiply a vector of independent normal draws by it each tick to get correlated ones:

```python
import numpy as np

class GBMSimulator:
    def __init__(self, tickers: list[str]) -> None:
        self._tickers = tickers
        self._prices = {t: SEED_PRICES.get(t, random.uniform(50, 300)) for t in tickers}
        self._chol = np.linalg.cholesky(self._build_corr_matrix(tickers))

    @property
    def prices(self) -> dict[str, float]:
        return dict(self._prices)

    def tick(self) -> dict[str, float]:
        z = np.random.standard_normal(len(self._tickers))
        correlated_z = self._chol @ z
        for i, ticker in enumerate(self._tickers):
            params = GBM_PARAMS.get(ticker, DEFAULT_PARAMS)
            drift, vol = params["drift"], params["vol"]
            self._prices[ticker] *= math.exp(drift - 0.5 * vol**2 + vol * correlated_z[i])
        self._maybe_shock()
        return dict(self._prices)
```

Recompute the Cholesky matrix once when the ticker set changes (`add_ticker`/`remove_ticker`), not every tick.

## Shock events

Per tick, per ticker, a small independent-of-GBM chance (~0.1%) of a sudden 2-5% jump — gives the demo occasional "notable move" moments without dominating normal price action:

```python
def _maybe_shock(self) -> None:
    for ticker in self._tickers:
        if random.random() < 0.001:
            direction = random.choice([1, -1])
            magnitude = random.uniform(0.02, 0.05)
            self._prices[ticker] *= (1 + direction * magnitude)
```

## `SimulatorDataSource`

Wraps `GBMSimulator` in the `MarketDataSource` interface — an `asyncio` loop ticking every 500ms, writing each ticker's new price into the shared `PriceCache`:

```python
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

    async def add_ticker(self, ticker: str) -> None:
        self._sim.add_ticker(ticker)  # rebuilds correlation matrix

    async def remove_ticker(self, ticker: str) -> None:
        self._sim.remove_ticker(ticker)

    async def _run(self) -> None:
        while True:
            await asyncio.sleep(self._interval)
            prev_prices = self._sim.prices
            new_prices = self._sim.tick()
            now = datetime.now(timezone.utc).isoformat()
            for ticker, price in new_prices.items():
                prev = prev_prices[ticker]
                self._cache.set(PriceUpdate(
                    ticker=ticker, price=price, previous_price=prev,
                    timestamp=now,
                    direction="up" if price > prev else "down" if price < prev else "flat",
                ))
```

No external dependencies beyond `numpy` (already needed for the Cholesky step) — everything else is stdlib `asyncio`, `math`, `random`.

## Self-check

A minimal sanity test, not a full suite — prices stay positive over many ticks regardless of correlation/shock logic:

```python
def test_gbm_prices_stay_positive():
    sim = GBMSimulator(["AAPL", "TSLA"])
    for _ in range(1000):
        prices = sim.tick()
        assert all(p > 0 for p in prices.values())
```
