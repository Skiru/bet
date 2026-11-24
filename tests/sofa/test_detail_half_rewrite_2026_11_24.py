"""Sofascore's after-the-match half rewrite (2026-11-24).

Albania U21 - Andorra U21 (16435127) of 2026-11-20 was graded on period1 3-1
(goals 2', 11', 45', 45'); the resettle sweep re-fetched /event on 11-22 as
period1 0-0, period2 4-2 with the incidents' HT marker 0-0 too, the cache
replaced the good payload, and the regrade flipped 32 correct half rows. The
goal incidents are the second witness (metrics.goal_incidents_half_time), the
cache keeps a finished score a re-fetch degrades (detail_guard), and
repair_half_regrades.py finds the rows already flipped.
"""

from __future__ import annotations

import copy
import json
import sqlite3
from pathlib import Path
from typing import Any

from bet.sofa.cache import SofaCache
from bet.sofa.config import SofaConfig
from bet.sofa.detail_guard import (
    HALF_CONTRADICTS_GOALS,
    HALF_ZEROED,
    LOST_SCORE_FIELDS,
    guard_scores,
)
from bet.sofa.football_sim_markets import sim_value
from bet.sofa.metrics import goal_incidents_half_time, half_time_disagrees
from scripts.sofa import repair_half_regrades as repair


def _goal(
    minute: int, home: int, away: int, added: int | None = None
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "incidentType": "goal",
        "time": minute,
        "homeScore": home,
        "awayScore": away,
    }
    if added is not None:
        out["addedTime"] = added
    return out


def _event(
    p1: tuple[int, int] | None, full: tuple[int, int] = (4, 2)
) -> dict[str, Any]:
    home: dict[str, Any] = {
        "current": full[0],
        "display": full[0],
        "normaltime": full[0],
    }
    away: dict[str, Any] = {
        "current": full[1],
        "display": full[1],
        "normaltime": full[1],
    }
    if p1 is not None:
        home.update(period1=p1[0], period2=full[0] - p1[0])
        away.update(period1=p1[1], period2=full[1] - p1[1])
    return {
        "id": 16435127,
        "status": {"code": 100, "type": "finished"},
        "tournament": {"category": {"sport": {"slug": "football"}}},
        "homeScore": home,
        "awayScore": away,
    }


def _incidents(ht: tuple[int, int]) -> dict[str, Any]:
    # newest first, as Sofascore lists them; the two 45' goals share a minute
    return {
        "incidents": [
            {"incidentType": "period", "text": "FT", "homeScore": 4, "awayScore": 2},
            _goal(83, 4, 2),
            _goal(77, 3, 2),
            {
                "incidentType": "period",
                "text": "HT",
                "homeScore": ht[0],
                "awayScore": ht[1],
            },
            _goal(45, 2, 1),
            _goal(45, 3, 1),
            _goal(11, 1, 1),
            _goal(2, 0, 1),
        ]
    }


GOOD = _event((3, 1))
REWRITTEN = _event((0, 0))
GOOD_INC = _incidents((3, 1))
REWRITTEN_INC = _incidents((0, 0))


def test_goals_give_the_first_half() -> None:
    assert goal_incidents_half_time(GOOD, GOOD_INC) == (3, 1)
    assert goal_incidents_half_time(REWRITTEN, REWRITTEN_INC) == (3, 1)
    stoppage = {"incidents": [_goal(45, 1, 0, added=3), _goal(46, 1, 1)]}
    assert goal_incidents_half_time(_event((1, 0), (1, 1)), stoppage) == (1, 0)
    assert goal_incidents_half_time(_event((0, 0), (0, 0)), {"incidents": []}) == (0, 0)


def test_goals_that_are_no_reading_give_none() -> None:
    no_minute = {
        "incidents": [{"incidentType": "goal", "homeScore": 1, "awayScore": 0}]
    }
    assert goal_incidents_half_time(_event((1, 0), (1, 0)), no_minute) is None
    # a goal missing from the list: its last running score is not the score
    partial = {"incidents": [_goal(35, 0, 1)]}
    assert goal_incidents_half_time(_event((0, 2), (1, 3)), partial) is None
    # an extra-time goal is not regular time's
    extra = {"incidents": [_goal(20, 1, 0), _goal(105, 2, 0)]}
    event = _event((1, 0), (1, 0))
    event["status"] = {"code": 110, "type": "finished"}
    event["homeScore"]["current"] = 2
    assert goal_incidents_half_time(event, extra) == (1, 0)


def test_a_zeroed_half_is_refused_when_the_marker_is_zeroed_too() -> None:
    assert half_time_disagrees(REWRITTEN, REWRITTEN_INC)
    assert (
        sim_value("result_1h", "1", REWRITTEN, REWRITTEN_INC) == "HALF_TIME_DISAGREES"
    )
    assert not half_time_disagrees(GOOD, GOOD_INC)
    assert sim_value("result_1h", "1", GOOD, GOOD_INC) == 1.0
    # the marker alone still refuses when the goals are no reading
    marker_only = {
        "incidents": [
            {"incidentType": "period", "text": "HT", "homeScore": 1, "awayScore": 0}
        ]
    }
    assert half_time_disagrees(_event((0, 0), (1, 0)), marker_only)


def test_a_rewritten_refetch_keeps_the_old_score() -> None:
    new = copy.deepcopy({"event": REWRITTEN, "referee": "kept from the new one"})
    stored, reason = guard_scores({"event": GOOD}, new, GOOD_INC)
    assert reason == HALF_CONTRADICTS_GOALS
    assert stored["event"]["homeScore"]["period1"] == 3
    assert stored["event"]["awayScore"]["period1"] == 1
    assert stored["referee"] == "kept from the new one"
    assert stored["score_guard"]["refused"]["homeScore"]["period1"] == 0
    assert new["event"]["homeScore"]["period1"] == 0  # the argument untouched
    # no incidents cached: the rewrite's signature against a consistent score
    assert guard_scores({"event": GOOD}, {"event": REWRITTEN}, None)[1] == HALF_ZEROED


