# Database Layer — Summary

**Status:** Complete, tested (21 tests), ruff-clean.

## What Was Built

A single-file SQLite persistence layer in `backend/app/db/` (3 modules). Plain
functions over short-lived connections — no ORM, no migrations, no connection
pool. The schema matches PLAN.md §7 exactly. Lazy idempotent init seeds a fresh
database on first use.

### Modules

| File | Purpose |
|------|---------|
| `connection.py` | Path resolution, WAL connection context manager, schema DDL, lazy idempotent `init_db()` + seed |
| `queries.py` | Data-access functions (one short-lived connection per call, parameterized queries) |
| `__init__.py` | Re-exports the public API |

### Key Design Decisions

- **DB path** — `<project_root>/db/finally.db`, resolved via
  `Path(__file__).resolve().parents[3]` (robust to uvicorn launching from
  `backend/`). Override with the `FINALLY_DB_PATH` env var (used by tests).
- **WAL mode**, one connection opened+closed per call. No pool — correct and
  simplest for single-user sync sqlite3 under async FastAPI.
- **Lazy init** — `ensure_db()` runs `init_db()` once per resolved path; every
  query calls it transparently. You may also call `init_db()` explicitly at
  startup.
- **Idempotent seed** — seed runs only when the `default` profile is absent, so
  user edits (removed watchlist tickers, changed cash) survive restarts.
- **Parameterized queries everywhere** — no string-formatted SQL.
- **`user_id` on every function**, defaulting to `"default"` per the
  multi-user-ready schema.
- Rows returned as plain `dict`s. `chat_messages.actions` is stored as JSON text
  and returned already parsed (dict/list/None).

## Public API

Import from `app.db`:

```python
from app.db import (
    init_db, ensure_db, db_path,
    DEFAULT_USER_ID, DEFAULT_CASH_BALANCE, DEFAULT_WATCHLIST,
    # profile
    get_profile, get_or_create_profile, update_cash_balance,
    # watchlist
    list_watchlist, add_watchlist_ticker, remove_watchlist_ticker,
    # positions
    get_position, list_positions, upsert_position, delete_position,
    # trades
    insert_trade, list_trades,
    # snapshots
    insert_snapshot, list_snapshots,
    # chat
    insert_chat_message, list_chat_messages,
)
```

### Init

| Function | Description |
|----------|-------------|
| `init_db() -> None` | Create tables if missing; seed default profile + 10 watchlist tickers on a fresh db. Idempotent. |
| `ensure_db() -> None` | Run `init_db()` once per resolved path (called automatically by every query). |
| `db_path() -> Path` | The resolved SQLite file path. |

### Profile

| Function | Description |
|----------|-------------|
| `get_profile(user_id="default") -> dict \| None` | Profile row (`id`, `cash_balance`, `created_at`), or None. |
| `get_or_create_profile(user_id="default") -> dict` | Profile, creating it with `cash_balance=10000.0` if absent. |
| `update_cash_balance(balance, user_id="default") -> None` | Set the cash balance. |

### Watchlist

| Function | Description |
|----------|-------------|
| `list_watchlist(user_id="default") -> list[str]` | Watched tickers, oldest first. |
| `add_watchlist_ticker(ticker, user_id="default") -> None` | Add a ticker (no-op if already present). |
| `remove_watchlist_ticker(ticker, user_id="default") -> None` | Remove a ticker (no-op if absent). |

### Positions

| Function | Description |
|----------|-------------|
| `get_position(ticker, user_id="default") -> dict \| None` | One position row, or None. |
| `list_positions(user_id="default") -> list[dict]` | All positions, ordered by ticker. |
| `upsert_position(ticker, quantity, avg_cost, user_id="default") -> dict` | Insert or update; returns the stored row. |
| `delete_position(ticker, user_id="default") -> None` | Remove a position. |

### Trades

| Function | Description |
|----------|-------------|
| `insert_trade(ticker, side, quantity, price, user_id="default") -> dict` | Append a trade (`side` = `"buy"`/`"sell"`); returns the row. |
| `list_trades(user_id="default", limit=None) -> list[dict]` | Trades newest first, optionally capped. |

### Portfolio Snapshots

| Function | Description |
|----------|-------------|
| `insert_snapshot(total_value, user_id="default") -> dict` | Record a total-value snapshot; returns the row. |
| `list_snapshots(user_id="default", limit=None) -> list[dict]` | Snapshots oldest first (chart order). |

### Chat Messages

| Function | Description |
|----------|-------------|
| `insert_chat_message(role, content, actions=None, user_id="default") -> dict` | Append a message; `actions` (any JSON-serializable value or None) stored as JSON. Returns the row with `actions` parsed. |
| `list_chat_messages(user_id="default", limit=None) -> list[dict]` | Messages oldest first; `limit` returns the most recent N, still in chronological order. |

## Tests

**21 tests, all passing** — `backend/tests/db/test_db.py`. Each test uses a
temp db file (`FINALLY_DB_PATH` monkeypatched to `tmp_path`); the real
`db/finally.db` is never touched.

Coverage: table creation, seed correctness, lazy init, idempotent re-init
(preserving user edits), CRUD roundtrips for every table, `(user_id, ticker)`
UNIQUE enforcement (watchlist + positions), chat `actions` JSON roundtrip,
`limit` behavior, and per-user isolation.

```bash
cd backend
uv run --extra dev pytest tests/db -v
uv run --extra dev ruff check app/db tests/db
```
