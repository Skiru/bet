"""A CS2 series whose maps carry no round score is graded from its series score
- but only the lines a series score answers (2026-10-01).

Reveal - Huskies and RED Canids Academy - ALKA ended 2-0 on Sofascore with
both games 'finished' and no round score; build_series refused them
(DATA_MISMATCH) and a printed match winner and map handicap stayed pending.
"""

from __future__ import annotations

from typing import Any

from bet.sofa import cs2
from bet.sofa import sport_coupon as sc


def detail(home: int, away: int, status: str = "finished") -> dict[str, Any]:
    return {
        "status": {"type": status},
        "homeScore": {"current": home},
        "awayScore": {"current": away},
    }


def games(n: int) -> list[dict[str, Any]]:
    return [{"id": i, "status": {"type": "finished"}, "homeScore": {}, "awayScore": {}} for i in range(n)]


def test_the_rounds_less_two_nil_is_rebuilt_from_the_series_score() -> None:
    assert cs2.build_series(detail(2, 0), games(2), {}, True) is None, "the old refusal"
    maps = cs2.series_only_maps(detail(2, 0), games(2), True)
    assert maps is not None and len(maps) == 2
    assert all(m.t1_rounds > m.t2_rounds for m in maps)
    flipped = cs2.series_only_maps(detail(2, 0), games(2), False)
    assert flipped is not None and all(m.t2_rounds > m.t1_rounds for m in flipped)


def test_a_score_that_does_not_account_for_the_games_is_refused() -> None:
    assert cs2.series_only_maps(detail(2, 1), games(2), True) is None
    assert cs2.series_only_maps(detail(1, 1), games(2), True) is None, "no winner"
    assert cs2.series_only_maps(detail(2, 0, "inprogress"), games(2), True) is None


def _line(family: str, side: str, line: float | None, map_nr: int = 0) -> cs2.Cs2Line:
    return cs2.Cs2Line("1", family, map_nr, "", line, side, 1.25)


def test_series_families_grade_right_from_the_placeholders() -> None:
    maps = cs2.series_only_maps(detail(2, 0), games(2), True)
    assert maps is not None
    win = _line("match_winner", "T1", None)
    assert cs2.grade(win, cs2.actual_value(win, maps, "A", "B")) == "WIN"  # type: ignore[arg-type]
    # RED Canids Academy - ALKA: T2 at team1's -1.5 is ALKA +1.5, which loses a 2-0
    hcp = _line("maps_handicap", "T2", -1.5)
    assert cs2.grade(hcp, cs2.actual_value(hcp, maps, "A", "B")) == "LOSS"  # type: ignore[arg-type]
    total = _line("maps_total", "OVER", 2.5)
    assert cs2.grade(total, cs2.actual_value(total, maps, "A", "B")) == "LOSS"  # type: ignore[arg-type]


def test_a_coupon_leg_on_rounds_is_never_graded_from_placeholders() -> None:
    ev = {"state": "SETTLED", "series_only": True, "maps": [[1, 0], [1, 0]]}
    base = {"superbet_event_id": "1", "map_nr": 0, "subject": "", "odds": 1.2,
            "team1": "A", "team2": "B"}
    winner = {**base, "family": "match_winner", "line": None, "side": "T1"}
    rounds = {**base, "family": "rounds_total", "line": 40.5, "side": "OVER"}
    on_map = {**base, "family": "map_winner", "map_nr": 1, "line": None, "side": "T1"}
    assert sc._grade_leg("cs2", winner, ev) == "WIN"
    assert sc._grade_leg("cs2", rounds, ev) == "UNGRADEABLE"
    assert sc._grade_leg("cs2", on_map, ev) == "UNGRADEABLE"
