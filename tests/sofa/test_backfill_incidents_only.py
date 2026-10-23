"""backfill_event_stats.py --incidents-only: football /incidents for rows that
hold statistics but never got incidents.

Coverage audit 2026-10-23 (docs/sofa/history/AUDYT_POKRYCIA_2026-10-23.md):
"already asked" keys on statistics alone, so a football row saved with
statistics and no incidents was never asked again - 8,560 refereed matches,
whose card points the referee record (bet.sofa.referees) cannot count. The
mode asks /incidents only and never touches the statistics already stored.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from bet.sofa.db import get_connection, migrate
from scripts.sofa import backfill_event_stats as bes

NOW = 1_800_000_000
DAY = 86400


def _db(tmp_path: Path) -> str:
    db = str(tmp_path / "sofa.db")
    migrate(db)
    rows = [  # (event, sport, start, statistics, incidents)
        (1, "football", NOW - DAY, '{"s": 1}', None),        # target
        (2, "football", NOW - DAY, '{"s": 1}', '{"i": 1}'),  # complete
        (3, "football", NOW - DAY, None, None),              # 404 statistics
        (4, "tennis", NOW - DAY, '{"s": 1}', None),          # not football
        (5, "football", NOW - 900 * DAY, '{"s": 1}', None),  # too old
    ]
    with get_connection(db) as conn:
        for eid, sport, ts, stats, inc in rows:
            conn.execute(
                "INSERT INTO sofa_listed_event (event_id, sport, start_ts,"
                " fetched_at, event_json) VALUES (?, ?, ?, '2026-10-01', '{}')",
                (eid, sport, ts))
            conn.execute(
                "INSERT INTO sofa_event_stats (sofascore_event_id, fetched_at,"
                " statistics_json, incidents_json, status_type)"
                " VALUES (?, '2026-10-01', ?, ?, 'finished')", (eid, stats, inc))
    return db


def test_targets_are_football_rows_with_statistics_and_no_incidents(
        tmp_path: Path) -> None:
    db = _db(tmp_path)
    assert bes.incidents_only_targets(db, NOW - 365 * DAY) == [1]


class _Client:
    def __init__(self) -> None:
        self.asked: list[str] = []

    def event_statistics(self, eid: int) -> Any:
        self.asked.append(f"statistics {eid}")
        return {"new": True}

    def event_incidents(self, eid: int) -> Any:
        self.asked.append(f"incidents {eid}")
        return {"incidents": [{"incidentType": "card"}]}


class _Cache:
    def __init__(self) -> None:
        self.saved: list[tuple[int, Any, Any, str]] = []

    def save_event_stats(self, eid: int, stats: Any, inc: Any, status: str) -> None:
        self.saved.append((eid, stats, inc, status))


def test_incidents_only_asks_incidents_and_keeps_statistics() -> None:
    client, cache = _Client(), _Cache()
    run = bes.Backfill(client, cache, sport="football", incidents_only=True)
    run.fetch_one({"id": 1, "tournament": {"uniqueTournament": {"id": 17}}})
    assert client.asked == ["incidents 1"]
    assert cache.saved == [(1, None, {"incidents": [{"incidentType": "card"}]},
                            "finished")]
    assert run.counts["incidents"] == 1


def test_saving_none_statistics_keeps_the_stored_ones(tmp_path: Path) -> None:
    from bet.sofa.cache import SofaCache
    from bet.sofa.config import SofaConfig

    db = _db(tmp_path)
    cache = SofaCache(SofaConfig.from_env().__class__(
        **{**SofaConfig.from_env().__dict__, "db_path": db}))
    cache.save_event_stats(1, None, {"incidents": []}, "finished")
    with get_connection(db) as conn:
        row = conn.execute(
            "SELECT statistics_json, incidents_json FROM sofa_event_stats"
            " WHERE sofascore_event_id = 1").fetchone()
    assert json.loads(row[0]) == {"s": 1}
    assert json.loads(row[1]) == {"incidents": []}
