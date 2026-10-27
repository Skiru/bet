"""Review 2026-10-27 R4: a CS2 map played only from a level series (Bo3 map 3
at 1-1, Bo5 maps 4-5) is priced with the series Beta's posterior given the
states reaching it (epochs.CS2_DECIDER_MAP_POSTERIOR_FROM_UTC); off = the old
plain map p, byte for byte."""

import math

import pytest

from bet.sofa import cs2_engine as eng
from bet.sofa.cs2 import Cs2Line

K = eng.SERIES_KAPPA


def _model(p: float) -> eng.RatingModel:
    """Two rated teams at equal Elo whose calibrated home p is exactly `p`."""
    book = eng.EloBook()
    for _ in range(eng.MIN_MAPS_RATED + 2):
        book.update(1, 2)
        book.update(2, 1)
    return eng.RatingModel(book, a=math.log(p / (1.0 - p)), b=0.0, n_fit=500)


def _line(family: str, map_nr: int, side: str = "T1",
          line: float | None = None, subject: str = "") -> Cs2Line:
    return Cs2Line("sb", family, map_nr, subject, line, side, 1.5)


def _p(line: Cs2Line, best_of: int, on: bool, p: float = 0.75) -> float:
    if on:
        mp = eng.model_probability(line, 1, 2, "A", "B", best_of, [], _model(p),
                                   True, team_rounds_race=True,
                                   decider_posterior=True)
    else:  # the old call, without the keyword
        mp = eng.model_probability(line, 1, 2, "A", "B", best_of, [], _model(p),
                                   True, team_rounds_race=True)
    assert mp is not None
    return mp.p


def test_posterior_closed_forms() -> None:
    p = 0.75
    assert eng.decider_posterior_p(p, 3, 3) == pytest.approx((p * K + 1) / (K + 2))
    assert eng.decider_posterior_p(p, 3, 3) == pytest.approx(0.6875)
    # Bo5 map 4 (2-1 / 1-2 mixed) collapses to the same (pK+1)/(K+2)
    assert eng.decider_posterior_p(p, 5, 4) == pytest.approx((p * K + 1) / (K + 2))
    assert eng.decider_posterior_p(p, 5, 5) == pytest.approx((p * K + 2) / (K + 4))
    # maps always played keep p exactly
    for bo, nr in ((1, 1), (2, 1), (2, 2), (3, 1), (3, 2), (5, 1), (5, 2), (5, 3)):
        assert eng.decider_posterior_p(p, bo, nr) == p
    assert eng.decider_posterior_p(p, None, 3) == p


def test_posterior_matches_series_distribution_mixed() -> None:
    """P(map 3 played and team1 wins it) from the mixed series: the 2-1
    scores reached from 1-1 (orders W L W, L W W) are half of (2, 1)."""
    p = 0.62
    d = eng.series_distribution_mixed(p, 3)
    reach = d[(2, 1)] + d[(1, 2)]
    assert eng.decider_posterior_p(p, 3, 3) == pytest.approx(d[(2, 1)] / reach)
    d5 = eng.series_distribution_mixed(p, 5)
    assert eng.decider_posterior_p(p, 5, 5) == pytest.approx(
        d5[(3, 2)] / (d5[(3, 2)] + d5[(2, 3)]))


def test_map_winner_bo3_map3_on_and_off() -> None:
    assert _p(_line("map_winner", 3), 3, True) == pytest.approx(0.6875)
    assert _p(_line("map_winner", 3, "T2"), 3, True) == pytest.approx(0.3125)
    assert _p(_line("map_winner", 1), 3, True) == pytest.approx(0.75)
    assert _p(_line("map_winner", 3), 3, False) == pytest.approx(0.75)
    assert _p(_line("map_winner", 5), 5, True) == pytest.approx(
        (0.75 * K + 2) / (K + 4))


def test_map_level_families_read_the_posterior() -> None:
    """Round race and round handicap on map 3 equal the map-1 number priced
    at the posterior p; maps 1-2 unchanged by the switch."""
    post = (0.75 * K + 1) / (K + 2)
    for fam, side, ln, subj in (("map_team_rounds", "OVER", 10.5, "A"),
                                ("map_rounds_handicap", "T1", -3.5, "")):
        on3 = _p(_line(fam, 3, side, ln, subj), 3, True)
        at_post = _p(_line(fam, 1, side, ln, subj), 3, False, p=post)
        assert on3 == pytest.approx(at_post, abs=2e-3)  # race p rounded to 3 dp
        assert on3 != _p(_line(fam, 3, side, ln, subj), 3, False)
        for nr in (1, 2):
            assert (_p(_line(fam, nr, side, ln, subj), 3, True)
                    == _p(_line(fam, nr, side, ln, subj), 3, False))


def test_switch_off_is_the_old_call() -> None:
    for fam, nr, side, ln, subj in (("map_winner", 3, "T1", None, ""),
                                    ("map_team_rounds", 3, "UNDER", 9.5, "B"),
                                    ("map_rounds_handicap", 3, "T2", 2.5, "")):
        line = _line(fam, nr, side, ln, subj)
        old = eng.model_probability(line, 1, 2, "A", "B", 3, [], _model(0.75),
                                    True, team_rounds_race=True)
        new = eng.model_probability(line, 1, 2, "A", "B", 3, [], _model(0.75),
                                    True, team_rounds_race=True,
                                    decider_posterior=False)
        assert old == new


def test_series_families_untouched() -> None:
    line = _line("maps_total", 0, "OVER", 2.5)
    assert _p(line, 3, True) == _p(line, 3, False)
