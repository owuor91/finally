"""Chat layer tests.

Route tests run the app WITHOUT lifespan (same pattern as tests/routes), with a
seeded PriceCache + fake async source on app.state and LLM_MOCK=true. Parsing and
malformed-output handling are tested directly against fixture JSON strings, since
no OPENROUTER_API_KEY is available for real calls.
"""

import pytest
from fastapi.testclient import TestClient

from app.llm.service import LLMResponse, _call_llm, _mock_response
from app.market import PriceCache


class FakeSource:
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
def client(temp_db, monkeypatch):
    monkeypatch.setenv("LLM_MOCK", "true")
    from app.db import init_db
    from app.main import app

    init_db()
    cache = PriceCache()
    for ticker in ("AAPL", "GOOGL", "MSFT", "NVDA"):
        cache.update(ticker, 100.0)
    app.state.price_cache = cache
    app.state.data_source = FakeSource(cache)
    return TestClient(app)


# --- structured-output parsing (fixture JSON stands in for LLM output) ---


def test_parse_full_schema():
    r = LLMResponse.model_validate_json(
        '{"message":"ok","trades":[{"ticker":"AAPL","side":"buy","quantity":10}],'
        '"watchlist_changes":[{"ticker":"PYPL","action":"add"}]}'
    )
    assert r.message == "ok"
    assert r.trades[0].ticker == "AAPL"
    assert r.watchlist_changes[0].action == "add"


def test_parse_message_only_defaults_empty():
    r = LLMResponse.model_validate_json('{"message":"hi"}')
    assert r.trades == []
    assert r.watchlist_changes == []


def test_call_llm_returns_fallback_on_malformed(monkeypatch):
    class FakeMsg:
        content = "not json at all"

    class FakeChoice:
        message = FakeMsg()

    class FakeResp:
        choices = [FakeChoice()]

    monkeypatch.setattr("litellm.completion", lambda **kw: FakeResp())
    r = _call_llm([{"role": "user", "content": "hi"}])
    assert r.trades == []
    assert "problem" in r.message.lower()


def test_call_llm_returns_fallback_on_network_error(monkeypatch):
    def boom(**kw):
        raise RuntimeError("network down")

    monkeypatch.setattr("litellm.completion", boom)
    r = _call_llm([{"role": "user", "content": "hi"}])
    assert "problem" in r.message.lower()


# --- mock-mode determinism ---


def test_mock_detects_buy_and_sell():
    r = _mock_response("buy 5 NVDA and sell 2 aapl")
    sides = {(t.side, t.ticker, t.quantity) for t in r.trades}
    assert ("buy", "NVDA", 5.0) in sides
    assert ("sell", "AAPL", 2.0) in sides


def test_mock_detects_watchlist():
    r = _mock_response("watch pypl and unwatch tsla")
    changes = {(c.action, c.ticker) for c in r.watchlist_changes}
    assert ("add", "PYPL") in changes
    assert ("remove", "TSLA") in changes


def test_mock_canned_when_no_pattern():
    r1 = _mock_response("how is my portfolio doing?")
    r2 = _mock_response("how is my portfolio doing?")
    assert r1.trades == [] and r1.watchlist_changes == []
    assert r1.message == r2.message  # deterministic


# --- route: auto-execution + persistence ---


def test_chat_executes_trade(client):
    r = client.post("/api/chat", json={"message": "buy 5 NVDA"})
    assert r.status_code == 200
    body = r.json()
    assert body["trades"] == [
        {"ticker": "NVDA", "side": "buy", "quantity": 5.0, "error": None}
    ]
    # cash actually moved
    port = client.get("/api/portfolio").json()
    assert port["cash_balance"] == pytest.approx(10000 - 500)


def test_chat_multiple_trades(client):
    body = client.post("/api/chat", json={"message": "buy 1 AAPL and buy 2 MSFT"}).json()
    tickers = {t["ticker"] for t in body["trades"]}
    assert tickers == {"AAPL", "MSFT"}


def test_chat_trade_validation_error_surfaced(client):
    body = client.post("/api/chat", json={"message": "buy 100000 NVDA"}).json()
    (trade,) = body["trades"]
    assert trade["error"] is not None
    assert "Insufficient cash" in trade["error"]
    # failed buy did not move cash
    assert client.get("/api/portfolio").json()["cash_balance"] == 10000.0


def test_chat_watchlist_add(client):
    body = client.post("/api/chat", json={"message": "watch PYPL"}).json()
    assert body["watchlist_changes"] == [{"ticker": "PYPL", "action": "add"}]
    assert client.app.state.data_source.added == ["PYPL"]
    assert "PYPL" in {row["ticker"] for row in client.get("/api/watchlist").json()}


def test_chat_watchlist_remove(client):
    body = client.post("/api/chat", json={"message": "unwatch AAPL"}).json()
    assert body["watchlist_changes"] == [{"ticker": "AAPL", "action": "remove"}]
    assert client.app.state.data_source.removed == ["AAPL"]


def test_chat_persists_history(client):
    from app.db import list_chat_messages

    client.post("/api/chat", json={"message": "buy 5 NVDA"})
    msgs = list_chat_messages()
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert msgs[0]["content"] == "buy 5 NVDA"
    assert msgs[1]["actions"]["trades"][0]["ticker"] == "NVDA"


def test_chat_plain_message_no_actions(client):
    body = client.post("/api/chat", json={"message": "hello there"}).json()
    assert body["trades"] == []
    assert body["watchlist_changes"] == []
    assert isinstance(body["message"], str)
