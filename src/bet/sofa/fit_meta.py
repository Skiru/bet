"""What every fit writer shares: which settled rows it may read, and the
metadata that says when it read them.

Two defects of 2026-10-02 live here:

* Friendlies were in the fits. SAMPLES and the football rating drop the
  competitions in config/sofa_friendly_competitions.json, but fit_constants
  and fit_confidence read every settled row - about 6% of the global
  goals_for pool - so a prior and a curve described games the sheet never
  samples. `friendly_exclusion_sql` is the one filter both use.
* A fit carried no time. `fit_stamp` gives every output the wall clock of the
  fit and the newest dated `run_date` it read (the cache replay files its rows
  under the literal 'cache-calibration', which sorts after every date and so
  is excluded from the max).
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from typing import Any

from bet.sofa.samples import FRIENDLY_COMPETITION_IDS

# Keys the operator writes into a fitted file by hand. A fit that rebuilds the
# file from the DB must carry them over, or the next refit silently undoes an
# operator decision (admitted_player_markets: Calibration.player_prop_not_admitted).
OPERATOR_KEYS: tuple[str, ...] = ("admitted_player_markets",)


def friendly_exclusion_sql(
    prefix: str = "", ids: frozenset[int] = FRIENDLY_COMPETITION_IDS
) -> str:
    """A WHERE term that drops football rows of friendly competitions.

    NULL-safe: a row without a competition id is kept (``x IN (...)`` on a
    NULL would be NULL, and NOT NULL drops the row).
    """
    if not ids:
        return "1"
    listed = ",".join(str(int(c)) for c in sorted(ids))
    return (
        f"NOT ({prefix}sport = 'football' AND "
        f"COALESCE({prefix}competition_id, -1) IN ({listed}))"
    )


def max_settled_run_date(conn: sqlite3.Connection) -> str | None:
    """Newest dated run_date in sofa_settled_row (index-backed), or None."""
    columns = {r[1] for r in conn.execute("PRAGMA table_info(sofa_settled_row)")}
    if "run_date" not in columns:
        return None
    row = conn.execute(
        "SELECT MAX(run_date) FROM sofa_settled_row "
        "WHERE run_date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'"
    ).fetchone()
    value = row[0] if row is not None else None
    return str(value) if value is not None else None


def fit_stamp(conn: sqlite3.Connection) -> dict[str, Any]:
    """`fitted_at_utc`, `max_settled_run_date` and the friendly filter size."""
    return {
        "fitted_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "max_settled_run_date": max_settled_run_date(conn),
        "friendly_competitions_excluded": len(FRIENDLY_COMPETITION_IDS),
    }


def carry_operator_keys(new: dict[str, Any], prior: dict[str, Any] | None) -> None:
    """Copy every operator-owned key of `prior` into `new`, in place."""
    if not prior:
        return
    for key in OPERATOR_KEYS:
        if key in prior and key not in new:
            new[key] = prior[key]