def test_a_lost_half_keeps_the_old_score() -> None:
    stored, reason = guard_scores({"event": GOOD}, {"event": _event(None)}, None)
    assert reason == LOST_SCORE_FIELDS
    assert stored["event"]["homeScore"]["period1"] == 3


def test_a_correction_or_a_better_payload_is_taken() -> None:
    # the old payload was the rewritten one: the good re-fetch replaces it
    new = {"event": GOOD}
    assert guard_scores({"event": REWRITTEN}, new, GOOD_INC) == (new, None)
    # the match's own score changed: Sofascore's correction, taken whole
    corrected = {"event": _event((0, 0), (4, 3))}
    assert guard_scores({"event": GOOD}, corrected, GOOD_INC) == (corrected, None)
    # a half the goals confirm replaces an old one they contradict
    other = {"event": _event((2, 1))}
    assert guard_scores({"event": other["event"]}, {"event": GOOD}, GOOD_INC)[1] is None
    # an unfinished payload is never judged
    live = copy.deepcopy(REWRITTEN)
    live["status"] = {"code": 7, "type": "inprogress"}
    assert guard_scores({"event": GOOD}, {"event": live}, GOOD_INC)[1] is None


def _cache(tmp_path: Path) -> SofaCache:
    return SofaCache(
        SofaConfig(db_path=str(tmp_path / "sofa.db"), runs_dir=str(tmp_path))
    )


def test_the_cache_never_degrades_a_finished_score(tmp_path: Path) -> None:
    cache = _cache(tmp_path)
    cache.save_event_detail(16435127, {"event": GOOD}, "finished")
    cache.save_event_stats(16435127, {}, GOOD_INC, "finished")
    stored = cache.save_event_detail(16435127, {"event": REWRITTEN}, "finished")
    assert stored["score_guard"]["reason"] == HALF_CONTRADICTS_GOALS
    cached = cache.get_event_detail(16435127)
    assert cached is not None
    assert cached["event"]["homeScore"]["period1"] == 3
    # a first save is stored as given
    assert cache.save_event_detail(1, {"event": REWRITTEN}, "finished") == {
        "event": REWRITTEN
    }


def _settled_db(tmp_path: Path) -> sqlite3.Connection:
    cache = _cache(tmp_path)
    cache.save_event_detail(16435127, {"event": REWRITTEN}, "finished")
    cache.save_event_stats(16435127, {}, REWRITTEN_INC, "finished")
    conn = sqlite3.connect(str(tmp_path / "sofa.db"))
    rows = [  # (id, market, subject, line, direction, actual, outcome)
        (1, "result_1h", "1", 0.5, "OVER", 0.0, "LOSS"),  # flipped off the rewrite
        (2, "result_1h", "X", 0.5, "OVER", 1.0, "WIN"),  # flipped off the rewrite
        (3, "goals_total", "", 5.5, "OVER", 6.0, "WIN"),  # not a half market
    ]
    for rid, market, subject, line, direction, actual, outcome in rows:
        conn.execute(
            "INSERT INTO sofa_settled_row (id, run_date, sofascore_event_id, sport,"
            " competition_id, market, subject, line, direction, sample_size,"
            " sample_mean, sample_sd, p_central, p_bar, market_p, actual_value,"
            " outcome, settled_at, ladder_sigma, offered_odds, verdict)"
            " VALUES (?, '2026-11-20', 16435127, 'football', NULL, ?, ?, ?, ?, 10,"
            " 1.0, 1.0, 0.5, 0.5, NULL, ?, ?, '2026-11-22T05:54:31+00:00', NULL,"
            " 1.5, 'OK')",
            (rid, market, subject, line, direction, actual, outcome),
        )
    conn.commit()
    log = [
        {
            "id": 1,
            "run_date": "2026-11-20",
            "event_id": 16435127,
            "market": "result_1h",
            "subject": "1",
            "line": 0.5,
            "direction": "OVER",
            "old_actual": 1.0,
            "new_actual": 0.0,
            "old_outcome": "WIN",
            "new_outcome": "LOSS",
        },
        {
            "id": 2,
            "run_date": "2026-11-20",
            "event_id": 16435127,
            "market": "result_1h",
            "subject": "X",
            "line": 0.5,
            "direction": "OVER",
            "old_actual": 0.0,
            "new_actual": 1.0,
            "old_outcome": "LOSS",
            "new_outcome": "WIN",
        },
        {
            "id": 3,
            "run_date": "2026-11-20",
            "event_id": 16435127,
            "market": "goals_total",
            "subject": "",
            "line": 5.5,
            "direction": "OVER",
            "old_actual": 5.0,
            "new_actual": 6.0,
            "old_outcome": "LOSS",
            "new_outcome": "WIN",
        },
    ]
    (tmp_path / "regrade_20261122T055431Z.json").write_text(json.dumps(log))
    return conn


def test_repair_restores_only_flips_made_off_the_rewrite(tmp_path: Path) -> None:
    conn = _settled_db(tmp_path)
    restores, tally = repair.plan(conn, tmp_path)
    assert {(r["id"], r["new_actual"], r["new_outcome"]) for r in restores} == {
        (1, 1.0, "WIN"),
        (2, 0.0, "LOSS"),
    }
    assert tally["restore"] == 2
    assert tally["not_half_market"] == 1
    # dry run: nothing written
    assert conn.execute(
        "SELECT outcome FROM sofa_settled_row WHERE id = 1"
    ).fetchone() == ("LOSS",)
