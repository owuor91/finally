"""Route tests via FastAPI TestClient.

The app is used WITHOUT the lifespan context manager, so the real market
simulator never starts; we inject a seeded PriceCache and a fake data source
onto app.state instead.
"""

import pytest
from fastapi.testclient import TestClient

from app.market import PriceCache


class FakeSource:
    """Async add/remove that mirrors the real source's cache side effects."""

    def __init__(self, cache: PriceCache):
        self.cache = cache
        self.added: list[str] = []
        self.removed: list[str] = []

    async def add_ticker(self, ticker: str) -> None:
        self.added.append(ticker)
        self.cache.update(ticker, 50.0)

    async def remove_ticker(self, ticker: str) -> None:
        self.removed.append(ticker)
        self.cache.remove(ticker)


@pytest.fixture
def client(temp_db):
    from app.db import init_db
    from app.main import app

    init_db()  # temp_db is fresh; seed the default profile + watchlist
    cache = PriceCache()
    for ticker in ("AAPL", "GOOGL", "MSFT"):
        cache.update(ticker, 100.0)
    app.state.price_cache = cache
    app.state.data_source = FakeSource(cache)
    return TestClient(app)


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_get_portfolio_fresh(client):
    r = client.get("/api/portfolio")
    assert r.status_code == 200
    body = r.json()
    assert body["cash_balance"] == 10000.0
    assert body["positions"] == []
    assert body["total_value"] == 10000.0


def test_trade_roundtrip(client):
    r = client.post("/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 5, "side": "buy"})
    assert r.status_code == 200
    body = r.json()
    assert body["cash_balance"] == pytest.approx(10000 - 500)
    (pos,) = body["positions"]
    assert pos["ticker"] == "AAPL"
    assert pos["quantity"] == 5


def test_trade_insufficient_cash_returns_400(client):
    r = client.post(
        "/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 10000, "side": "buy"}
    )
    assert r.status_code == 400
    assert "Insufficient cash" in r.json()["detail"]


def test_history_grows_after_trade(client):
    assert client.get("/api/portfolio/history").json() == []
    client.post("/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 1, "side": "buy"})
    history = client.get("/api/portfolio/history").json()
    assert len(history) == 1
    assert set(history[0]) == {"total_value", "recorded_at"}


def test_get_watchlist_has_seeded_tickers_with_prices(client):
    body = client.get("/api/watchlist").json()
    tickers = {row["ticker"] for row in body}
    assert {"AAPL", "GOOGL", "MSFT"} <= tickers
    aapl = next(r for r in body if r["ticker"] == "AAPL")
    assert aapl["price"] == 100.0


def test_add_watchlist_ticker(client):
    r = client.post("/api/watchlist", json={"ticker": "tsla"})
    assert r.status_code == 200
    tickers = {row["ticker"] for row in r.json()}
    assert "TSLA" in tickers
    assert app_state_source(client).added == ["TSLA"]


def test_remove_watchlist_ticker(client):
    r = client.delete("/api/watchlist/AAPL")
    assert r.status_code == 200
    tickers = {row["ticker"] for row in r.json()}
    assert "AAPL" not in tickers
    assert app_state_source(client).removed == ["AAPL"]


def app_state_source(client: TestClient) -> FakeSource:
    return client.app.state.data_source
