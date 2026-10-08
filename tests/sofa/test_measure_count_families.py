"""measure_count_families: the numerics the A2 measurement stands on.

Offline and fast: synthetic counts only. The check that matters most is that
the vectorised `cur` family is the engine's own estimator (sheet_predictive_sd
+ sheet_count_p_raw) - the measurement compares families against that.
"""

from __future__ import annotations

import math

import numpy as np

import scripts.sofa.calibrate_from_cache as cc
import scripts.sofa.measure_count_families as mcf
from bet.sofa.comparability import MatchKind
from bet.sofa.engine import (
    nb_survival,
    sheet_count_p_raw,
    sheet_predictive_sd,
    winning_boundary,
)


def _cases(n: int, mean_range: tuple[float, float], seed: int = 0) -> mcf.Cases:
    rng = np.random.default_rng(seed)
    mu = rng.uniform(*mean_range, n)
    samp = np.full((n, mcf.SAMPLE_PAD), np.nan)
    ns = rng.integers(8, 11, n)
    for i in range(n):
        samp[i, : ns[i]] = rng.poisson(mu[i] * rng.uniform(0.8, 1.2), ns[i])
    mean = np.nanmean(samp, axis=1)
    var = np.nanvar(samp, axis=1, ddof=1)
    keep = mean > 0
    centre = 0.7 * mean + 0.3 * mu
    y = rng.poisson(mu).astype(float)
    ev = np.arange(n, dtype=np.int64)
    zero = np.zeros(n, dtype=np.int64)
    return mcf.Cases(
        ts=np.arange(n, dtype=float), ev=ev, comp=zero + 1, team=zero,
        y=y, n=ns.astype(float), mean=mean, var=var, centre=centre, samp=samp,
    ).take(keep)


def test_lgamma_matches_math() -> None:
    x = np.array([0.05, 0.3, 0.5, 1.0, 2.5, 10.0, 123.4, 1000.0])
    ref = np.array([math.lgamma(v) for v in x])
    assert np.max(np.abs(mcf.lgamma_np(x) - ref) / np.maximum(1.0, np.abs(ref))) < 1e-12


def test_nb_pmf_is_a_distribution_with_the_requested_moments() -> None:
    mu = np.array([0.4, 3.0, 11.0])
    var = np.array([0.4, 7.5, 30.0])  # the first is Poisson
    pmf = mcf.nb_pmf(mu, var, 200)
    k = np.arange(201)
    assert np.allclose(pmf.sum(axis=1), 1.0, atol=1e-9)
    assert np.allclose((pmf * k).sum(axis=1), mu, atol=1e-6)
    assert np.allclose((pmf * k**2).sum(axis=1) - mu**2, var, atol=1e-4)


def test_nb_over_is_engine_nb_survival() -> None:
    mu = np.array([0.8, 2.6, 9.5, 9.5])
    var = np.array([0.8, 4.0, 20.0, 9.0])  # variance below the mean: Poisson
    thr = np.array([[0, 1, 2], [1, 2, 3], [8, 9, 10], [8, 9, 10]])
    got = mcf.nb_over(mu, var, thr)
    for i in range(4):
        for j in range(3):
            want = nb_survival(float(mu[i]), float(var[i]), int(thr[i, j]))
            assert abs(got[i, j] - want) < 1e-9


def test_current_family_is_the_engine_estimator() -> None:
    c = _cases(60, (0.6, 14.0))
    lines, thr = mcf.rung_grid(c.centre)
    assert np.allclose(lines[0], cc.lines_for(float(c.centre[0])))
    for market, listed in (("corners_for", True), ("fouls_for", False)):
        mine = mcf.current_over(market, c, thr, listed)
        for i in range(len(c)):
            sd = sheet_predictive_sd(
                market, "football", float(c.mean[i]), float(c.var[i]),
                int(c.n[i]), float(c.centre[i]),
            )
            for j in range(mcf.GRID):
                b = winning_boundary(float(lines[i, j]), "OVER")
                want = sheet_count_p_raw(market, float(c.centre[i]), sd, b, "OVER")
                assert abs(want - mine[i, j]) < 1e-9, (market, i, j)


