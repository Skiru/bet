"""scripts/sofa/measure_k_under_dispersion.py - the K-under-dispersion
measurement on synthetic rows (offline, fast)."""

from __future__ import annotations

import numpy as np
import pytest

from bet.sofa.count_dispersion import parse_table
from scripts.sofa import measure_k_under_dispersion as mk
from scripts.sofa import measure_pooling as mp


def test_prior_round_trips_through_the_k15_centre() -> None:
    for n, mean, prior in ((8, 3.2, 4.4), (10, 0.7, 0.9), (3, 12.0, 9.5)):
        c15 = mk.centre_at(15.0, n, mean, prior)
        assert mk.prior_of(c15, n, mean) == pytest.approx(prior)
    assert mk.centre_at(0.0, 10, 3.0, 5.0) == 3.0
    assert mk.centre_at(1000.0, 10, 3.0, 5.0) == pytest.approx(5.0, abs=0.03)


def test_dispersion_variants() -> None:
    table = parse_table({"markets": {"goals_for": {
        "family": "nb", "alpha": 0.2, "by_competition": {"17": 0.5}}}})
    assert mk.dispersion_for("N", table, "goals_for", 17) is None
    assert mk.dispersion_for("M", table, "goals_for", 17).alpha == 0.2  # type: ignore[union-attr]
    assert mk.dispersion_for("A", table, "goals_for", 17).alpha == 0.5  # type: ignore[union-attr]
    assert mk.dispersion_for("A", table, "goals_for", 99).alpha == 0.2  # type: ignore[union-attr]
    assert mk.dispersion_for("A", table, "no_such", 17) is None


def test_row_probs_are_probabilities_and_move_with_k() -> None:
    table = parse_table({"markets": {"goals_for": {"family": "nb", "alpha": 0.2}}})
    ps, lines, hi = mk.row_probs("goals_for", 17, 2.0, 1.5, 8, 1.0, "A", table)
    assert len(ps) == len(mk.K_GRID) and len(lines) == 9 and len(hi) == 9
    assert all(mp.P_CLIP <= p <= 1 - mp.P_CLIP for row in ps for p in row)
    # a sample mean above the prior: a larger K pulls the centre down, so
    # P(OVER) of the middle rung falls
    mid = [row[4] for row in ps]
    assert mid[0] > mid[-1]


def test_choose_k_picks_the_lowest_summed_loss_on_the_mask_only() -> None:
    ll = np.ones((6, len(mk.K_GRID)))
    ll[:3, 2] = 0.5  # K=5 is best on the first three rows
    ll[3:, 7] = 0.0  # K=40 is best on the others, outside the mask
    mask = np.array([True, True, True, False, False, False])
    k, sums = mk.choose_k(ll, mask)
    assert k == mk.K_GRID[2]
    assert len(sums) == len(mk.K_GRID)


def _synthetic(tmp_rows: int = 400) -> dict[str, np.ndarray]:
    rng = np.random.default_rng(4)
    n = tmp_rows
    ev = np.arange(n) // 2
    return {
        "ev": ev, "ts": np.arange(n), "base": np.full(n, mp.BASES.index("goals")),
        "unit": np.zeros(n, dtype=int), "comp": np.full(n, 17),
        "n": np.full(n, 8), "nmin": np.full(n, 8),
        "y": rng.poisson(1.4, n).astype(float),
        "mean": rng.uniform(1.0, 2.0, n), "var": np.full(n, 1.5),
        "train": (np.arange(n) < n // 2).astype(int),
    }


def test_analyse_runs_end_to_end_and_never_touches_a_thin_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    meta = _synthetic()
    table = parse_table({"markets": {"goals_for": {"family": "nb", "alpha": 0.1}}})
    prior = meta["mean"] * 0 + 1.4
    # the worker reads a module-level table: set it as the initializer would
    monkeypatch.setattr(mk, "_TABLE", table)
    rows = [("goals_for", 17, float(meta["mean"][i]), float(meta["var"][i]), 8,
             float(meta["y"][i]), float(prior[i])) for i in range(len(prior))]
    ll, pp, oo, hh = mk._chunk((rows, "A"))
    loss = {"ll": ll, "p": pp, "o": oo, "hi": hh}
    res = mk.analyse(meta, loss, reps=30, log=lambda _m: None, min_train_rows=10_000)
    assert res["chosen"]["goals_for"]["K"] == mk.K_TODAY  # too thin: unchanged
    stratum = res["strata"]["ALL_for|n>=8"]
    # K stays 15 everywhere, so the paired difference is exactly zero
    assert stratum["d_ll_all"]["est"] == 0.0
    assert stratum["d_lc_all"]["est"] == 0.0
    res2 = mk.analyse(meta, loss, reps=30, log=lambda _m: None, min_train_rows=10)
    assert res2["chosen"]["goals_for"]["train_rows"] == 200
    assert "d_lc_all" in res2["strata"]["ALL_for|n>=8"]


def test_validated_k_keeps_a_k_only_when_it_wins_on_the_held_out_train_rows() -> None:
    n = 3000
    ev = np.arange(n)
    meta = {"ev": ev, "ts": np.arange(n), "nmin": np.full(n, 8),
            "train": np.ones(n, dtype=int)}
    group = np.zeros(n, dtype=int)
    train = np.ones(n, dtype=bool)
    ok = np.ones(n, dtype=bool)
    ll = np.full((n, len(mk.K_GRID)), 5.0)
    rng = np.random.default_rng(1)
    i5 = mk.K_GRID.index(5.0)
    i15 = mk.K_GRID.index(mk.K_TODAY)
    # K = 5 is better by 0.1 per row everywhere (a real effect)
    ll[:, i15] = 4.0 + rng.normal(0, 0.05, n)
    ll[:, i5] = 3.9 + rng.normal(0, 0.05, n)
    out = mk.validated_k(meta, ll, group, train, ok, reps=50, min_train_rows=100)
    assert out[0][0] == 5.0 and out[0][1]["kept"]
    # better in the first part, worse in the validation third: stays at 15
    ll[:, i5] = np.where(np.arange(n) < 2000, 3.9, 4.2)
    out = mk.validated_k(meta, ll, group, train, ok, reps=50, min_train_rows=100)
    assert out[0][0] == mk.K_TODAY and not out[0][1]["kept"]
    # thin: nothing changes
    out = mk.validated_k(meta, ll, group, train, ok, reps=50, min_train_rows=10_000)
    assert out[0][0] == mk.K_TODAY
