"""P14 (epochs.TENNIS_RATING_SCORE_WINNER), review R2 #5: a newly admitted
type-0 side may carry no gender; a match with "F" on either side is a
women's match under the switch (it was read as a men's one when only the
away side said "F"). Off: the home side's gender, as before."""

from __future__ import annotations

from typing import Any

from bet.sofa.tennis_rating import parse_event
from tests.sofa.test_audit1023_p14_tennis_rating import _ithaca


def _women(home_gender: Any, away_gender: Any) -> dict[str, Any]:
    return _ithaca(
        winnerCode=1,
        homeTeam={"id": 1, "name": "A Player", "type": 0, "gender": home_gender,
                  "national": False},
        awayTeam={"id": 2, "name": "B Player", "type": 1, "gender": away_gender,
                  "national": False})


def test_the_away_sides_f_makes_it_a_womens_match_under_the_switch() -> None:
    r = parse_event(_women(None, "F"), score_winner=True)
    assert r is not None and r.female


def test_off_the_home_side_decides_as_before() -> None:
    ev = _women(None, "F")
    ev["homeTeam"]["type"] = 1  # a player the old rule admits too
    r = parse_event(ev)
    assert r is not None and not r.female
    ev["homeTeam"]["gender"] = "F"
    r = parse_event(ev)
    assert r is not None and r.female


def test_men_stay_men() -> None:
    r = parse_event(_women("M", "M"), score_winner=True)
    assert r is not None and not r.female
