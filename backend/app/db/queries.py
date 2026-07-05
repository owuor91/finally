"""Data-access functions over the SQLite database.

Plain functions, parameterized queries, one short-lived connection per call.
Every function takes user_id (default "default") per the multi-user-ready schema.
Rows are returned as plain dicts.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from .connection import DEFAULT_CASH_BALANCE, DEFAULT_USER_ID, connection, new_id, now_iso


def _row(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


# --- Profile ---------------------------------------------------------------

def get_profile(user_id: str = DEFAULT_USER_ID) -> dict[str, Any] | None:
    """The user's profile row (id, cash_balance, created_at), or None."""
    with connection() as conn:
        return _row(
            conn.execute(
                "SELECT * FROM users_profile WHERE id = ?", (user_id,)
            ).fetchone()
        )


def get_or_create_profile(user_id: str = DEFAULT_USER_ID) -> dict[str, Any]:
    """The user's profile, creating it with the default cash balance if absent."""
    with connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO users_profile (id, cash_balance, created_at) VALUES (?, ?, ?)",
            (user_id, DEFAULT_CASH_BALANCE, now_iso()),
        )
        return dict(
            conn.execute(
                "SELECT * FROM users_profile WHERE id = ?", (user_id,)
            ).fetchone()
        )


def update_cash_balance(balance: float, user_id: str = DEFAULT_USER_ID) -> None:
    """Set the user's cash balance."""
    with connection() as conn:
        conn.execute(
            "UPDATE users_profile SET cash_balance = ? WHERE id = ?", (balance, user_id)
        )


# --- Watchlist -------------------------------------------------------------

def list_watchlist(user_id: str = DEFAULT_USER_ID) -> list[str]:
    """Watched tickers, oldest first."""
    with connection() as conn:
        rows = conn.execute(
            "SELECT ticker FROM watchlist WHERE user_id = ? ORDER BY added_at",
            (user_id,),
        ).fetchall()
        return [r["ticker"] for r in rows]


def add_watchlist_ticker(ticker: str, user_id: str = DEFAULT_USER_ID) -> None:
    """Add a ticker to the watchlist (no-op if already present)."""
    with connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO watchlist (id, user_id, ticker, added_at) VALUES (?, ?, ?, ?)",
            (new_id(), user_id, ticker, now_iso()),
        )


def remove_watchlist_ticker(ticker: str, user_id: str = DEFAULT_USER_ID) -> None:
    """Remove a ticker from the watchlist (no-op if absent)."""
    with connection() as conn:
        conn.execute(
            "DELETE FROM watchlist WHERE user_id = ? AND ticker = ?", (user_id, ticker)
        )


# --- Positions -------------------------------------------------------------

def get_position(ticker: str, user_id: str = DEFAULT_USER_ID) -> dict[str, Any] | None:
    """A single position row, or None if not held."""
    with connection() as conn:
        return _row(
            conn.execute(
                "SELECT * FROM positions WHERE user_id = ? AND ticker = ?",
                (user_id, ticker),
            ).fetchone()
        )


def list_positions(user_id: str = DEFAULT_USER_ID) -> list[dict[str, Any]]:
    """All positions for the user, ordered by ticker."""
    with connection() as conn:
        rows = conn.execute(
            "SELECT * FROM positions WHERE user_id = ? ORDER BY ticker", (user_id,)
        ).fetchall()
        return [dict(r) for r in rows]


