"""scripts/sofa/measure_tennis_outcome_model.py - offline checks of the pure
parts: smoothing, the i.i.d.-set reading, score codes, the neighbour's match
winner, team cups, the base-rate counter and the vectorised logistic fit."""

import numpy as np
import pytest

from bet.sofa import tennis_rating as tr
from scripts.sofa import measure_tennis_outcome_model as m


def test_smoothed_is_never_zero_or_one() -> None:
    assert m.smoothed(0, 600, 2) == pytest.approx(0.5 / 601)
    assert 0 < m.smoothed(600, 600, 4) < 1


@pytest.mark.parametrize("p", [0.05, 0.3, 0.5, 0.77, 0.98])
def test_iid_scores_invert_the_match_probability(p: float) -> None:
    s = m.set_prob_from_match(p)
    assert s * s * (3 - 2 * s) == pytest.approx(p, abs=1e-9)
    sc = m.iid_scores(p)
    assert sum(sc) == pytest.approx(1.0)
    assert sc[0] + sc[1] == pytest.approx(p, abs=1e-9)


def test_score_code_reads_the_home_side() -> None:
    assert m.score_code([(6, 3), (6, 4)]) == 0
    assert m.score_code([(3, 6), (6, 4), (1, 0)]) == 1  # match tiebreak
    assert m.score_code([(6, 3), (4, 6), (2, 6)]) == 2
    assert m.score_code([(3, 6), (4, 6)]) == 3


def _o(sets: list[tuple[int, int]]) -> tr.Outcome:
    gf = sum(a for a, _ in sets)
    ga = sum(b for _, b in sets)
    return tr.Outcome(0.6, gf, ga, len(sets), 0, sets[0], sets[1])


def test_won_match_reads_the_third_set() -> None:
    assert m._won_match(_o([(6, 3), (6, 4)]))
    assert not m._won_match(_o([(3, 6), (4, 6)]))
    # more games overall, lost the decider
    assert not m._won_match(_o([(6, 0), (3, 6), (6, 7)]))
    assert m._won_match(_o([(2, 6), (6, 4), (1, 0)]))


def test_team_cups_are_named() -> None:
    assert m.is_team_cup("Davis Cup | Davis Cup, World Group I | Davis Cup")
    assert not m.is_team_cup("ITF Men | M15 Monastir | ITF Monastir")


def test_base_rates_count_as_of() -> None:
    b = m.BaseRates()
    b.add(True, True, 0)
    b.add(False, True, 2)
    r = b.rates()
    assert r["match_winner"] == pytest.approx(1.5 / 3)
    assert r["set1_winner"] == pytest.approx(2.5 / 3)
    assert r["deciding_set"] == pytest.approx(1.5 / 3)
    assert r["set_score"] == pytest.approx([1.5 / 4, 0.5 / 4, 1.5 / 4, 0.5 / 4])


def test_favoured_and_buckets() -> None:
    p = np.array([0.2, 0.8, 0.75])
    y = np.array([0.0, 1.0, 0.0])
    pf, yf = m.favoured(p, y)
    assert list(pf) == pytest.approx([0.8, 0.8, 0.75])
    assert list(yf) == [1.0, 1.0, 0.0]
    rows = m.bucket_table(pf, yf, m.BIN_EDGES)
    assert sum(r["n"] for r in rows) == 3


def test_numpy_logistic_matches_the_rating_fit() -> None:
    rng = np.random.default_rng(3)
    x = rng.normal(size=(400, 2))
    y = (rng.random(400) < 1 / (1 + np.exp(-(0.3 + x @ [1.0, -0.5])))).astype(float)
    ours = m.fit_logistic_np(x, y)
    theirs = tr.fit_logistic(x.tolist(), y.tolist())
    assert ours == pytest.approx(theirs, abs=1e-6)
