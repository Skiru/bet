"""The cache replay settles a match total ONCE, from the pooled sample
(2026-10-02).

calibrate_from_cache._settle_side ran once per side and wrote each side's
`*_total` rows under the one key (event, market, "", line, direction), so the
away side's rows overwrote the home side's wherever the two line grids met -
a replayed total carried one side's ten matches, while SHEET prices a total
from both sides' samples pooled, one historical match once
(run_sheet.deduplicate_observations over side_a + side_b + h2h).
"""

from __future__ import annotations

import sqlite3
import statistics
from pathlib import Path

from bet.sofa.db import migrate
from scripts.sofa.calibrate_from_cache import (
    MIN_SAMPLE,
    SAMPLE_N,
    Played,
    SettledRow,
    build,
    write_settled,
)

HOME, AWAY = 1, 2
TARGET = 999


def _match(eid: int, ts: int, home: int, away: int, h: float, a: float) -> Played:
    return Played(
        event_id=eid, timestamp=ts, home_id=home, away_id=away,
        sport="football", competition_id=17, values={"corners": (h, a)},
    )


def _history(away_games: int = 9) -> tuple[list[Played], list[float], list[float],
                                           list[float], list[float]]:
    """HOME and AWAY each play their own opponents, plus one earlier meeting.

    Returns (played, home own, home totals, away own, away totals), each side's
    lists in chronological order, the meeting included in both.
    """
    played: list[Played] = []
    home_own: list[float] = []
    home_tot: list[float] = []
    away_own: list[float] = []
    away_tot: list[float] = []
    ts = 1_000
    eid = 100
    for i in range(9):  # HOME's corners matches: low totals
        h, a = 3.0 + i % 3, 3.0
        played.append(_match(eid, ts, HOME, 10 + i, h, a))
        home_own.append(h)
        home_tot.append(h + a)
        ts += 10
        eid += 1
    for i in range(away_games):  # AWAY's: high totals
        h, a = 7.0, 5.0 + i % 2
        played.append(_match(eid, ts, 20 + i, AWAY, h, a))
        away_own.append(a)
        away_tot.append(h + a)
        ts += 10
        eid += 1
    # The earlier meeting sits in both histories.
    played.append(_match(eid, ts, HOME, AWAY, 4.0, 6.0))
    for own, tot, v in ((home_own, home_tot, 4.0), (away_own, away_tot, 6.0)):
        own.append(v)
        tot.append(10.0)
    ts += 10
    played.append(_match(TARGET, ts, HOME, AWAY, 5.0, 4.0))
    return played, home_own, home_tot, away_own, away_tot


def _target(rows: list[SettledRow], market: str) -> list[SettledRow]:
    return [r for r in rows if r.event_id == TARGET and r.market == market]


def test_total_row_reads_the_pooled_sample_once_per_key(tmp_path: Path) -> None:
    played, home_own, home_tot, away_own, away_tot = _history()
    assert len(home_tot) >= MIN_SAMPLE and len(away_tot) >= MIN_SAMPLE
    rows = build(played, baselines={})

    totals = _target(rows, "corners_total")
    assert totals, "both sides have a sample: the total is settled"
    # The sheet's pool: both recent lists, the meeting (last in both) once.
    pooled = home_tot[-SAMPLE_N:] + away_tot[-SAMPLE_N:][:-1]
    assert len(pooled) == 19
    for row in totals:
        assert row.subject == ""
        assert row.sample_size == len(pooled)
        assert row.sample_mean == round(statistics.mean(pooled), 4)
        assert row.sample_sd == round(statistics.stdev(pooled), 4)
        assert row.actual == 9.0
    # The two per-side samples differ, so neither one alone is the pool.
    assert statistics.mean(home_tot) != statistics.mean(pooled)
    assert statistics.mean(away_tot) != statistics.mean(pooled)

    keys = [(r.event_id, r.market, r.subject, r.line, r.direction) for r in totals]
    assert len(keys) == len(set(keys)), "one row per total key"

    # *_for rows stay per side, each from its own history only.
    fors = _target(rows, "corners_for")
    by_subject = {r.subject for r in fors}
    assert by_subject == {str(HOME), str(AWAY)}
    for subject, own in ((str(HOME), home_own), (str(AWAY), away_own)):
        mine = [r for r in fors if r.subject == subject]
        assert mine
        for row in mine:
            assert row.sample_size == len(own[-SAMPLE_N:])
            assert row.sample_mean == round(statistics.mean(own[-SAMPLE_N:]), 4)

    # Nothing overwrites anything in the table: written == distinct keys.
    db = tmp_path / "sofa.db"
    migrate(str(db))
    written = write_settled(rows, db)
    with sqlite3.connect(db) as conn:
        stored = conn.execute(
            "SELECT COUNT(*) FROM sofa_settled_row WHERE run_date='cache-calibration'"
        ).fetchone()[0]
        stored_totals = conn.execute(
            "SELECT DISTINCT sample_size, sample_mean FROM sofa_settled_row "
            "WHERE sofascore_event_id = ? AND market = 'corners_total'",
            (TARGET,),
        ).fetchall()
    assert written == stored == len(rows)
    assert stored_totals == [(19, round(statistics.mean(pooled), 4))]


def test_total_is_not_settled_when_one_side_is_thin() -> None:
    # AWAY: 6 own matches + the meeting = 7 < MIN_SAMPLE.
    played, home_own, _, away_own, _ = _history(away_games=6)
    assert len(away_own) < MIN_SAMPLE <= len(home_own)
    rows = build(played, baselines={})
    assert _target(rows, "corners_total") == [], (
        "SHEET refuses a total with either side thin (THIN_SAMPLE)"
    )
    assert {r.subject for r in _target(rows, "corners_for")} == {str(HOME)}
