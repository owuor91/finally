"""Tests for the SQLite persistence layer."""

import sqlite3

import pytest

from app.db import (
    add_watchlist_ticker,
    delete_position,
    get_or_create_profile,
    get_position,
    get_profile,
    init_db,
    insert_chat_message,
    insert_snapshot,
    insert_trade,
    list_chat_messages,
    list_positions,
    list_snapshots,
    list_trades,
    list_watchlist,
    remove_watchlist_ticker,
    update_cash_balance,
    upsert_position,
)
from app.db.connection import DEFAULT_WATCHLIST, connection


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """Point the db layer at a fresh temp file per test (never the real db)."""
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("FINALLY_DB_PATH", str(db_file))
    # ensure_db caches per path; a fresh tmp path is always uninitialized,
    # but clear the cache to be safe against cross-test bleed.
    from app.db import connection as conn_mod

    conn_mod._initialized_paths.clear()
    yield db_file


# --- Init & seed -----------------------------------------------------------

def test_init_creates_all_tables(temp_db):
    init_db()
    with connection(ensure=False) as conn:
        names = {
            r["name"]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
    assert {
        "users_profile",
        "watchlist",
        "positions",
        "trades",
        "portfolio_snapshots",
        "chat_messages",
    } <= names


def test_seed_profile(temp_db):
    init_db()
    profile = get_profile()
    assert profile is not None
    assert profile["id"] == "default"
    assert profile["cash_balance"] == 10000.0


def test_seed_watchlist(temp_db):
    init_db()
    assert list_watchlist() == DEFAULT_WATCHLIST


def test_lazy_init_on_first_query(temp_db):
    # No explicit init_db(); first query should trigger it.
    assert get_profile() is not None
    assert len(list_watchlist()) == 10


def test_reinit_is_idempotent(temp_db):
    init_db()
    update_cash_balance(500.0)
    remove_watchlist_ticker("AAPL")
    add_watchlist_ticker("PYPL")
    init_db()  # must not wipe or duplicate user edits
    assert get_profile()["cash_balance"] == 500.0
    wl = list_watchlist()
    assert "AAPL" not in wl
    assert wl.count("PYPL") == 1
    assert get_profile()["cash_balance"] == 500.0


# --- Profile ---------------------------------------------------------------

def test_update_cash_balance(temp_db):
    init_db()
    update_cash_balance(12345.67)
    assert get_profile()["cash_balance"] == 12345.67


def test_get_or_create_profile_for_new_user(temp_db):
    init_db()
    profile = get_or_create_profile(user_id="alice")
    assert profile["id"] == "alice"
    assert profile["cash_balance"] == 10000.0
    # Idempotent: does not reset an existing balance.
    update_cash_balance(42.0, user_id="alice")
    assert get_or_create_profile(user_id="alice")["cash_balance"] == 42.0


# --- Watchlist -------------------------------------------------------------

def test_add_and_remove_watchlist(temp_db):
    init_db()
    add_watchlist_ticker("PYPL")
    assert "PYPL" in list_watchlist()
    remove_watchlist_ticker("PYPL")
    assert "PYPL" not in list_watchlist()


def test_watchlist_unique_constraint(temp_db):
    init_db()
    add_watchlist_ticker("PYPL")
    add_watchlist_ticker("PYPL")  # INSERT OR IGNORE -> no duplicate
    assert list_watchlist().count("PYPL") == 1


def test_watchlist_raw_unique_violation(temp_db):
    init_db()
    with pytest.raises(sqlite3.IntegrityError):
        with connection() as conn:
            conn.execute(
                "INSERT INTO watchlist (id, user_id, ticker, added_at) VALUES (?, ?, ?, ?)",
                ("x", "default", "AAPL", "now"),
            )


# --- Positions -------------------------------------------------------------

def test_position_upsert_roundtrip(temp_db):
    init_db()
    upsert_position("AAPL", 10, 190.0)
    pos = get_position("AAPL")
    assert pos["quantity"] == 10
    assert pos["avg_cost"] == 190.0
    # Update in place, not duplicate.
    upsert_position("AAPL", 15, 192.5)
    assert get_position("AAPL")["quantity"] == 15
    assert len([p for p in list_positions() if p["ticker"] == "AAPL"]) == 1


def test_position_delete(temp_db):
    init_db()
    upsert_position("TSLA", 5, 250.0)
    delete_position("TSLA")
    assert get_position("TSLA") is None


def test_get_position_missing(temp_db):
    init_db()
    assert get_position("NOPE") is None


def test_position_unique_constraint(temp_db):
    init_db()
    upsert_position("AAPL", 1, 100.0)
    with pytest.raises(sqlite3.IntegrityError):
        with connection() as conn:
            conn.execute(
                "INSERT INTO positions (id, user_id, ticker, quantity, avg_cost, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ("x", "default", "AAPL", 2, 100.0, "now"),
            )


# --- Trades ----------------------------------------------------------------

def test_insert_and_list_trades(temp_db):
    init_db()
    insert_trade("AAPL", "buy", 10, 190.0)
    insert_trade("AAPL", "sell", 5, 195.0)
    trades = list_trades()
    assert len(trades) == 2
    assert trades[0]["side"] == "sell"  # newest first
    assert trades[0]["price"] == 195.0


def test_list_trades_limit(temp_db):
    init_db()
    for i in range(5):
        insert_trade("AAPL", "buy", 1, 100.0 + i)
    assert len(list_trades(limit=2)) == 2


# --- Snapshots -------------------------------------------------------------

def test_insert_and_list_snapshots(temp_db):
    init_db()
    insert_snapshot(10000.0)
    insert_snapshot(10500.0)
    snaps = list_snapshots()
    assert len(snaps) == 2
    assert snaps[0]["total_value"] == 10000.0  # oldest first


# --- Chat messages ---------------------------------------------------------

def test_chat_message_roundtrip_with_actions(temp_db):
    init_db()
    actions = {"trades": [{"ticker": "AAPL", "side": "buy", "quantity": 10}]}
    msg = insert_chat_message("assistant", "Bought AAPL", actions=actions)
    assert msg["actions"] == actions
    fetched = list_chat_messages()[-1]
    assert fetched["actions"] == actions
    assert fetched["role"] == "assistant"


def test_chat_message_null_actions(temp_db):
    init_db()
    msg = insert_chat_message("user", "hello")
    assert msg["actions"] is None
    assert list_chat_messages()[0]["actions"] is None


def test_list_chat_messages_limit_returns_most_recent_in_order(temp_db):
    init_db()
    for i in range(5):
        insert_chat_message("user", f"msg {i}")
    recent = list_chat_messages(limit=2)
    assert [m["content"] for m in recent] == ["msg 3", "msg 4"]


# --- Isolation -------------------------------------------------------------

def test_users_are_isolated(temp_db):
    init_db()
    add_watchlist_ticker("PYPL", user_id="alice")
    assert "PYPL" in list_watchlist(user_id="alice")
    assert "PYPL" not in list_watchlist(user_id="default")