def test_zero_inflated_nb_keeps_the_mean() -> None:
    mu = np.array([1.2, 4.0])
    thr = np.tile(np.arange(120), (2, 1))
    over = mcf.zinb_over(mu, 0.2, 0.08, thr)
    assert np.allclose(over.sum(axis=1), mu, atol=1e-4)  # E X = sum P(X > k)
    plain = mcf.nb_over(mu, mu + 0.2 * mu * mu, thr[:, :1])
    assert np.all(over[:, 0] < plain[:, 0])  # more mass at zero


def test_com_poisson_is_mean_matched_and_nu_one_is_poisson() -> None:
    tab = mcf.cmp_table(1.0)
    mu = np.array([0.3, 2.0, 7.0, 30.0])
    thr = np.tile(np.arange(100), (4, 1))
    over = mcf.cmp_over(tab, mu, thr)
    assert np.allclose(over.sum(axis=1), mu, rtol=2e-3)
    pois = mcf.nb_over(mu, mu, thr[:, :6])
    assert np.allclose(mcf.cmp_over(tab, mu, thr[:, :6]), pois, atol=2e-3)
    wide = mcf.cmp_table(0.6)  # overdispersed: more mass in the upper tail
    k9 = np.array([[9]])
    assert mcf.cmp_over(wide, mu[1:2], k9)[0, 0] > mcf.cmp_over(tab, mu[1:2], k9)[0, 0]


def test_kernel_empirical_is_a_decreasing_survival_inside_the_support() -> None:
    c = _cases(20, (2.0, 8.0), seed=2)
    _, thr = mcf.rung_grid(c.centre)
    p = mcf.emp_over(c.samp, c.n, c.centre, c.mean, np.sqrt(c.var), thr, 1.0)
    assert np.all((p >= 0) & (p <= 1))
    assert np.all(np.diff(p, axis=1) <= 1e-12)


def test_fit_recovers_the_dispersion_of_synthetic_nb() -> None:
    rng = np.random.default_rng(1)
    n = 40000
    mu = rng.uniform(1.0, 9.0, n)
    alpha = 0.25
    r = 1.0 / alpha
    y = rng.poisson(rng.gamma(r, mu / r)).astype(float)
    z = np.zeros(n, dtype=np.int64)
    c = mcf.Cases(
        np.arange(n, dtype=float), np.arange(n), z + 5, z, y,
        np.full(n, 10.0), mu, mu, mu, np.full((n, mcf.SAMPLE_PAD), np.nan),
    )
    fit = mcf.fit_family_params(c, mle_cases=20000)
    assert abs(fit.alpha - alpha) / alpha < 0.12
    assert abs(fit.alpha_mom - alpha) / alpha < 0.12
    assert fit.zi_pi <= 0.02  # nothing to inflate
    assert fit.phi > 1.0


def test_partial_pooling_endpoints() -> None:
    fit = mcf.Fit(alpha=0.2, alpha_mom=0.2, bmean=4.0,
                  comp_ab={7: (4.0 * 1000 * 0.5, 4.0 * 1000)},
                  team_ab={3: (4.0 * 1000 * 0.1, 4.0 * 1000)})
    z = np.zeros(2, dtype=np.int64)
    c = mcf.Cases(z.astype(float), z, z + 7, z + 3, z.astype(float), z + 10.0,
                  z + 1.0, z + 1.0, z + 1.0, np.zeros((2, mcf.SAMPLE_PAD)))
    assert np.allclose(mcf.alpha_league(c, fit, 1e9), 0.2, atol=1e-6)
    assert np.allclose(mcf.alpha_league(c, fit, 1e-9), 0.5, atol=1e-6)
    assert np.allclose(mcf.alpha_team(c, fit, 1e9, 1e-9), 0.1, atol=1e-6)
    unseen = mcf.Cases(*(a[:1] for a in (
        c.ts, c.ev, c.comp + 1, c.team, c.y, c.n, c.mean, c.var, c.centre, c.samp)))
    assert np.allclose(mcf.alpha_league(unseen, fit, 100.0), 0.2)


