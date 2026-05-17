"""Database connection management for sync and async access."""

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


def _configure_connection(conn: sqlite3.Connection) -> None:
    """Apply standard pragmas and settings."""
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.row_factory = sqlite3.Row


@contextmanager
def get_db(db_path: Path | str = DEFAULT_DB_PATH):
    """Context manager for SQLite connections.

    - Enables WAL mode and foreign keys
    - Sets row_factory to sqlite3.Row for dict-like access
    - Commits on clean exit, rolls back on exception
    """
    conn = sqlite3.connect(str(db_path))
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
async def get_async_db(db_path: Path | str = DEFAULT_DB_PATH):
    """Async context manager using aiosqlite. Same pragmas as get_db."""
    if aiosqlite is None:
        raise ImportError("aiosqlite is required for async database access. Install with: pip install aiosqlite")
    conn = await aiosqlite.connect(str(db_path))
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
