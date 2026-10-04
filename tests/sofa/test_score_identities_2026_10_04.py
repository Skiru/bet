"""A score that contradicts itself is no count (review 2026-10-04).

Both payloads are verbatim from the cache. SETTLE and the cache replay read
extract_metric without check_identities, so the contradiction reached
sofa_settled_row: Buxton - South Shields graded goals_2h_total 0.5 OVER a
loss (incidents: away goals at 7' and 64'), and Shang - Mannarino graded
games_total 19 on a 6-7(9) 2-6 match, flipping eight rows.
"""

from __future__ import annotations

from typing import Any

from bet.sofa.contracts import GapReason
from bet.sofa.metrics import extract_metric, goal_score_inconsistent

FINISHED = {"code": 100, "description": "Ended", "type": "finished"}

BUXTON: dict[str, Any] = {  # 17160371, 2026-10-03
    "id": 17160371, "status": FINISHED,
    "homeScore": {"current": 0, "display": 0, "period1": 0, "period2": 0,
                  "normaltime": 0},
    "awayScore": {"current": 2, "display": 2, "period1": 1, "period2": 0,
                  "normaltime": 1},
}

SHANG_MANNARINO: dict[str, Any] = {  # 17149657, 2026-09-24
    "id": 17149657, "status": FINISHED,
    "homeScore": {"current": 0, "display": 0, "period1": 6, "period2": 2,
                  "period1TieBreak": 9, "point": "15", "normaltime": 0},
    "awayScore": {"current": 2, "display": 2, "period1": 7, "period2": 6,
                  "period1TieBreak": 11, "point": "40", "normaltime": 2},
}
GAMES_WON = {"ALL": {"gamesWon": (8.0, 11.0)}}


def test_an_away_side_score_that_does_not_add_up_is_refused() -> None:
    assert goal_score_inconsistent(BUXTON)
    for metric in ("goals_total", "goals_2h_total", "goals_1h_total"):
        got = extract_metric(metric, "football", {}, None, BUXTON, True)
        assert got == GapReason.INTERNAL_INCONSISTENT, metric
    got = extract_metric("goals_2h_for", "football", {}, None, BUXTON, False)
    assert got == GapReason.INTERNAL_INCONSISTENT


def test_a_consistent_score_still_counts() -> None:
    event = {
        "status": FINISHED,
        "homeScore": {"current": 2, "period1": 1, "period2": 1, "normaltime": 2},
        "awayScore": {"current": 1, "period1": 0, "period2": 1, "normaltime": 1},
    }
    assert not goal_score_inconsistent(event)
    assert extract_metric("goals_total", "football", {}, None, event, True) == 3.0
    assert extract_metric("goals_2h_for", "football", {}, None, event, False) == 1.0


def test_extra_time_reads_normaltime_and_is_not_inconsistent() -> None:
    event = {  # 1-1 at 90, 2-1 after extra time
        "status": {"code": 110, "type": "finished"},
        "homeScore": {"current": 2, "period1": 1, "period2": 0, "normaltime": 1},
        "awayScore": {"current": 1, "period1": 0, "period2": 1, "normaltime": 1},
    }
    assert not goal_score_inconsistent(event)
    assert extract_metric("goals_total", "football", {}, None, event, True) == 2.0


def test_games_come_from_the_set_score_when_games_won_contradicts_it() -> None:
    total = extract_metric("games_total", "tennis", GAMES_WON, None,
                           SHANG_MANNARINO, True)
    assert total == 21.0
    mannarino = extract_metric("games_won_for", "tennis", GAMES_WON, None,
                               SHANG_MANNARINO, False)
    assert mannarino == 13.0


def test_games_won_is_still_read_when_the_sets_are_unreadable() -> None:
    event = {"status": FINISHED, "homeScore": {}, "awayScore": {}}
    got = extract_metric("games_total", "tennis", {"ALL": {"gamesWon": (12.0, 7.0)}},
                         None, event, True)
    assert got == 19.0
