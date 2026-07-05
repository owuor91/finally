"""SQLite connection, schema initialization, and seed data.

Single-file SQLite for a single-user app: short-lived connections per call,
WAL mode, lazy idempotent init. No pool, no ORM.
"""

from __future__ import annotations

import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

DEFAULT_USER_ID = "default"
DEFAULT_CASH_BALANCE = 10000.0
DEFAULT_WATCHLIST = [
    "AAPL", "GOOGL", "MSFT", "AMZN", "TSLA",
    "NVDA", "META", "JPM", "V", "NFLX",
]

SCHEMA = """
CREATE TABLE IF NOT EXISTS users_profile (
    id TEXT PRIMARY KEY,
    cash_balance REAL NOT NULL DEFAULT 10000.0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS watchlist (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL DEFAULT 'default',
    ticker TEXT NOT NULL,
    added_at TEXT NOT NULL,
    UNIQUE(user_id, ticker)
);

CREATE TABLE IF NOT EXISTS positions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL DEFAULT 'default',
    ticker TEXT NOT NULL,
    quantity REAL NOT NULL,
    avg_cost REAL NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(user_id, ticker)
);

CREATE TABLE IF NOT EXISTS trades (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL DEFAULT 'default',
    ticker TEXT NOT NULL,
    side TEXT NOT NULL,
    quantity REAL NOT NULL,
    price REAL NOT NULL,
    executed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL DEFAULT 'default',
    total_value REAL NOT NULL,
    recorded_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL DEFAULT 'default',
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    actions TEXT,
    created_at TEXT NOT NULL
);
"""

_initialized_paths: set[str] = set()


def db_path() -> Path:
    """Resolve the SQLite file path: <project_root>/db/finally.db.

    Honors the FINALLY_DB_PATH env var override (used by tests). Resolved
    relative to this file, not cwd, since uvicorn may launch from backend/.
    """
    override = os.environ.get("FINALLY_DB_PATH")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[3] / "db" / "finally.db"


def now_iso() -> str:
    """Current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    """A fresh UUID4 string for a primary key."""
    return str(uuid.uuid4())


@contextmanager
def connection(ensure: bool = True) -> Iterator[sqlite3.Connection]:
    """Short-lived connection with WAL mode and Row factory.

    Commits on clean exit, rolls back on exception, always closes.
    Runs lazy init first unless ensure=False (init_db uses ensure=False).
    """
    if ensure:
        ensure_db()
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """Create tables (if missing) and seed default data on a fresh db.

    Idempotent: re-running never duplicates or wipes existing rows. Seed only
    runs when the default profile is absent, so user edits (e.g. removing a
    watchlist ticker) survive restarts.
    """
    with connection(ensure=False) as conn:
        conn.executescript(SCHEMA)
        exists = conn.execute(
            "SELECT 1 FROM users_profile WHERE id = ?", (DEFAULT_USER_ID,)
        ).fetchone()
        if exists is None:
            _seed(conn)


def _seed(conn: sqlite3.Connection) -> None:
    conn.execute(
        "INSERT INTO users_profile (id, cash_balance, created_at) VALUES (?, ?, ?)",
        (DEFAULT_USER_ID, DEFAULT_CASH_BALANCE, now_iso()),
    )
    conn.executemany(
        "INSERT INTO watchlist (id, user_id, ticker, added_at) VALUES (?, ?, ?, ?)",
        [(new_id(), DEFAULT_USER_ID, t, now_iso()) for t in DEFAULT_WATCHLIST],
    )


def ensure_db() -> None:
    """Run init_db once per resolved db path (cheap no-op thereafter)."""
    key = str(db_path())
    if key not in _initialized_paths:
        init_db()
        _initialized_paths.add(key)
