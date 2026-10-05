# ruff: noqa: E501  - rows of a fixture table.
"""measure_blocked_families (plan 2026-10-05 F1.3): claimed vs realised, by match."""

from __future__ import annotations

import sqlite3

from scripts.sofa.measure_blocked_families import (
    BLOCKED,
    Row,
    gap_interval,
    load_rows,
    summarise,
)


def test_summary_is_per_row_and_the_interval_resamples_matches() -> None:
    rows = [Row(1, 0.8, True, 0.75, 1.30), Row(1, 0.8, True, 0.75, 1.30),
            Row(2, 0.8, False, None, 1.30), Row(3, 0.8, True, 0.70, None)]
    r = summarise("both_over_goals", rows, n_boot=200)
    assert (r.rows, r.matches) == (4, 3)
    assert abs(r.realised - 0.75) < 1e-9 and abs(r.gap + 0.05) < 1e-9
    assert r.priced_rows == 3 and r.market_p is not None and abs(r.market_p - 0.7333333) < 1e-6
    assert r.roi_rows == 3 and r.roi is not None and abs(r.roi - (0.3 + 0.3 - 1.0) / 3) < 1e-9
    assert r.gap_lo is not None and r.gap_hi is not None and r.gap_lo <= r.gap <= r.gap_hi
    assert gap_interval(rows[:2]) is None  # one match: no interval


def test_load_rows_skips_cache_replay_and_the_low_band() -> None:
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE sofa_settled_row (run_date TEXT, sofascore_event_id INTEGER, market TEXT, "
                 "p_central REAL, outcome TEXT, market_p REAL, offered_odds REAL)")
    conn.executemany("INSERT INTO sofa_settled_row VALUES (?,?,?,?,?,?,?)", [
        ("2026-10-01", 1, "games_set1_total", 0.82, "WIN", 0.80, 1.25),
        ("2026-10-01", 1, "games_set1_total", 0.40, "LOSS", 0.45, 2.10),   # below the floor
        ("cache-calibration", 2, "games_set1_total", 0.90, "WIN", None, None),  # replay, not live
        ("2026-10-02", 3, "corners_total", 0.90, "WIN", 0.85, 1.15),       # not a blocked family
    ])
    rows = load_rows(conn, BLOCKED["TENNIS_SET_MARKET_NOT_ADMITTED"], min_p=0.70,
                     date_from="2026-09-18", date_to="2026-10-04")
    assert list(rows) == ["games_set1_total"]
    assert rows["games_set1_total"] == [Row(1, 0.82, True, 0.80, 1.25)]
