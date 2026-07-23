"""
conftest.py — 共享 fixtures
"""
import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture
def mock_conn():
    """Mock asyncpg connection with fetchrow + fetch + execute"""
    conn = AsyncMock()
    conn.fetchrow = AsyncMock()
    conn.fetch = AsyncMock()
    conn.execute = AsyncMock()
    return conn


@pytest.fixture
def mock_pool(mock_conn):
    """Mock pool with acquire context manager"""
    pool = MagicMock()
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=mock_conn)
    cm.__aexit__ = AsyncMock(return_value=None)
    pool.acquire.return_value = cm
    return pool
