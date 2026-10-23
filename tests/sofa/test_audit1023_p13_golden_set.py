"""Audit 2026-10-23 B13 / P13: a volleyball match followed by a golden set
(Sofascore "AET" / "AGS").

Superbet settles on the match (Regulamin 5.D.3.a: the official result is the
one on court in the regulation playing time); the golden set decides the
two-legged tie and is kept by Sofascore under `overtime`, never in a period.
Settlement (shadow.event_state / build_result) is a correctness fix, live at
once; the score-model history reads such a match only from
epochs.VB_GOLDEN_SET_FROM_UTC (score_model.parse_event golden_set).
"""

from __future__ import annotations

import copy
from datetime import UTC, datetime, timedelta
from typing import Any

from bet.sofa import epochs
from bet.sofa.score_model import VOLLEYBALL_METRIC, parse_event
from bet.sofa.shadow import (
    SPORTS,
    ShadowLine,
    actual_value,
    build_result,
    event_state,
    grade,
)

VB = SPORTS["volleyball"]

# 12193496 (A1 Women playoffs): the home side won the match 3-1, the away side
# the golden set 18-16 and the tie - and winnerCode names the tie's winner.
TIE_WINNER_CODE: dict[str, Any] = {
    "id": 12193496, "startTimestamp": 1_700_000_000, "winnerCode": 2,
    "status": {"code": 130, "description": "AGS", "type": "finished"},
    "tournament": {"id": 1, "category": {"sport": {"slug": "volleyball"}},
                   "uniqueTournament": {"id": 77}},
    "homeTeam": {"id": 1, "name": "H"}, "awayTeam": {"id": 2, "name": "A"},
    "homeScore": {"current": 3, "period1": 18, "period2": 25, "period3": 25,
                  "period4": 25, "normaltime": 3, "overtime": 16,
                  "aggregated": 4},
    "awayScore": {"current": 1, "period1": 25, "period2": 23, "period3": 13,
                  "period4": 23, "normaltime": 1, "overtime": 18,
                  "aggregated": 4},
}
# 15999857 Belluno - Altotevere (Serie A3 playoffs): 3-2, winnerCode 1.
BELLUNO: dict[str, Any] = {
    "id": 15999857, "startTimestamp": 1_700_000_000, "winnerCode": 1,
    "status": {"code": 130, "description": "AGS", "type": "finished"},
    "tournament": {"id": 1, "category": {"sport": {"slug": "volleyball"}},
                   "uniqueTournament": {"id": 78}},
    "homeTeam": {"id": 3, "name": "Belluno"},
    "awayTeam": {"id": 4, "name": "Altotevere"},
    "homeScore": {"current": 3, "period1": 25, "period2": 25, "period3": 20,
                  "period4": 24, "period5": 15, "overtime": 15},
    "awayScore": {"current": 2, "period1": 23, "period2": 16, "period3": 25,
                  "period4": 26, "period5": 13, "overtime": 13},
}

KO = datetime(2026, 10, 20, 18, tzinfo=UTC)


def _line(market_id: int, side: str, line: float | None) -> ShadowLine:
    return ShadowLine("1", market_id, "x", 0, "", line, side, 1.9)


def test_a_golden_set_match_is_finished() -> None:
    for ev in (TIE_WINNER_CODE, BELLUNO):
        assert event_state(ev, VB, KO, KO + timedelta(hours=5)) == "FINISHED"
    # AET is the same story
    aet = copy.deepcopy(BELLUNO)
    aet["status"]["description"] = "AET"
    assert event_state(aet, VB, KO, KO + timedelta(hours=5)) == "FINISHED"


def test_the_winner_is_the_matchs_not_the_ties() -> None:
    # Before the fix: winnerCode 2 against sets 3-1 refused the whole game.
    r = build_result(TIE_WINNER_CODE, VB, True, allow_final_only=True)
    assert r is not None
    assert r.winner == "T1" and (r.t1_full, r.t2_full) == (3, 1)
    # the golden set (overtime 16-18) is in no quantity: total points are the
    # four sets' 93 + 84
    assert r.t1_periods == (18, 25, 25, 25) and r.t2_periods == (25, 23, 13, 23)
    winner = _line(745, "T1", None)
    assert grade(winner, actual_value(winner, r, VB), False) == "WIN"
    total = _line(230060, "OVER", 176.5)
    assert actual_value(total, r, VB) == 93 + 84
    sets = _line(230058, "OVER", 3.5)
    assert actual_value(sets, r, VB) == 4
    exact = _line(785, "3:1", None)
    assert grade(exact, actual_value(exact, r, VB), False) == "WIN"
    # Seen from the away side as team1 the same match is a loss for T1.
    flipped = build_result(TIE_WINNER_CODE, VB, False, allow_final_only=True)
    assert flipped is not None and flipped.winner == "T2"


def test_belluno_grades_on_its_five_sets() -> None:
    r = build_result(BELLUNO, VB, True, allow_final_only=True)
    assert r is not None and r.winner == "T1" and len(r.t1_periods) == 5
    assert sum(r.t1_periods) + sum(r.t2_periods) == 109 + 103


def test_an_unfinished_or_inconsistent_golden_set_match_is_refused() -> None:
    short = copy.deepcopy(TIE_WINNER_CODE)
    for side in ("homeScore", "awayScore"):
        del short[side]["period4"]
    short["homeScore"]["current"] = 2
    assert build_result(short, VB, True, allow_final_only=True) is None
    # like 15670573 (sets 3-0 beside current 3-1): sets 4-0 beside 3-1
    bad = copy.deepcopy(TIE_WINNER_CODE)
    bad["homeScore"].update(period1=27)
    assert build_result(bad, VB, True, allow_final_only=True) is None


def test_an_ended_match_still_reads_winner_code() -> None:
    ended = copy.deepcopy(TIE_WINNER_CODE)
    ended["status"]["description"] = "Ended"
    # unchanged rule: a winnerCode against the sets is a mismatch
    assert build_result(ended, VB, True, allow_final_only=True) is None


def test_hockey_aet_is_untouched() -> None:
    assert "AET" in SPORTS["hockey"].finished_descriptions
    assert SPORTS["hockey"].golden_set_descriptions == frozenset()


def test_model_reads_it_only_under_the_switch() -> None:
    assert parse_event(TIE_WINNER_CODE, VB) is None
    r = parse_event(TIE_WINNER_CODE, VB, golden_set=True)
    assert r is not None
    assert r.values[VOLLEYBALL_METRIC] == ((18 + 25 + 25 + 25) / 4,
                                          (25 + 23 + 13 + 23) / 4)
    short = copy.deepcopy(TIE_WINNER_CODE)
    for side in ("homeScore", "awayScore"):
        del short[side]["period4"]
    assert parse_event(short, VB, golden_set=True) is None


def test_the_switch_by_day_and_build_clock() -> None:
    on = datetime(2026, 10, 24, 0, 0, 0, tzinfo=UTC)
    assert epochs.VB_GOLDEN_SET_FROM_UTC == on
    assert not epochs.vb_golden_set("2026-10-23", on)
    assert not epochs.vb_golden_set("2026-10-24", on - timedelta(minutes=1))
    assert epochs.vb_golden_set("2026-10-24", on)


def test_model_refuses_sets_that_disagree_with_current() -> None:
    bad = copy.deepcopy(TIE_WINNER_CODE)
    bad["homeScore"].update(period1=27)  # sets 4-0 beside current 3-1
    assert parse_event(bad, VB, golden_set=True) is None
