"""Offline tests of the A3 dependence / goals measurement (synthetic data only)."""

from __future__ import annotations

import math

import numpy as np

from bet.sofa.joint import _build
from scripts.sofa import measure_dependence_goals as m


def test_numpy_gaussian_copula_equals_the_shipped_joint() -> None:
    args = (5.2, 8.0, 4.1, 6.0)
    ours = m.copula_pmf(*args, -0.2)
    shipped = np.array(_build(*args, -0.2).pmf)
    assert ours.shape == shipped.shape
    assert np.abs(ours - shipped).max() < 1e-6


def test_copula_pmf_is_a_distribution_with_the_given_marginals() -> None:
    for family, nu in (("gauss", 4), ("t", 4), ("t", 8)):
        pmf = m.copula_pmf(2.1, 2.6, 1.4, 1.4, 0.3, family, nu)
        assert abs(pmf.sum() - 1.0) < 1e-9
        assert (pmf >= 0).all()
        marg_a = pmf.sum(axis=1)
        assert abs(float(np.arange(len(marg_a)) @ marg_a) - 2.1) < 0.02


def test_t_copula_has_a_heavier_joint_tail_than_gaussian() -> None:
    args = (4.0, 5.0, 4.0, 5.0)
    g = m.copula_pmf(*args, 0.5)
    t = m.copula_pmf(*args, 0.5, "t", 4)
    assert t[9:, 9:].sum() > g[9:, 9:].sum()
    assert t[:2, :2].sum() > g[:2, :2].sum()


def test_solve_latent_hits_the_target_correlation() -> None:
    args = (1.3, 1.3, 1.1, 1.1)
    for target in (-0.2, 0.15):
        latent = m.solve_latent(*args, target)
        got = m.observed_corr(m.copula_pmf(*args, latent))
        assert abs(got - target) < 3e-3
    assert m.solve_latent(*args, 0.0) == 0.0


def test_dc_correction_keeps_the_total_and_moves_low_cells() -> None:
    lh = np.array([1.4, 2.0])
    la = np.array([1.1, 0.9])
    base = m.independent_grid(
        m.poisson_pmf_matrix(lh, 14), m.poisson_pmf_matrix(la, 14)
    )
    grid = m.dc_grid(base, lh, la, -0.1)
    assert np.allclose(grid.sum(axis=(1, 2)), base.sum(axis=(1, 2)), atol=1e-12)
    assert (grid[:, 0, 0] > base[:, 0, 0]).all()  # rho < 0 lifts 0-0
    assert (grid[:, 1, 1] > base[:, 1, 1]).all()
    assert (grid[:, 0, 1] < base[:, 0, 1]).all()


def test_fit_dc_rho_recovers_the_parameter() -> None:
    rng = np.random.default_rng(1)
    n = 60000
    lh = rng.uniform(0.8, 2.2, n)
    la = rng.uniform(0.6, 1.8, n)
    base = m.independent_grid(
        m.poisson_pmf_matrix(lh, 14), m.poisson_pmf_matrix(la, 14)
    )
    true_rho = -0.12
    grid = m.dc_grid(base, lh, la, true_rho)
    grid /= grid.sum(axis=(1, 2), keepdims=True)
    flat = grid.reshape(n, -1)
    cum = np.cumsum(flat, axis=1)
    u = rng.random(n)[:, None]
    cell = np.minimum((cum < u).sum(axis=1), flat.shape[1] - 1)
    x, y = cell // 15, cell % 15
    est = m.fit_dc_rho(lh, la, x.astype(np.int64), y.astype(np.int64))
    assert abs(est - true_rho) < 0.03


def test_bivariate_poisson_keeps_the_means_and_adds_covariance() -> None:
    lh = np.array([1.6])
    la = np.array([1.2])
    grid = m.bivariate_poisson_grid(lh, la, 0.25, 20)[0]
    assert abs(grid.sum() - 1.0) < 1e-6
    i = np.arange(grid.shape[0])
    assert abs(float(i @ grid.sum(axis=1)) - 1.6) < 1e-4
    assert abs(float(i @ grid.sum(axis=0)) - 1.2) < 1e-4
    cov = float(((i[:, None] - 1.6) * (i[None, :] - 1.2) * grid).sum())
    assert abs(cov - 0.25 * 1.2) < 1e-4  # lambda3 = kappa * min(lh, la)


def test_event_matrix_x12_sums_to_one() -> None:
    lh, la = np.array([1.5, 0.9]), np.array([1.0, 1.4])
    grid = m.independent_grid(
        m.poisson_pmf_matrix(lh, 14), m.poisson_pmf_matrix(la, 14)
    )
    grid /= grid.sum(axis=(1, 2), keepdims=True)
    probs, labels = m.goal_event_matrix(grid)
    cols = [k for k, (c, _) in enumerate(labels) if c == "x12"]
    assert len(cols) == 3
    assert np.allclose(probs[:, cols].sum(axis=1), 1.0)
    out = m.goal_outcomes(np.array([2.0, 0.0]), np.array([1.0, 0.0]))
    assert out.shape[1] == probs.shape[1]


def test_bootstrap_ratio_interval_is_ordered_and_covers_the_estimate() -> None:
    rng = np.random.default_rng(2)
    num = rng.normal(0.1, 1.0, 2000)
    den = np.ones(2000)
    est, lo, hi = m.bootstrap_ratio(num, den, reps=300)
    assert lo < est < hi
    assert abs(est - num.mean()) < 1e-12
    assert hi - lo < 0.2
    assert all(math.isnan(v) for v in m.bootstrap_ratio(np.array([]), np.array([])))


def test_correlation_matrix_ci_of_independent_columns_covers_zero() -> None:
    rng = np.random.default_rng(4)
    data = rng.normal(size=(3000, 3))
    data[:, 2] += 0.5 * data[:, 0]
    est, lo, hi = m.corr_matrix_ci(data, reps=100)
    assert lo[0, 1] < 0.0 < hi[0, 1]
    assert lo[0, 2] > 0.2
    assert abs(est[0, 0] - 1.0) < 1e-12


def test_event_probs_independent_both_over_is_a_product() -> None:
    pmf = m.copula_pmf(3.0, 3.0, 2.0, 2.0, 0.0)
    out = m.event_probs(pmf, [0.5, 1.5], [0.5])
    pa, pb = pmf.sum(axis=1), pmf.sum(axis=0)
    assert abs(out["both_over"][1] - pa[2:].sum() * pb[2:].sum()) < 1e-9
    assert abs(out["most"].sum() - 1.0) < 1e-9


def test_loss_functions() -> None:
    p, o = np.array([0.8, 0.3]), np.array([1.0, 0.0])
    assert np.allclose(m.log_loss(p, o), [-math.log(0.8), -math.log(0.7)])
    assert np.allclose(m.brier(p, o), [0.04, 0.09])
