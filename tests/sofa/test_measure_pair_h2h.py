"""scripts/sofa/measure_pair_h2h.py - the pure helpers of the pair H2H
measurement (pre-registered in docs/sofa/evidence/pair_h2h_2026-10-13.md)."""

import math

import numpy as np
import pytest

from scripts.sofa.measure_pair_h2h import (
    Columns,
    PairMemory,
    adjust,
    boot_groups,
    day_ts,
    evaluate,
    fit_big_k,
    loss_vec,
    months,
    nb_constant,
    ols_slope,
    pair_key,
    placebo_value,
    shrink_weight,
    side_subject,
    summarise,
    verdict,
)

DAY = 86400


def test_pair_key_is_unordered_and_side_subject_follows_the_lower_id():
    assert pair_key(9, 3) == pair_key(3, 9) == (3, 9)
    assert side_subject(4, 3, (3, 9)) == 4
    assert side_subject(4, 9, (3, 9)) == 5


def test_shrink_weight_is_the_blup_and_infinity_is_no_adjustment():
    assert shrink_weight(1, 1.0) == pytest.approx(0.5)
    assert shrink_weight(3, 1.0) == pytest.approx(0.75)
    assert shrink_weight(5, math.inf) == 0.0
    arr = shrink_weight(np.array([1.0, 4.0]), 4.0)
    assert arr.tolist() == pytest.approx([0.2, 0.5])


def test_memory_never_sees_the_match_itself_or_beyond_the_window():
    mem = PairMemory(2, max_gap_days=100, k_max=2)
    pair = (1, 2)
    t0 = day_ts("2026-01-01")
    mem.add(pair, t0, {0: 1.0})
    mem.add(pair, t0 + 50 * DAY, {0: 2.0, 1: 5.0})
    mem.add(pair, t0 + 90 * DAY, {0: 3.0})
    # strictly before; newest first; at most k_max
    assert [r for _, r in mem.prior(pair, 0, t0 + 90 * DAY)] == [2.0, 1.0]
    assert [r for _, r in mem.prior(pair, 0, t0 + 91 * DAY)] == [3.0, 2.0]
    # older than max_gap is not read
    assert [r for _, r in mem.prior(pair, 0, t0 + 160 * DAY, )] == [3.0]
    # a subject missing from a meeting is skipped, not zero
    assert [r for _, r in mem.prior(pair, 1, t0 + 91 * DAY)] == [5.0]
    # the short-gap read drops meetings closer than min_gap
    assert [r for _, r in mem.prior(pair, 0, t0 + 91 * DAY, 30 * DAY)] == [2.0, 1.0]
    assert mem.prior((7, 8), 0, t0) == []


def test_summarise():
    assert summarise([(0, 1.0), (0, 3.0)], [(0, 3.0)]) == (2, 2.0, 1, 3.0)
    assert summarise([(0, 1.0)], []) == (1, 1.0, 0, 0.0)


def test_columns_count_the_window_and_keep_only_rows_with_a_meeting():
    t = day_ts("2026-01-10")
    cols = Columns(day_ts("2026-01-01"), day_ts("2026-02-01"))
    cols.add(1, (1, 2), t, 2.0, 3.0, [], [])
    cols.add(2, (1, 2), t, 2.0, 3.0, [(t - DAY, 0.5)], [])
    cols.add(3, (1, 2), day_ts("2025-12-01"), 2.0, 3.0, [(0, 0.5)], [])
    assert cols.window_rows == 2 and cols.window_groups == {1, 2}
    assert len(cols) == 2


def test_losses():
    y = np.array([2.0])
    # squared error
    assert loss_vec("se", y, np.array([3.0]), np.zeros(1))[0] == pytest.approx(1.0)
    # binary log-loss
    assert loss_vec("bin", np.array([1.0]), np.array([0.5]), np.zeros(1))[0] == (
        pytest.approx(math.log(2)))
    # NB: differences between two means equal those of the full likelihood
    def full(yv: float, mu: float, alpha: float) -> float:
        r = 1 / alpha
        return -(math.lgamma(yv + r) - math.lgamma(r) - math.lgamma(yv + 1)
                 + r * math.log(r / (r + mu)) + yv * math.log(mu / (r + mu)))
    a = np.array([0.2])
    full_ours = loss_vec("nb", y, np.array([3.0]), a) + nb_constant(y, a)
    assert full_ours[0] == pytest.approx(full(2, 3.0, 0.2))
    pois = loss_vec("nb", y, np.array([3.0]), np.zeros(1)) + nb_constant(y, np.zeros(1))
    assert pois[0] == pytest.approx(-(2 * math.log(3) - 3 - math.lgamma(3)))
    d = (loss_vec("nb", y, np.array([3.0]), a) - loss_vec("nb", y, np.array([2.5]), a))
    assert d[0] == pytest.approx(full(2, 3.0, 0.2) - full(2, 2.5, 0.2))
    # alpha 0 is the Poisson
    dp = loss_vec("nb", y, np.array([3.0]), np.zeros(1)) - loss_vec(
        "nb", y, np.array([2.0]), np.zeros(1))
    assert dp[0] == pytest.approx(-(2 * math.log(3) - 3) + (2 * math.log(2) - 2))


