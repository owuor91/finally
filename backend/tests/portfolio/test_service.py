"""Trade execution + valuation logic tests."""

import pytest

from app.db import get_position, get_profile, list_snapshots, list_trades
from app.market import PriceCache
from app.portfolio import build_portfolio, execute_trade


@pytest.fixture
def cache():
    c = PriceCache()
    c.update("AAPL", 100.0)
    c.update("MSFT", 200.0)
    return c


def test_buy_deducts_cash_and_creates_position(temp_db, cache):
    execute_trade("AAPL", "buy", 10, cache)

    assert get_profile()["cash_balance"] == pytest.approx(10000 - 1000)
    pos = get_position("AAPL")
    assert pos["quantity"] == 10
    assert pos["avg_cost"] == pytest.approx(100.0)
    assert len(list_trades()) == 1
    assert len(list_snapshots()) == 1  # snapshot recorded on trade


def test_buy_weighted_average_cost(temp_db, cache):
    execute_trade("AAPL", "buy", 10, cache)  # 10 @ 100
    cache.update("AAPL", 200.0)
    execute_trade("AAPL", "buy", 10, cache)  # 10 @ 200

    pos = get_position("AAPL")
    assert pos["quantity"] == 20
    assert pos["avg_cost"] == pytest.approx(150.0)


def test_sell_reduces_position_and_adds_cash(temp_db, cache):
    execute_trade("AAPL", "buy", 10, cache)
    cache.update("AAPL", 120.0)
    execute_trade("AAPL", "sell", 4, cache)

    pos = get_position("AAPL")
    assert pos["quantity"] == 6
    assert pos["avg_cost"] == pytest.approx(100.0)  # unchanged on sell
    # -1000 buy + 480 sell
    assert get_profile()["cash_balance"] == pytest.approx(10000 - 1000 + 480)


def test_sell_entire_position_deletes_row(temp_db, cache):
    execute_trade("AAPL", "buy", 10, cache)
    execute_trade("AAPL", "sell", 10, cache)
    assert get_position("AAPL") is None


def test_sell_at_a_loss(temp_db, cache):
    execute_trade("AAPL", "buy", 10, cache)  # cost 1000
    cache.update("AAPL", 50.0)
    execute_trade("AAPL", "sell", 10, cache)  # proceeds 500
    assert get_profile()["cash_balance"] == pytest.approx(10000 - 1000 + 500)


def test_buy_insufficient_cash_raises(temp_db, cache):
    with pytest.raises(ValueError, match="Insufficient cash"):
        execute_trade("AAPL", "buy", 1000, cache)  # 100k > 10k
    assert get_position("AAPL") is None
    assert get_profile()["cash_balance"] == 10000


def test_sell_more_than_owned_raises(temp_db, cache):
    execute_trade("AAPL", "buy", 5, cache)
    with pytest.raises(ValueError, match="Insufficient shares"):
        execute_trade("AAPL", "sell", 10, cache)
    assert get_position("AAPL")["quantity"] == 5


def test_sell_with_no_position_raises(temp_db, cache):
    with pytest.raises(ValueError, match="Insufficient shares"):
        execute_trade("AAPL", "sell", 1, cache)


def test_invalid_side_raises(temp_db, cache):
    with pytest.raises(ValueError, match="Invalid side"):
        execute_trade("AAPL", "hold", 1, cache)


def test_non_positive_quantity_raises(temp_db, cache):
    with pytest.raises(ValueError, match="greater than zero"):
        execute_trade("AAPL", "buy", 0, cache)


def test_no_price_raises(temp_db, cache):
    with pytest.raises(ValueError, match="No live price"):
        execute_trade("TSLA", "buy", 1, cache)


def test_build_portfolio_pnl(temp_db, cache):
    execute_trade("AAPL", "buy", 10, cache)  # avg 100
    cache.update("AAPL", 150.0)

    p = build_portfolio(cache)
    assert p["cash_balance"] == pytest.approx(9000.0)
    (pos,) = p["positions"]
    assert pos["ticker"] == "AAPL"
    assert pos["current_price"] == 150.0
    assert pos["market_value"] == 1500.0
    assert pos["unrealized_pnl"] == 500.0
    assert pos["unrealized_pnl_percent"] == 50.0
    assert p["total_value"] == pytest.approx(9000 + 1500)
    assert p["total_unrealized_pnl"] == pytest.approx(500.0)


def test_build_portfolio_falls_back_to_avg_cost_without_price(temp_db, cache):
    execute_trade("AAPL", "buy", 10, cache)
    stale = PriceCache()  # no AAPL price
    p = build_portfolio(stale)
    (pos,) = p["positions"]
    assert pos["current_price"] == 100.0
    assert pos["unrealized_pnl"] == 0.0