def test_bootstrap_separates_a_better_family_from_a_copy() -> None:
    rng = np.random.default_rng(0)
    n = 4000
    ev = np.arange(n)
    base_ll = rng.uniform(0.6, 0.8, n)

    def sc(ll: np.ndarray) -> mcf.Scored:
        ones = np.full(n, 5.0)
        return mcf.Scored(ll * 0.3, ll * 5.0, ones, ones, ones * 0.8, ones * 0.8,
                          np.zeros((1, 3)), np.zeros((1, 3)))

    out = mcf.bootstrap_deltas(
        ev, sc(base_ll), {"copy": sc(base_ll), "better": sc(base_ll - 0.01)}, 200
    )
    assert out["copy"]["d_ll"][0] == 0.0
    assert out["copy"]["d_ll"][1] <= 0.0 <= out["copy"]["d_ll"][2]
    assert out["better"]["d_ll"][2] < 0.0
    assert out["better"]["d_brier"][2] < 0.0


def test_collector_keeps_what_the_replay_settles_with() -> None:
    """The replay is run unchanged and only _settle_sample is swapped: the
    collector sees the same centre and sample SHEET's replay prices from."""
    played = [
        cc.Played(i, 1_700_000_000 + i * 90_000, 1 + (i % 2), 2 - (i % 2),
                  "football", 17,
                  {"corners": (float(3 + i % 5), float(4 + i % 3))},
                  kind=MatchKind.REGULAR)
        for i in range(30)
    ]
    original = cc._settle_sample
    try:
        collector = mcf.Collector(cc, {})
        cc._settle_sample = collector
        assert list(cc.iter_rows(played, {})) == []
    finally:
        cc._settle_sample = original
    cols = collector.cols["corners_for"]
    assert len(cols["y"]) > 0
    assert len(cols["y"]) == len(collector.samp["corners_for"]) // mcf.SAMPLE_PAD
    assert all(v >= cc.MIN_SAMPLE for v in cols["n"])
    assert "corners_total" in collector.cols


def test_verdict_needs_both_intervals_both_halves_and_enough_matches() -> None:
    good = {"d_ll": [-0.004, -0.006, -0.002], "d_brier": [-0.001, -0.002, -0.0003]}
    assert mcf.verdict(good, (-0.003, -0.005), 0.01, 0.01, 5000) == "BETTER"
    assert mcf.verdict(good, (-0.003, 0.001), 0.01, 0.01, 5000) == "NO_DIFFERENCE"
    assert mcf.verdict(good, (-0.003, -0.005), 0.01, 0.01, 100) == "INCONCLUSIVE"
    bad = {"d_ll": [0.004, 0.002, 0.006], "d_brier": [0.001, 0.0003, 0.002]}
    assert mcf.verdict(bad, (0.003, 0.005), 0.01, 0.01, 5000) == "WORSE"


def test_every_family_is_a_decreasing_survival_on_the_ladder() -> None:
    c = _cases(300, (0.8, 12.0), seed=4)
    fit = mcf.fit_family_params(c, mle_cases=300)
    _, thr = mcf.rung_grid(c.centre)
    for name in mcf.FAMILIES:
        p = mcf.family_over(name, "corners_for", True, c, thr, fit, mcf.Hyper())
        assert p.shape == (len(c), mcf.GRID), name
        assert np.all((p >= 0.0) & (p <= 1.0)), name
        assert np.all(np.diff(p, axis=1) <= 1e-9), name


def test_score_families_counts_only_rungs_the_current_estimator_prices() -> None:
    c = _cases(400, (1.0, 9.0), seed=5)
    fit = mcf.fit_family_params(c, mle_cases=400)
    out = mcf.score_families(("cur", "nb_pool"), "corners_for", True, c, fit,
                             mcf.Hyper(), size=150)
    assert np.array_equal(out["cur"].cnt, out["nb_pool"].cnt)
    assert out["cur"].cnt.sum() > 0
    assert out["cur"].tail[:, 0].sum() == len(c) * mcf.GRID
    assert np.all(out["cur"].brier <= out["cur"].cnt + 1e-9)
