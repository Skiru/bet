"""Run identity and per-step run bookkeeping.

One ``run_id`` is minted by DISCOVER and travels through the artifacts
(``EventListV1.run_id`` -> ``EventDossierListV1.run_id`` ->
``StatsSheetV1.run_id``), so ENRICH and ANALYZE never have to guess which
DISCOVER produced their input. Each step also records itself in the existing
``pipeline_runs`` table, which makes "show me everything from run X" a single
query instead of a reconstruction from file mtimes.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from bet.db.connection import get_db

STEPS = ("DISCOVER", "ENRICH", "ANALYZE")


def new_run_id(date: str) -> str:
    """Mint a run id for ``date``.

    Shape: ``simple_stats-2026-08-25-T131229Z-a1b2c3d4``. The timestamp makes
    runs sort chronologically at a glance; the random suffix keeps two runs
    started in the same second distinct.
    """
    stamp = datetime.now(timezone.utc).strftime("T%H%M%SZ")
    return f"simple_stats-{date}-{stamp}-{uuid.uuid4().hex[:8]}"


def record_pipeline_run(
    conn: sqlite3.Connection,
    *,
    date: str,
    step: str,
    status: str,
    run_id: str,
    stats: dict | None = None,
    error_message: str | None = None,
    started_at: str | None = None,
) -> None:
    """Upsert this step's row in ``pipeline_runs``.

    The table's ``UNIQUE(date, step)`` means a rerun overwrites rather than
    accumulating, which matches how the rest of this pipeline behaves (a rerun
    for a date replaces that date's result). ``run_id`` lives inside the free
    ``stats`` JSON because the table has no dedicated column and section 8 of
    the plan rules out migrations.
    """
    payload = {"run_id": run_id, **(stats or {})}
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        INSERT INTO pipeline_runs (date, step, status, started_at, completed_at, error_message, stats)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(date, step) DO UPDATE SET
            status = excluded.status,
            started_at = excluded.started_at,
            completed_at = excluded.completed_at,
            error_message = excluded.error_message,
            stats = excluded.stats
        """,
        (
            date,
            f"simple_stats:{step}",
            status,
            started_at or now,
            now,
            error_message,
            json.dumps(payload, ensure_ascii=False, default=str),
        ),
    )


def record_run(
    *,
    date: str,
    step: str,
    status: str,
    run_id: str,
    db_path: str | Path | None = None,
    stats: dict | None = None,
    error_message: str | None = None,
    started_at: str | None = None,
) -> None:
    """``record_pipeline_run`` with its own short-lived connection, for callers
    that are not already inside a transaction."""
    from bet.simple_stats.persistence import default_db_path

    with get_db(db_path or default_db_path()) as conn:
        record_pipeline_run(
            conn,
            date=date,
            step=step,
            status=status,
            run_id=run_id,
            stats=stats,
            error_message=error_message,
            started_at=started_at,
        )


def load_run(date: str, db_path: str | Path | None = None) -> dict[str, dict]:
    """Every recorded simple_stats step for ``date``, keyed by step name.

    This is the lineage read-path: given a date you get each step's status,
    run_id, timings and artifact digests without touching the filesystem.
    """
    from bet.simple_stats.persistence import default_db_path

    out: dict[str, dict] = {}
    with get_db(db_path or default_db_path()) as conn:
        rows = conn.execute(
            "SELECT step, status, started_at, completed_at, error_message, stats "
            "FROM pipeline_runs WHERE date = ? AND step LIKE 'simple_stats:%'",
            (date,),
        ).fetchall()
    for row in rows:
        try:
            stats = json.loads(row["stats"]) if row["stats"] else {}
        except (TypeError, ValueError):
            stats = {}
        out[str(row["step"]).split(":", 1)[-1]] = {
            "status": row["status"],
            "started_at": row["started_at"],
            "completed_at": row["completed_at"],
            "error_message": row["error_message"],
            **stats,
        }
    return out
