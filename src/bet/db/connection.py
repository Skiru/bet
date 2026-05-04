"""Database connection management for sync and async access."""

import sqlite3
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path

import aiosqlite

from bet.db.schema import init_db

DEFAULT_DB_PATH = (
    Path(__file__).parent.parent.parent.parent / "betting" / "data" / "betting.db"
)


def _configure_connection(conn: sqlite3.Connection) -> None:
    """Apply standard pragmas and settings."""
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
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
    conn = await aiosqlite.connect(str(db_path))
    await conn.execute("PRAGMA journal_mode = WAL")
    await conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        await conn.commit()
    except Exception:
        await conn.rollback()
        raise
    finally:
        await conn.close()
