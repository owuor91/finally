"""SQLite persistence layer for FinAlly.

Lazy-initialized, single-file SQLite. Import the data-access functions
directly:

    from app.db import (
        init_db, get_profile, update_cash_balance,
        list_watchlist, add_watchlist_ticker, remove_watchlist_ticker,
        get_position, list_positions, upsert_position, delete_position,
        insert_trade, list_trades,
        insert_snapshot, list_snapshots,
        insert_chat_message, list_chat_messages,
    )
"""

from .connection import (
    DEFAULT_CASH_BALANCE,
    DEFAULT_USER_ID,
    DEFAULT_WATCHLIST,
    db_path,
    ensure_db,
    init_db,
)
from .queries import (
    add_watchlist_ticker,
    delete_position,
    get_or_create_profile,
    get_position,
    get_profile,
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

__all__ = [
    "DEFAULT_CASH_BALANCE",
    "DEFAULT_USER_ID",
    "DEFAULT_WATCHLIST",
    "db_path",
    "ensure_db",
    "init_db",
    "get_profile",
    "get_or_create_profile",
    "update_cash_balance",
    "list_watchlist",
    "add_watchlist_ticker",
    "remove_watchlist_ticker",
    "get_position",
    "list_positions",
    "upsert_position",
    "delete_position",
    "insert_trade",
    "list_trades",
    "insert_snapshot",
    "list_snapshots",
    "insert_chat_message",
    "list_chat_messages",
]
