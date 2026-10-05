"""scripts/sofa/measure_model_defects.py - the pieces the F2.2 / F3.2 numbers
rest on, offline."""

from __future__ import annotations

import math

import numpy as np
import pytest

from bet.sofa.comparability import MatchKind
from bet.sofa.engine import nb_survival
from scripts.sofa.measure_model_defects import (
    bench_card_points,
    crossfit_feature,
    missing_counts,
    nb_logpmf,
    nb_variance_case,
    one_hot,
    other_division,
    poisson_glm,
    round_label,
    season_rounds,
    unused_substitutes,
)
from scripts.sofa.measure_sample_composition import Past, Target

DAY = 86400


@pytest.mark.parametrize(("mean", "var"), [(1.3, 1.3), (1.3, 2.4), (4.0, 9.0)])
def test_nb_logpmf_is_the_distribution_nb_survival_prices(
    mean: float, var: float
) -> None:
    pmf = [math.exp(nb_logpmf(y, mean, var)) for y in range(200)]
    assert sum(pmf) == pytest.approx(1.0, abs=1e-9)
    for k in (0, 1, 3):
        survival = nb_survival(mean, var, k)
        assert 1.0 - sum(pmf[: k + 1]) == pytest.approx(survival, abs=1e-9)


def test_nb_variance_case_changes_nothing_when_the_centre_did_not_move() -> None:
    values = [1.0, 0.0, 2.0, 3.0, 1.0, 0.0, 2.0, 1.0, 4.0, 1.0]
    mean = sum(values) / len(values)
    got = nb_variance_case("goals_for", "football", values, 2.0, mean, 15.0, (0.5, 1.5))
    assert got is not None
    raw, scaled, ratio = got
    assert ratio == pytest.approx(1.0)
    assert raw == pytest.approx(scaled)


def test_poisson_glm_recovers_a_multiplicative_effect() -> None:
    rng = np.random.default_rng(1)
    n = 20_000
    lam0 = rng.uniform(0.5, 3.0, n)
    x = rng.integers(0, 2, n).astype(float)
    y = rng.poisson(lam0 * np.exp(0.1 + 0.3 * x)).astype(float)
    beta = poisson_glm(np.column_stack([np.ones(n), x]), y, np.log(lam0))
    assert beta[0] == pytest.approx(0.1, abs=0.03)
    assert beta[1] == pytest.approx(0.3, abs=0.03)


def test_crossfit_credits_a_real_feature_and_not_a_global_bias() -> None:
    rng = np.random.default_rng(2)
    n = 20_000
    ids = np.arange(n)
    lam0 = rng.uniform(0.5, 3.0, n)
    real = rng.integers(0, 2, n).astype(float)
    noise = rng.integers(0, 2, n).astype(float)
    # A global bias of +20% that the intercept alone absorbs ...
    y = rng.poisson(lam0 * 1.2 * np.exp(0.4 * real)).astype(float)
    base, feat, _ = crossfit_feature(lam0, y, real[:, None], ids)
    assert (feat - base).mean() < -0.01
    # ... and a feature with no effect gains nothing out of sample.
    y2 = rng.poisson(lam0 * 1.2).astype(float)
    base2, feat2, _ = crossfit_feature(lam0, y2, noise[:, None], ids)
    assert (feat2 - base2).mean() > -0.0005


def test_one_hot_drops_the_reference() -> None:
    x, names = one_hot(["a", "b", "c", "a"], "a")
    assert names == ["b", "c"]
    assert x.tolist() == [[0, 0], [1, 0], [0, 1], [0, 0]]


def _past(ts: int, comp: int, cat: int, kind: MatchKind = MatchKind.REGULAR) -> Past:
    return Past(ts, ts, comp, None, kind, {"goals": (1.0, 1.0)}, cat)


def test_other_division_flags_a_promoted_side_and_not_a_split_season() -> None:
    season_start = {7: 100 * DAY}
    t = Target(130 * DAY, 999, 10, 7, 1, 2, {"goals": (1.0, 0.0)},
               MatchKind.REGULAR, 5, 55)
    # Promoted: last season in competition 11 of the same country, now in 10.
    promoted = [_past(d * DAY, 11, 55) for d in range(60, 99, 4)]
    current = [_past(d * DAY, 10, 55) for d in (105, 112, 119)]
    history = promoted + current
    sample = list(reversed(history))[:10]
    assert other_division(sample, t, history, season_start)
    # Apertura / Clausura: the side played competition 10 before this season.
    split = [_past(50 * DAY, 10, 55)] + history
    assert not other_division(sample, t, split, season_start)
    # A cup or a continental match is no other division of the country.
    abroad = [_past(d * DAY, 11, 77) for d in range(60, 99, 4)] + current
    assert not other_division(list(reversed(abroad))[:10], t, abroad, season_start)


def test_round_label() -> None:
    rounds = {(10, 7): 34}

    def t(rnd: int | None) -> Target:
        return Target(0, 1, 10, 7, 1, 2, {}, MatchKind.REGULAR, rnd, 55)

    assert round_label(t(2), rounds) == "rounds 1-3"
    assert round_label(t(15), rounds) == "mid season"
    assert round_label(t(29), rounds) == "last 20%"
    assert round_label(t(33), rounds) == "last 2 rounds"
    assert round_label(t(None), rounds) is None
    assert round_label(Target(0, 1, 99, 7, 1, 2, {}), rounds) is None


def test_season_length_comes_from_the_previous_season() -> None:
    # Season 6 ran 34 rounds; season 7 is being played and is at round 12.
    # Its length is last season's, never its own newest round (which would
    # call every league's newest matches "the last two rounds").
    last_season = [Target(r * DAY, r, 10, 6, 1, 2, {}, MatchKind.REGULAR, r, 55)
                   for r in range(1, 35)]
    this_season = [Target((100 + r) * DAY, 100 + r, 10, 7, 1, 2, {},
                          MatchKind.REGULAR, r, 55) for r in range(1, 13)]
    lengths = season_rounds(last_season + this_season)
    assert lengths == {(10, 7): 34}
    assert round_label(this_season[-1], lengths) == "mid season"
    assert round_label(last_season[-1], lengths) is None  # no season before it


def test_bench_cards_are_the_unused_substitutes_only() -> None:
    lineups = {
        "home": {"players": [
            {"player": {"id": 1}, "substitute": False,
             "statistics": {"minutesPlayed": 90}},
            {"player": {"id": 2}, "substitute": True,
             "statistics": {"minutesPlayed": 12}},
            {"player": {"id": 3}, "substitute": True, "statistics": {}},
        ]},
        "away": {"players": [{"player": {"id": 4}, "substitute": True}]},
    }
    bench = unused_substitutes(lineups)
    assert bench == {3, 4}
    incidents = {"incidents": [
        {"incidentType": "card", "incidentClass": "yellow", "player": {"id": 1}},
        {"incidentType": "card", "incidentClass": "yellow", "player": {"id": 3},
         "time": -5},
        {"incidentType": "card", "incidentClass": "red", "player": {"id": 4}},
        {"incidentType": "card", "incidentClass": "yellow", "player": {"id": 4},
         "rescinded": True},
        {"incidentType": "goal", "player": {"id": 3}},
    ]}
    assert bench_card_points(incidents, bench) == 3.0


def test_missing_counts_reads_missing_not_doubtful() -> None:
    lineups = {
        "home": {"missingPlayers": [{"type": "missing"}, {"type": "doubtful"}]},
        "away": {"missingPlayers": []},
    }
    assert missing_counts(lineups) == (1, 0)
    assert missing_counts({"home": {}, "away": {}}) is None
