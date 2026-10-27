"""Confidence review 2026-10-27 R3: hockey's late (empty-net) goal is part of
the third period's mean, never added on top of it
(epochs.HK_LATE_GOAL_IN_MEAN_FROM_UTC, score_model.late_goal_mass)."""

from __future__ import annotations

import dataclasses
import random
from datetime import UTC, datetime

import pytest

from bet.sofa import epochs, timeutil
from bet.sofa import score_model as sm
from bet.sofa.football_rating import RatingBook
from bet.sofa.shadow import SPORTS

MU1 = [0.9, 1.0, 1.05]
MU2 = [0.85, 0.95, 1.0]
N = 100_000


def _means(prm: sm.SimParams, seed: int = 7) -> tuple[float, float]:
    rng = random.Random(seed)
    games = [sm._hockey(rng, MU1, MU2, prm) for _ in range(N)]
    p3 = sum(g.t1_periods[2] + g.t2_periods[2] for g in games) / N
    total = sum(sum(g.t1_periods) + sum(g.t2_periods) for g in games) / N
    return p3, total


@pytest.mark.parametrize("base", [
    sm.SimParams(),
    sm.empty_net_params(None, "hockey", True),
    sm.SimParams(hk_common=0.1, hk_disp=0.06),
])
def test_on_keeps_regulation_and_third_period_means(base: sm.SimParams | None
                                                    ) -> None:
    prm = dataclasses.replace(base or sm.SimParams(), hk_late_in_mean=True)
    p3, total = _means(prm)
    assert abs(p3 - (MU1[2] + MU2[2])) < 0.02
    assert abs(total - (sum(MU1) + sum(MU2))) < 0.02


def test_off_is_the_old_simulation_bit_for_bit() -> None:
    off = dataclasses.replace(sm.SimParams(), hk_late_in_mean=False)
    rng_a, rng_b = random.Random(5), random.Random(5)
    old = [sm._hockey(rng_a, MU1, MU2, sm.SimParams(hk_late_in_mean=None))
           for _ in range(2000)]
    new = [sm._hockey(rng_b, MU1, MU2, off) for _ in range(2000)]
    assert old == new
    # the defect the switch fixes: the late goal on top of the mean
    p3, total = _means(off)
    assert p3 - (MU1[2] + MU2[2]) > 0.1
    assert total - (sum(MU1) + sum(MU2)) > 0.1


def test_late_goal_keeps_its_shape() -> None:
    """The margin's 2-3 goal mass still comes from the late goal: fewer
    one-goal regulation games than a plain draw at the same means."""
    on = sm.SimParams(hk_late_in_mean=True)
    plain = sm.SimParams(hk_late_lead=0.0, hk_late_trail=0.0)

    def one_goal(prm: sm.SimParams) -> float:
        rng = random.Random(11)
        gs = [sm._hockey(rng, MU1, MU2, prm) for _ in range(40_000)]
        return sum(abs(sum(g.t1_periods) - sum(g.t2_periods)) == 1
                   for g in gs) / len(gs)
    assert one_goal(on) < one_goal(plain) - 0.02


def test_simulate_reads_the_clock_when_unforced(monkeypatch: pytest.MonkeyPatch
                                                ) -> None:
    model = sm.ScoreModel(SPORTS["hockey"], RatingBook(), 6.0)
    off = model.simulate(MU1, MU2, seed=9, n=500)
    assert sm.late_goal_in_mean_marker(model.params) == {}
    switch = datetime(2026, 10, 28, tzinfo=UTC)
    monkeypatch.setattr(epochs, "HK_LATE_GOAL_IN_MEAN_FROM_UTC", switch)
    monkeypatch.setattr(timeutil, "now",
                        lambda: datetime(2026, 10, 27, 23, tzinfo=UTC))
    assert model.simulate(MU1, MU2, seed=9, n=500) == off
    monkeypatch.setattr(timeutil, "now",
                        lambda: datetime(2026, 10, 28, 1, tzinfo=UTC))
    assert model.simulate(MU1, MU2, seed=9, n=500) != off
    assert sm.late_goal_in_mean_marker(model.params) == {
        sm.HK_LATE_GOAL_IN_MEAN_RULE: "2026-10-28T00:00:00Z"}
    forced = sm.late_goal_in_mean_params(None, "hockey", False)
    assert forced is not None and forced.hk_late_in_mean is False
    model.params = forced
    assert model.simulate(MU1, MU2, seed=9, n=500) == off
    assert sm.late_goal_in_mean_marker(forced) == {}
    assert epochs.hk_late_goal_in_mean("2026-10-27") is False
    assert sm.late_goal_in_mean_params(None, "basketball", True) is None


def test_skellam_sums_to_one() -> None:
    total = sum(sm._skellam(3.0, 2.5, k) for k in range(-25, 26))
    assert abs(total - 1.0) < 1e-9
    assert sm._skellam(2.0, 0.0, 1) == pytest.approx(2.0 * 2.718281828 ** -2.0)