def test_adjust_floors_counts_and_clips_probabilities():
    c, rb, k = np.array([0.1]), np.array([-5.0]), np.array([5.0])
    assert adjust("nb", c, rb, k, 0.5)[0] == pytest.approx(0.05)
    assert adjust("bin", np.array([0.98]), np.array([0.5]), k, 0.5)[0] == 0.99
    assert adjust("se", c, rb, k, math.inf)[0] == pytest.approx(0.1)


def test_fit_big_k_finds_persistence_and_refuses_noise():
    rng = np.random.default_rng(1)
    n = 4000
    u = rng.normal(0, 1.0, n)          # the pair effect
    rbar = u + rng.normal(0, 1.0, n)   # one past residual
    y = 10 + u + rng.normal(0, 1.0, n)
    c, k, a = np.full(n, 10.0), np.ones(n), np.zeros(n)
    big_k = fit_big_k("se", y, c, a, k, rbar)
    # BLUP with tau^2 = sigma^2 = 1: w = 1 / (1 + 1) -> K = 1
    assert big_k in (0.5, 1, 2)
    # no pair effect: the grid's best is a weight near zero
    y0 = 10 + rng.normal(0, 1.0, n)
    assert fit_big_k("se", y0, c, a, k, rng.normal(0, 1.0, n)) >= 200
    assert fit_big_k("se", y0[:0], c[:0], a[:0], k[:0], rbar[:0]) == math.inf


def test_boot_groups_resamples_whole_groups():
    vals = np.array([1.0, 1.0, 3.0])
    res = boot_groups([7, 7, 9], vals, n_boot=200)
    assert res["mean"] == pytest.approx(5 / 3)
    assert res["rows"] == 3 and res["groups"] == 2
    # a draw is all of group 7 (mean 1), all of 9 (mean 3) or both (5/3)
    assert 1.0 <= res["q"][0] <= res["q"][1] <= 3.0


def test_ols_slope():
    x = np.array([0.0, 1.0, 2.0, 3.0])
    assert ols_slope(x, 2 * x + 1) == pytest.approx(2.0)
    assert math.isnan(ols_slope(np.ones(3), np.arange(3.0)))


def test_months_cover_the_window():
    ms = months("2025-08-15", "2025-10-02")
    assert [m for m, _, _ in ms] == ["2025-08", "2025-09", "2025-10"]
    assert ms[0][1] == day_ts("2025-08-15")
    assert ms[-1][2] == day_ts("2025-10-03")


def _cols_with_pair_effect(effect_sd: float) -> Columns:
    rng = np.random.default_rng(0)
    cols = Columns(day_ts("2025-08-01"), day_ts("2026-10-13"))
    start = day_ts("2024-10-01")
    for i in range(6000):
        ts = start + int(i * (740 * DAY) / 6000)
        u = rng.normal(0, effect_sd)
        past = u + rng.normal(0, 1.0)
        y = 10 + u + rng.normal(0, 1.0)
        cols.add(i, (i % 500, 1000 + i % 500), ts, 10.0, y, [(ts - 40 * DAY, past)],
                 [(ts - 40 * DAY, past)])
    return cols


def test_evaluate_and_verdict_on_synthetic_rows():
    strong = evaluate(_cols_with_pair_effect(1.0), "se", "2025-08-01", "2026-10-12")
    assert strong["rows"] > 0
    assert strong["d_loss"][2] < 0
    assert strong["slope_resid_on_rbar"]["slope"] == pytest.approx(0.5, abs=0.1)
    assert verdict(strong) == "CANDIDATE"
    none = evaluate(_cols_with_pair_effect(0.0), "se", "2025-08-01", "2026-10-12")
    assert verdict(none) in ("NO_GAIN", "MAY_BE_CHANCE")
    assert evaluate(Columns(0, 1), "se", "2025-08-01", "2026-10-12") == {"rows": 0}
    assert verdict({"d_loss": [0.1, -0.1, 0.2]}) == "NO_GAIN"


def test_placebo_reads_the_sides_against_other_opponents_only():
    pair = (3, 9)
    recent = {3: [(5, 1.0), (9, 100.0), (6, 3.0)], 9: [(7, -2.0), (3, 50.0)]}
    # one side: its latest k residuals, the meeting with 9 skipped
    assert placebo_value(recent, ((3, 1.0),), pair, 2, False) == pytest.approx(2.0)
    assert placebo_value(recent, ((3, 1.0),), pair, 1, False) == pytest.approx(3.0)
    # a total: the mean of the two sides' means
    assert placebo_value(recent, ((3, 1.0), (9, 1.0)), pair, 2, False) == (
        pytest.approx(0.0))
    # a margin: lower side's mean minus the other's
    assert placebo_value(recent, ((3, 1.0), (9, -1.0)), pair, 2, True) == (
        pytest.approx(4.0))
    # a side with nothing against anyone else: no placebo
    assert placebo_value({3: [(9, 1.0)]}, ((3, 1.0),), pair, 2, False) is None
