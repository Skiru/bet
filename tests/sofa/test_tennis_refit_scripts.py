"""The between-days tennis refit scripts read the cache without writing it.

2026-10-03 night: the three tennis fits were re-run against a 41 GB sofa.db a
backfill was writing at the same time, into a scratch directory. Two things
had to hold: measure_side_correlations takes the DB on its command line and
opens it read-only (it used to open SOFA_DB_PATH for writing), and the tier
fit parses only the statistics of the tennis matches it counts (it used to
parse every football row too).
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

from scripts.sofa import fit_tennis_tier_baselines as tier_fit
from scripts.sofa import measure_side_correlations as side_corr


def _stats_db(path: Path) -> str:
    db = str(path / "sofa.db")
    con = sqlite3.connect(db)
    con.execute(
        "CREATE TABLE sofa_event_stats (sofascore_event_id INTEGER PRIMARY KEY, "
        "fetched_at TEXT NOT NULL, statistics_json TEXT, incidents_json TEXT, "
        "status_type TEXT NOT NULL, lineups_json TEXT)"
    )
    con.execute(
        "CREATE TABLE sofa_entity_events (sofascore_entity_id INTEGER NOT NULL, "
        "kind TEXT NOT NULL, page INTEGER NOT NULL, fetched_at TEXT NOT NULL, "
        "events_json TEXT NOT NULL, "
        "PRIMARY KEY (sofascore_entity_id, kind, page))"
    )
    rows = [(eid, "t", json.dumps({"id": eid}), None, "finished", None)
            for eid in range(1, 1201)]
    rows.append((5000, "t", None, None, "finished", None))
    con.executemany("INSERT INTO sofa_event_stats VALUES (?,?,?,?,?,?)", rows)
    con.commit()
    con.close()
    return db


def test_tier_fit_reads_only_the_statistics_it_was_asked_for(
    tmp_path: Path,
) -> None:
    db = _stats_db(tmp_path)
    # Across more than one IN (...) chunk, with a repeat and an id with no row.
    wanted = [3, 3, 700, 1200, 999_999]
    got = tier_fit.load_statistics(db, wanted)
    assert sorted(got) == [3, 700, 1200]
    assert got[700] == {"id": 700}
    # No ids given: every row with statistics, as before.
    assert len(tier_fit.load_statistics(db)) == 1200
    # An empty selection reads nothing rather than everything.
    assert tier_fit.load_statistics(db, []) == {}


def test_side_correlations_open_the_db_read_only(tmp_path: Path) -> None:
    db = _stats_db(tmp_path)
    con = side_corr.connect_read_only(Path(db))
    try:
        assert con.execute("SELECT count(*) FROM sofa_event_stats").fetchone() == (
            1201,
        )
        with pytest.raises(sqlite3.OperationalError):
            con.execute("DELETE FROM sofa_event_stats")
    finally:
        con.close()
    # A wrong path is an error, not a new empty database.
    missing = tmp_path / "nope.db"
    with pytest.raises(sqlite3.OperationalError):
        side_corr.connect_read_only(missing).execute("SELECT 1")
    assert not missing.exists()


def test_side_correlations_take_the_db_and_out_on_the_command_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = _stats_db(tmp_path)
    out = tmp_path / "scratch" / "corr.json"
    # SOFA_DB_PATH points elsewhere: --db wins and nothing is created there.
    elsewhere = tmp_path / "elsewhere.db"
    monkeypatch.setenv("SOFA_DB_PATH", str(elsewhere))
    monkeypatch.setattr(
        sys, "argv", ["measure_side_correlations.py", "--db", db, "--out", str(out)]
    )
    assert side_corr.main() == 0
    written = json.loads(out.read_text())
    assert written["_min_pairs"] == side_corr.MIN_PAIRS
    assert not elsewhere.exists()


def _listed(eid: int, sport: str, home: int, away: int) -> dict[str, object]:
    return {
        "id": eid,
        "homeTeam": {"id": home},
        "awayTeam": {"id": away},
        "tournament": {"category": {"sport": {"slug": sport}}},
    }


def _stats(**items: tuple[float, float]) -> str:
    return json.dumps({"statistics": [{"period": "ALL", "groups": [{
        "statisticsItems": [
            {"key": k, "homeValue": h, "awayValue": a} for k, (h, a) in items.items()
        ]}]}]})


def test_each_pool_holds_only_its_own_sport(tmp_path: Path) -> None:
    """Volleyball's `aces` shares the tennis key; it must not enter the tennis
    pool, and a football key on a tennis event must not enter football's."""
    db = str(tmp_path / "sofa.db")
    con = sqlite3.connect(db)
    con.execute(
        "CREATE TABLE sofa_event_stats (sofascore_event_id INTEGER PRIMARY KEY, "
        "fetched_at TEXT NOT NULL, statistics_json TEXT, incidents_json TEXT, "
        "status_type TEXT NOT NULL, lineups_json TEXT)"
    )
    con.execute(
        "CREATE TABLE sofa_entity_events (sofascore_entity_id INTEGER NOT NULL, "
        "kind TEXT NOT NULL, page INTEGER NOT NULL, fetched_at TEXT NOT NULL, "
        "events_json TEXT NOT NULL, "
        "PRIMARY KEY (sofascore_entity_id, kind, page))"
    )
    events = [
        _listed(1, "tennis", 10, 11),
        _listed(2, "volleyball", 20, 21),
        _listed(3, "football", 30, 31),
        {"id": 4, "homeTeam": {"id": 40}, "awayTeam": {"id": 41}},  # no sport
    ]
    con.execute(
        "INSERT INTO sofa_entity_events VALUES (1, 'last', 0, 't', ?)",
        (json.dumps({"events": events}),),
    )
    con.executemany(
        "INSERT INTO sofa_event_stats VALUES (?, 't', ?, NULL, 'finished', NULL)",
        [
            (1, _stats(aces=(5, 3), doubleFaults=(2, 1), cornerKicks=(1, 1))),
            (2, _stats(aces=(7, 6))),
            (3, _stats(cornerKicks=(6, 4), aces=(9, 9))),
            (4, _stats(aces=(1, 1), cornerKicks=(2, 2))),
        ],
    )
    con.commit()
    con.close()

    pools = side_corr.collect(Path(db))
    assert pools["aces"] == [(10, 11, 5.0, 3.0)]
    assert pools["double_faults"] == [(10, 11, 2.0, 1.0)]
    assert pools["corners"] == [(30, 31, 6.0, 4.0)]
    assert set(side_corr.METRIC_SPORT) == {*side_corr.STAT_KEYS, "cards_points"}


def test_side_correlations_refuse_a_missing_db(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        sys, "argv",
        ["measure_side_correlations.py", "--db", str(tmp_path / "nope.db"),
         "--out", str(tmp_path / "o.json")],
    )
    with pytest.raises(SystemExit) as exc:
        side_corr.main()
    assert exc.value.code == 2
    assert not (tmp_path / "nope.db").exists()
