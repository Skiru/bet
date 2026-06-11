"""Database connection management for sync and async access.

Environment-aware DB resolver:
- `BET_DB_PATH` env var: direct path override
- `DATABASE_URL` env var: sqlite:///path or sqlite:///:memory:
- Fallback: betting/data/betting.db
"""

import os
import sqlite3
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path

try:
    import aiosqlite
except ImportError:
    aiosqlite = None  # type: ignore[assignment]

DEFAULT_DB_PATH = (
    Path(__file__).parent.parent.parent.parent / "betting" / "data" / "betting.db"
)


def _resolve_db_path(db_path: Path | str | None = None) -> Path | str:
    """Resolve the effective DB path from env vars or explicit argument.

    Resolution order:
    1. Explicit `db_path` argument (used by tests/custom callers)
    2. `BET_DB_PATH` environment variable (direct path)
    3. `DATABASE_URL` environment variable (sqlite:/// or sqlite:///:memory:)
    4. `DEFAULT_DB_PATH` fallback
    """
    if db_path is not None:
        return db_path

    bet_db_path = os.environ.get("BET_DB_PATH")
    if bet_db_path:
        return bet_db_path

    database_url = os.environ.get("DATABASE_URL", "")
    if database_url:
        if database_url.startswith("sqlite:///:memory:"):
            return ":memory:"
        if database_url.startswith("sqlite:///"):
            return database_url.replace("sqlite:///", "", 1)
        if database_url.startswith("sqlite://"):
            raise ValueError(
                f"Unsupported DATABASE_URL scheme: {database_url}. "
                "Use sqlite:///path/to/file.db or sqlite:///:memory:"
            )
        raise ValueError(
            f"Unsupported DATABASE_URL scheme: {database_url}. "
            "Only sqlite:// is supported."
        )

    return DEFAULT_DB_PATH


def _configure_connection(conn: sqlite3.Connection) -> None:
    """Apply standard pragmas and settings."""
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.row_factory = sqlite3.Row


@contextmanager
def get_db(db_path: Path | str | None = None):
    """Context manager for SQLite connections.

    Resolves the DB path via `_resolve_db_path()`:
    - `BET_DB_PATH` env var
    - `DATABASE_URL` env var (sqlite:///path or sqlite:///:memory:)
    - Falls back to `betting/data/betting.db`

    Enables WAL mode and foreign keys. Commits on clean exit, rolls back on exception.
    """
    resolved = _resolve_db_path(db_path)
    conn = sqlite3.connect(str(resolved))
    _configure_connection(conn)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@asynccontextmanager
async def get_async_db(db_path: Path | str | None = None):
    """Async context manager using aiosqlite. Same pragmas as get_db.

    Resolves the DB path via `_resolve_db_path()`.
    """
    if aiosqlite is None:
        raise ImportError("aiosqlite is required for async database access. Install with: pip install aiosqlite")
    resolved = _resolve_db_path(db_path)
    conn = await aiosqlite.connect(str(resolved))
    await conn.execute("PRAGMA journal_mode = WAL")
    await conn.execute("PRAGMA foreign_keys = ON")
    await conn.execute("PRAGMA busy_timeout = 30000")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        await conn.commit()
    except Exception:
        await conn.rollback()
        raise
    finally:
        await conn.close()


def retry_on_lock(fn, *args, max_retries: int = 3, base_delay: float = 0.5, **kwargs):
    """Call fn(*args, **kwargs) with retry on sqlite3.OperationalError (database locked).
    
    Exponential backoff: 0.5s → 1s → 2s (default 3 retries).
    Re-raises non-lock OperationalErrors immediately.
    """
    import time
    import logging
    for attempt in range(max_retries + 1):
        try:
            return fn(*args, **kwargs)
        except sqlite3.OperationalError as e:
            if "locked" in str(e).lower() and attempt < max_retries:
                delay = base_delay * (2 ** attempt)
                logging.getLogger(__name__).warning(
                    "DB locked (attempt %d/%d), retrying in %.1fs",
                    attempt + 1, max_retries, delay,
                )
                time.sleep(delay)
                continue
            raise
