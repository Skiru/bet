"""A football match that went from 90 minutes straight to penalties is graded
on its statistics by SETTLE (2026-10-12).

Sofascore code 120 (AP) was read as "120 minutes" for every non-goal count,
so the printed EFL Trophy corner legs of 2026-10-06 (group games: a draw goes
straight to a shootout) sat EVENT_NOT_FINISHED for good. The payloads below
are the cached ones of events 16801916 (Accrington - Salford) and an extra
time cup tie; samples and ratings keep refusing both (no `settling`).
"""

from __future__ import annotations

from typing import Any

import pytest

from bet.sofa.contracts import GapReason
from bet.sofa.metrics import extract_metric, played_extra_time, regulation_score

# Event 16801916, sofa_event_detail as cached.
SHOOTOUT_ONLY: dict[str, Any] = {
    "status": {"code": 120, "description": "AP", "type": "finished"},
    "homeScore": {"current": 6, "display": 1, "period1": 0, "period2": 1,
                  "normaltime": 1, "penalties": 5},
    "awayScore": {"current": 5, "display": 1, "period1": 0, "period2": 1,
                  "normaltime": 1, "penalties": 4},
}
# Extra time played, then penalties (shape of the 24 such cached events).
WITH_EXTRA_TIME: dict[str, Any] = {
    "status": {"code": 120, "description": "AP", "type": "finished"},
    "homeScore": {"current": 6, "display": 2, "period1": 1, "period2": 0,
                  "normaltime": 1, "extra1": 1, "extra2": 0, "overtime": 1,
                  "penalties": 4},
    "awayScore": {"current": 5, "display": 2, "period1": 0, "period2": 1,
                  "normaltime": 1, "extra1": 0, "extra2": 1, "overtime": 1,
                  "penalties": 3},
}
FLAT = {"ALL": {"cornerKicks": (7.0, 4.0), "fouls": (11.0, 9.0)},
        "1ST": {"cornerKicks": (3.0, 2.0)}}


def test_played_extra_time() -> None:
    assert not played_extra_time(SHOOTOUT_ONLY)
    assert played_extra_time(WITH_EXTRA_TIME)
    assert played_extra_time({"status": {"code": 110}, "homeScore": {},
                              "awayScore": {}})
    assert not played_extra_time({"status": {"code": 100}})
    # A score that does not add up to normaltime + penalties: not provably 90'.
    odd = {**SHOOTOUT_ONLY, "homeScore": {**SHOOTOUT_ONLY["homeScore"], "current": 7}}
    assert played_extra_time(odd)


def test_settling_grades_corners_of_a_shootout_after_90_minutes() -> None:
    assert extract_metric("corners_total", "football", FLAT, None, SHOOTOUT_ONLY,
                          True, settling=True) == 11.0
    assert extract_metric("corners_for", "football", FLAT, None, SHOOTOUT_ONLY,
                          False, settling=True) == 4.0


def test_samples_still_refuse_a_shootout_match() -> None:
    assert extract_metric("corners_total", "football", FLAT, None, SHOOTOUT_ONLY,
                          True) is GapReason.EVENT_NOT_FINISHED


def test_settling_still_refuses_counts_after_extra_time() -> None:
    assert extract_metric("corners_total", "football", FLAT, None, WITH_EXTRA_TIME,
                          True, settling=True) is GapReason.EVENT_NOT_FINISHED


@pytest.mark.parametrize("event", [SHOOTOUT_ONLY, WITH_EXTRA_TIME])
@pytest.mark.parametrize("settling", [True, False])
def test_goals_are_the_90_minute_score_never_the_shootout(
    event: dict[str, Any], settling: bool
) -> None:
    assert regulation_score(event) == (1.0, 1.0)
    assert extract_metric("goals_total", "football", FLAT, None, event, True,
                          settling=settling) == 2.0
    assert extract_metric("goals_for", "football", FLAT, None, event, True,
                          settling=settling) == 1.0