def upsert_position(
    ticker: str, quantity: float, avg_cost: float, user_id: str = DEFAULT_USER_ID
) -> dict[str, Any]:
    """Insert or update the position for a ticker. Returns the stored row."""
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO positions (id, user_id, ticker, quantity, avg_cost, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, ticker) DO UPDATE SET
                quantity = excluded.quantity,
                avg_cost = excluded.avg_cost,
                updated_at = excluded.updated_at
            """,
            (new_id(), user_id, ticker, quantity, avg_cost, now_iso()),
        )
        return dict(
            conn.execute(
                "SELECT * FROM positions WHERE user_id = ? AND ticker = ?",
                (user_id, ticker),
            ).fetchone()
        )


def delete_position(ticker: str, user_id: str = DEFAULT_USER_ID) -> None:
    """Remove a position (e.g. after selling the full quantity)."""
    with connection() as conn:
        conn.execute(
            "DELETE FROM positions WHERE user_id = ? AND ticker = ?", (user_id, ticker)
        )


# --- Trades ----------------------------------------------------------------

def insert_trade(
    ticker: str,
    side: str,
    quantity: float,
    price: float,
    user_id: str = DEFAULT_USER_ID,
) -> dict[str, Any]:
    """Append a trade to the log. side is "buy" or "sell". Returns the row."""
    trade_id = new_id()
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO trades (id, user_id, ticker, side, quantity, price, executed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (trade_id, user_id, ticker, side, quantity, price, now_iso()),
        )
        return dict(
            conn.execute("SELECT * FROM trades WHERE id = ?", (trade_id,)).fetchone()
        )


def list_trades(
    user_id: str = DEFAULT_USER_ID, limit: int | None = None
) -> list[dict[str, Any]]:
    """Trades newest first, optionally capped at `limit`."""
    sql = "SELECT * FROM trades WHERE user_id = ? ORDER BY executed_at DESC"
    params: list[Any] = [user_id]
    if limit is not None:
        sql += " LIMIT ?"
        params.append(limit)
    with connection() as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


# --- Portfolio snapshots ---------------------------------------------------

def insert_snapshot(
    total_value: float, user_id: str = DEFAULT_USER_ID
) -> dict[str, Any]:
    """Record a portfolio total-value snapshot. Returns the row."""
    snap_id = new_id()
    with connection() as conn:
        conn.execute(
            "INSERT INTO portfolio_snapshots (id, user_id, total_value, recorded_at) VALUES (?, ?, ?, ?)",
            (snap_id, user_id, total_value, now_iso()),
        )
        return dict(
            conn.execute(
                "SELECT * FROM portfolio_snapshots WHERE id = ?", (snap_id,)
            ).fetchone()
        )


def list_snapshots(
    user_id: str = DEFAULT_USER_ID, limit: int | None = None
) -> list[dict[str, Any]]:
    """Snapshots oldest first (chart order), optionally capped at `limit`."""
    sql = "SELECT * FROM portfolio_snapshots WHERE user_id = ? ORDER BY recorded_at"
    params: list[Any] = [user_id]
    if limit is not None:
        sql += " LIMIT ?"
        params.append(limit)
    with connection() as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


# --- Chat messages ---------------------------------------------------------

def insert_chat_message(
    role: str,
    content: str,
    actions: Any | None = None,
    user_id: str = DEFAULT_USER_ID,
) -> dict[str, Any]:
    """Append a chat message. `actions` (any JSON-serializable value or None)
    is stored as JSON text. Returns the row with `actions` parsed back."""
    msg_id = new_id()
    actions_json = json.dumps(actions) if actions is not None else None
    with connection() as conn:
        conn.execute(
            "INSERT INTO chat_messages (id, user_id, role, content, actions, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (msg_id, user_id, role, content, actions_json, now_iso()),
        )
        row = conn.execute(
            "SELECT * FROM chat_messages WHERE id = ?", (msg_id,)
        ).fetchone()
        return _decode_message(row)


def list_chat_messages(
    user_id: str = DEFAULT_USER_ID, limit: int | None = None
) -> list[dict[str, Any]]:
    """Chat messages oldest first, optionally capped to the most recent `limit`."""
    with connection() as conn:
        if limit is not None:
            rows = conn.execute(
                "SELECT * FROM chat_messages WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
            rows = list(reversed(rows))
        else:
            rows = conn.execute(
                "SELECT * FROM chat_messages WHERE user_id = ? ORDER BY created_at",
                (user_id,),
            ).fetchall()
        return [_decode_message(r) for r in rows]


def _decode_message(row: sqlite3.Row) -> dict[str, Any]:
    msg = dict(row)
    msg["actions"] = json.loads(msg["actions"]) if msg["actions"] is not None else None
    return msg
