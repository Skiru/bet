"""Canonical SQLite connection and transaction policy."""

import os
import sqlite3
from contextlib import asynccontextmanager, contextmanager
from collections.abc import AsyncIterator, Callable, Iterator
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, TypeVar

try:
    import aiosqlite
except ImportError:
    aiosqlite = None  # type: ignore[assignment]

BUSY_TIMEOUT_MS = 30_000
T = TypeVar("T")


class DatabaseMode(str, Enum):
    READ_ONLY = "READ_ONLY"
    READ_WRITE = "READ_WRITE"


@dataclass(frozen=True)
class DatabaseInfrastructureError(RuntimeError):
    code: str
    operation: str
    retryable: bool = False

    def __str__(self) -> str:
        return f"{self.code}: database {self.operation} failed"


def _resolve_db_path(db_path: Path | str | None = None) -> Path | str:
    """Resolve the effective DB path from env vars or explicit argument.

    Resolution order:
    1. Explicit `db_path` argument (used by tests/custom callers)
    2. `BET_DB_PATH` environment variable (direct path)
    3. `DATABASE_URL` environment variable (sqlite:/// or sqlite:///:memory:)
    A path is mandatory. There is no implicit operational database fallback.
    """
    live_shadow = os.environ.get("BET_PIPELINE_RUNTIME_MODE") == "LIVE_ANALYSIS_SHADOW"
    if live_shadow:
        from bet.pipeline.runtime_execution import RuntimeExecutionContext

        context = RuntimeExecutionContext.from_child_env(dict(os.environ))
        requested = Path(str(db_path or context.shadow_db_path)).resolve()
        if requested != Path(context.shadow_db_path).resolve():
            raise DatabaseInfrastructureError(
                code="SHADOW_DB_TARGET_MISMATCH", operation="resolve_path"
            )
        return context.shadow_db_path
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

    raise DatabaseInfrastructureError(
        code="DB_PATH_REQUIRED",
        operation="resolve_path",
    )


def connect_sqlite(
    db_path: Path | str, *, readonly: bool = False, timeout_ms: int = BUSY_TIMEOUT_MS
) -> sqlite3.Connection:
    """Connect to a SQLite database using canonical settings."""
    resolved = str(db_path)
    if readonly:
        resolved_p = Path(resolved).resolve()
        conn = sqlite3.connect(f"file:{resolved_p}?mode=ro", uri=True)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(f"PRAGMA busy_timeout = {timeout_ms}")
        conn.execute("PRAGMA query_only = ON")
        conn.row_factory = sqlite3.Row
        return conn

    conn = sqlite3.connect(resolved)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(f"PRAGMA busy_timeout = {timeout_ms}")
    conn.row_factory = sqlite3.Row
    return conn


def _configure_connection(conn: sqlite3.Connection) -> None:
    """Apply standard pragmas and settings."""
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
    conn.row_factory = sqlite3.Row


@contextmanager
def get_db(db_path: Path | str | None = None) -> Iterator[sqlite3.Connection]:
    """Own one explicit read-write transaction and commit only on clean exit."""
    if os.environ.get("BET_PIPELINE_RUNTIME_MODE") == "LIVE_ANALYSIS_SHADOW":
        from bet.pipeline.runtime_execution import (
            RuntimeDatabaseAccessPolicy,
            RuntimeDbRole,
            RuntimeExecutionContext,
        )

        context = RuntimeExecutionContext.from_child_env(dict(os.environ))
        conn = RuntimeDatabaseAccessPolicy(context).connect(
            RuntimeDbRole.SHADOW_READ_WRITE
        )
    else:
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


@contextmanager
def get_readonly_db(db_path: Path | str | None = None) -> Iterator[sqlite3.Connection]:
    """Open the canonical SQLite database with enforced read-only/query-only semantics."""
    resolved = Path(str(_resolve_db_path(db_path))).resolve()
    conn = sqlite3.connect(f"file:{resolved}?mode=ro", uri=True)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
    conn.execute("PRAGMA query_only = ON")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


@asynccontextmanager
async def get_async_db(db_path: Path | str | None = None) -> AsyncIterator[Any]:
    """Async context manager using aiosqlite. Same pragmas as get_db.

    Resolves the DB path via `_resolve_db_path()`.
    """
    if aiosqlite is None:
        raise ImportError(
            "aiosqlite is required for async database access. Install with: pip install aiosqlite"
        )
    resolved = _resolve_db_path(db_path)
    conn = await aiosqlite.connect(str(resolved))
    await conn.execute("PRAGMA journal_mode = WAL")
    await conn.execute("PRAGMA foreign_keys = ON")
    await conn.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        await conn.commit()
    except Exception:
        await conn.rollback()
        raise
    finally:
        await conn.close()


def retry_on_lock(
    fn: Callable[..., T],
    *args: Any,
    max_retries: int = 3,
    base_delay: float = 0.5,
    **kwargs: Any,
) -> T:
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
                delay = base_delay * (2**attempt)
                logging.getLogger(__name__).warning(
                    "DB locked (attempt %d/%d), retrying in %.1fs",
                    attempt + 1,
                    max_retries,
                    delay,
                )
                time.sleep(delay)
                continue
            raise
