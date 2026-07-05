"""Pytest configuration and fixtures."""

import pytest


@pytest.fixture
def event_loop_policy():
    """Use the default event loop policy for all async tests."""
    import asyncio

    return asyncio.DefaultEventLoopPolicy()


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """Point the db layer at a fresh temp file per test (never the real db)."""
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("FINALLY_DB_PATH", str(db_file))
    from app.db import connection as conn_mod

    conn_mod._initialized_paths.clear()
    yield db_file
    conn_mod._initialized_paths.clear()
