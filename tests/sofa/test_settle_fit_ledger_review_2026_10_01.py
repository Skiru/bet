"""SETTLE / FIT / ledger defects of the 2026-10-01 review.

- fit_confidence scored joint / comparative markets as counts against their
  line; they now enter no curve family.
- fit_constants scored K_CENTRE on derived rows as counts, and on priors that
  held the scored match's own value; derived rows are out and each prior
  leaves its own match out.
- calibrate_from_cache keyed matches by event id only, so a match listed
  under two ids entered its own sample.
- the ledger's ROI interval resampled days (two days -> the two day ROIs);
  it now resamples matches and refuses under MIN_CLUSTERS of them, as
  audit_clv does.
- the ledger carried no flag for builders graded at the haircut estimate.
- run_settle's value_roi would have counted a PUSH as -1.
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from scripts.sofa import (
    audit_ledger,
    calibrate_from_cache,
    fit_constants,
    record_results,
)
from scripts.sofa.run_settle import value_rows_return

REPO = Path(__file__).resolve().parents[2]


# --- 1: fit_confidence ------------------------------------------------------


def _fit_confidence(tmp_path: Path, rows: list[tuple[Any, ...]]) -> dict[str, Any]:
    db = tmp_path / "sofa.db"
    con = sqlite3.connect(db)
    con.execute("""create table sofa_settled_row (market text, line real,
        direction text, sample_size int, sample_mean real, sample_sd real,
        actual_value real, p_central real, sport text, sofascore_event_id int)""")
    con.execute("create table sofa_entity_events (kind text, events_json text)")
    events = {"events": [
        {"id": 1, "homeTeam": {"gender": "F"}, "awayTeam": {"gender": "F"},
         "tournament": {"category": {"sport": {"slug": "football"}}}},
    ]}
    con.execute("insert into sofa_entity_events values ('last', ?)",
                (json.dumps(events),))
    con.executemany("insert into sofa_settled_row values (?,?,?,?,?,?,?,?,?,?)", rows)
    con.commit()
    con.close()
    out = tmp_path / "cal.json"
    proc = subprocess.run(
        [sys.executable, "scripts/sofa/fit_confidence.py", "--db-path", str(db),
         "--out", str(out)],
        cwd=REPO, capture_output=True, text=True,
        env={"PYTHONPATH": "src:.", "PATH": "/usr/bin:/bin"},
    )
    assert proc.returncode == 0, proc.stderr
    doc: dict[str, Any] = json.loads(out.read_text())
    return doc


def test_a_derived_row_is_counted_in_no_confidence_curve(tmp_path: Path) -> None:
    counts = [("goals_total", 4.5, "UNDER", 10, 2.0, 1.2,
               2.0 if i % 5 else 6.0, 0.9, "football", 1 + i % 2)
              for i in range(1200)]
    # A handicap row: actual_value is a margin, the line is a handicap - read
    # as a count it would land in the same buckets as the goals above.
    derived = [(m, -1.5, "OVER", 10, 2.0, 1.2, 3.0, None, "football", 1)
               for m in ("handicap_goals", "most_corners", "both_over_corners")
               for _ in range(600)]
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    clean = _fit_confidence(tmp_path / "a", counts)
    mixed = _fit_confidence(tmp_path / "b", counts + derived)
    assert mixed["fitted_from"]["scored_rows"] == 1200
    for family in ("pooled", "pooled_by_sport", "by_market", "by_market_direction",
                   "by_class"):
        assert mixed[family] == clean[family], family
    assert not any(m.startswith(("handicap_", "most_", "both_over_"))
                   for m in mixed["by_market"])


# --- 1 + 4: fit_constants ---------------------------------------------------


def _settled_db(rows: list[dict[str, Any]]) -> sqlite3.Connection:
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.execute("""create table sofa_settled_row (id integer primary key,
        sofascore_event_id int, sport text, competition_id int, market text,
        subject text, line real, direction text, sample_size int,
        sample_mean real, sample_sd real, actual_value real, outcome text)""")
    for r in rows:
        con.execute(
            "insert into sofa_settled_row (sofascore_event_id, sport, "
            "competition_id, market, subject, line, direction, sample_size, "
            "sample_mean, sample_sd, actual_value, outcome) values "
            "(?,?,?,?,?,?,?,?,?,?,?,?)",
            (r["event"], "football", r.get("comp", 7), r["market"],
             r.get("subject", "1"), r.get("line", 2.5), r.get("direction", "OVER"),
             10, 2.0, 1.0, r["actual"], r.get("outcome", "WIN")),
        )
    return con


def test_k_centre_ignores_derived_rows() -> None:
    rows = [{"market": "goals_total", "competition_id": 7, "sample_mean": 2.0,
             "sample_size": 10, "sample_sd": 1.0, "line": 2.5,
             "direction": "OVER", "outcome": "WIN" if i % 2 else "LOSS"}
            for i in range(40)]
    derived = [{**r, "market": "handicap_goals", "line": -1.5,
                "outcome": "WIN"} for r in rows]
    assert (fit_constants._k_centre_curve(rows, {})
            == fit_constants._k_centre_curve(rows + derived, {}))


def test_a_k_centre_prior_leaves_its_own_match_out() -> None:
    # 31 matches of one league: 30 at 2.0 and the scored one at 10.0.
    rows = [{"event": e, "market": "goals_total", "actual": 2.0} for e in range(30)]
    rows.append({"event": 99, "market": "goals_total", "actual": 10.0})
    con = _settled_db(rows)
    totals = fit_constants.baseline_totals(con)
    assert totals[0]["goals_total"]["7"] == (70.0, 31)
    scored = {r["own_sum"]: dict(r)
              for r in con.execute(fit_constants.K_CENTRE_ROWS_LOO_SQL)}
    own = scored[10.0]
    assert own["own_n"] == 1
    # with its own 10.0 the prior is 70/31 = 2.26; without it, 2.0
    assert fit_constants.leave_match_out_prior(own, totals) == 2.0
    other = scored[2.0]
    assert fit_constants.leave_match_out_prior(other, totals) == 68.0 / 30


def test_a_league_that_falls_under_the_bar_without_the_match_reads_the_pool() -> None:
    # league 7 has exactly 30 values incl. the scored match: 29 without it
    rows = [{"event": e, "market": "corners_total", "actual": 9.0} for e in range(29)]
    rows.append({"event": 99, "market": "corners_total", "actual": 3.0})
    rows += [{"event": 200 + e, "comp": 8, "market": "corners_total", "actual": 11.0}
             for e in range(40)]
    con = _settled_db(rows)
    totals = fit_constants.baseline_totals(con)
    own = next(dict(r) for r in con.execute(fit_constants.K_CENTRE_ROWS_LOO_SQL)
               if r["own_sum"] == 3.0)
    pooled = (29 * 9.0 + 40 * 11.0) / 69
    assert fit_constants.leave_match_out_prior(own, totals) == pooled


def test_a_two_subject_market_takes_both_of_its_matchs_values_out() -> None:
    rows = []
    for e in range(20):
        rows += [{"event": e, "market": "corners_for", "subject": s, "actual": 5.0}
                 for s in ("1", "2")]
    rows += [{"event": 99, "market": "corners_for", "subject": "1", "actual": 9.0},
             {"event": 99, "market": "corners_for", "subject": "2", "actual": 3.0,
              "line": 3.5}]
    con = _settled_db(rows)
    totals = fit_constants.baseline_totals(con)
    own = [dict(r) for r in con.execute(fit_constants.K_CENTRE_ROWS_LOO_SQL)
           if r["own_sum"] == 12.0]
    assert all(r["own_n"] == 2 for r in own)
    assert len(own) == 2
    assert fit_constants.leave_match_out_prior(own[0], totals) == 5.0


# --- 3: calibrate_from_cache ------------------------------------------------


def _event(
    eid: int, ts: int, home: int, away: int, score: tuple[int, int]
) -> dict[str, Any]:
    return {
        "id": eid, "startTimestamp": ts, "status": {"type": "finished"},
        "homeTeam": {"id": home, "name": f"T{home}"},
        "awayTeam": {"id": away, "name": f"T{away}"},
        "homeScore": {"current": score[0]}, "awayScore": {"current": score[1]},
        "tournament": {"category": {"sport": {"slug": "football"}},
                       "uniqueTournament": {"id": 5}},
    }


def test_a_match_listed_under_two_ids_is_replayed_once(tmp_path: Path) -> None:
    db = tmp_path / "sofa.db"
    con = sqlite3.connect(db)
    con.execute("create table sofa_entity_events (kind text, events_json text)")
    con.execute("""create table sofa_event_stats (sofascore_event_id int,
        statistics_json text, incidents_json text, status_type text)""")
    ts = 1_790_000_000
    copies = [_event(17056234, ts, 1, 2, (2, 1)), _event(17079707, ts, 1, 2, (2, 1))]
    other = [_event(10 + i, ts - 86400 * (i + 1), 1, 3 + i, (1, 1)) for i in range(3)]
    con.execute("insert into sofa_entity_events values ('last', ?)",
                (json.dumps({"events": copies[:1] + other}),))
    con.execute("insert into sofa_entity_events values ('last', ?)",
                (json.dumps({"events": copies[1:]}),))
    con.commit()
    con.close()
    played = calibrate_from_cache.load_cache(db)
    at_ts = [p for p in played if p.timestamp == ts]
    assert [p.event_id for p in at_ts] == [17056234]
    assert len(played) == 4


# --- 2 + 5: ledger ----------------------------------------------------------


def test_the_ledger_records_matches_and_estimated_builders() -> None:
    singles = [
        {"source": {"sofascore_event_id": 1}, "odds": 1.5, "outcome": "WIN"},
        {"source": {"sofascore_event_id": 1}, "odds": 1.8, "outcome": "LOSS"},
        {"source": {"sofascore_event_id": 2}, "odds": 1.6, "outcome": "VOID"},
    ]
    builders = [
        {"source": {"sofascore_event_id": 3}, "odds": 3.0, "outcome": "WIN",
         "odds_measured": False},
        {"source": {"sofascore_event_id": 4}, "odds": 2.5, "outcome": "LOSS",
         "odds_measured": True},
    ]
    sport = [{"superbet_event_id": "9", "odds": 2.0, "outcome": "WIN"}]
    assert record_results.by_match(singles + builders + sport) == {
        "sofa:1": [-0.5, 2], "sofa:3": [2.0, 1], "sofa:4": [-1.0, 1],
        "sb:9": [1.0, 1],
    }
    est = record_results.estimated_builders(builders)
    assert (est["positions"], est["settled"], est["units"]) == (1, 1, 2.0)
    # singles carry no odds_measured and are never "estimated"
    assert record_results.estimated_builders(singles)["positions"] == 0


def test_the_ledger_table_shows_estimated_builder_units() -> None:
    day = {"date": "2026-09-30", "variant": "official",
           "total": {"positions": 2, "settled": 2, "won": 1, "lost": 1, "units": 1.0},
           "builders": {"positions": 1},
           "estimated_builders": {"positions": 1, "settled": 1, "units": 2.0},
           "by_match": {"sofa:1": [-1.0, 1], "sofa:3": [2.0, 1]}}
    old = {**day, "date": "2026-09-29"}
    del old["estimated_builders"]
    del old["by_match"]
    line = next(x for x in audit_ledger.render([day], None)
                if x.startswith("| official"))
    assert "+2.00 in 1" in line and "- (<20 matches)" in line
    line = next(x for x in audit_ledger.render([day, old], None)
                if x.startswith("| official"))
    assert "+? on 1 unrecorded day" in line and "no per-match record" in line


# --- 6: run_settle value_roi ------------------------------------------------


def test_value_roi_counts_a_push_as_neither_a_loss_nor_a_bet() -> None:
    def row(outcome: str) -> SimpleNamespace:
        return SimpleNamespace(verdict="VALUE", offered_odds=2.0, outcome=outcome)

    staked, ret = value_rows_return([row("WIN"), row("LOSS"), row("PUSH")])
    assert len(staked) == 2 and ret == 0.0
