"""scripts/sofa/measure_football_result_model.py - the C2 outcome-market
measurement on synthetic data (offline, fast)."""

from __future__ import annotations

import math

import numpy as np
import pytest

from bet.sofa import football_rating as fr
from scripts.sofa import measure_football_result_model as m


def test_count_pmf_poisson_and_nb_match_their_closed_forms() -> None:
    lam = np.array([0.4, 1.3, 2.7])
    pois = m.count_pmf(lam, None, 20)
    for row, mu in zip(pois, lam, strict=True):
        for k in (0, 1, 3):
            assert row[k] == pytest.approx(math.exp(-mu) * mu**k / math.factorial(k))
    r = np.array([2.0, 6.0, 50.0])
    nb = m.count_pmf(lam, r, 30)
    for row, mu, rr in zip(nb, lam, r, strict=True):
        p = rr / (rr + mu)
        for k in (0, 2, 5):
            exact = math.exp(
                math.lgamma(k + rr) - math.lgamma(rr) - math.lgamma(k + 1)
                + rr * math.log(p) + k * math.log1p(-p))
            assert row[k] == pytest.approx(exact, rel=1e-6)
        mean = float(np.arange(31) @ row)
        var = float((np.arange(31) ** 2) @ row) - mean**2
        assert mean == pytest.approx(mu, rel=1e-4)
        assert var == pytest.approx(mu + mu * mu / rr, rel=1e-3)


def test_market_probs_are_coherent() -> None:
    lh, la = np.array([1.6, 0.9]), np.array([1.1, 2.2])
    grid = m.score_grid(m.count_pmf(lh, None, 25), m.count_pmf(la, None, 25))
    mp = m.market_probs(grid)
    assert mp.res.sum(axis=1) == pytest.approx(np.ones(2))
    assert mp.cs.sum(axis=1) == pytest.approx(np.ones(2))
    # the total of independent Poissons is Poisson: P(odd) = (1 - e^-2L) / 2
    total = lh + la
    assert mp.odd == pytest.approx((1 - np.exp(-2 * total)) / 2, abs=1e-9)
    assert mp.btts == pytest.approx((1 - np.exp(-lh)) * (1 - np.exp(-la)), abs=1e-9)
    assert mp.cs[:, 0] == pytest.approx(np.exp(-total), abs=1e-12)  # 0-0


def test_selections_drop_draws_from_dnb_and_never_sell_other() -> None:
    grid = m.score_grid(m.count_pmf(np.array([1.5, 1.0, 1.2]), None),
                        m.count_pmf(np.array([1.0, 1.0, 0.8]), None))
    mp = m.market_probs(grid)
    x, y = np.array([2.0, 1.0, 0.0]), np.array([0.0, 1.0, 3.0])
    sels = m.selections(mp, None, x, y, None, None, None)
    dnb = [s for s in sels if s.market == "dnb"]
    assert all(list(s.match) == [0, 2] for s in dnb)
    assert dnb[0].p + dnb[1].p == pytest.approx(np.ones(2))
    assert not any(s.name == "other" for s in sels)
    dc = {s.name: s for s in sels if s.market == "double_chance"}
    assert list(dc["X2"].o) == [0.0, 1.0, 1.0]


def test_base_rate_is_the_league_shrunk_to_the_global() -> None:
    glob, league = m._Freq(), m._Freq()
    for _ in range(70):
        glob.add(1, 0, (0, 0))
    for _ in range(30):
        glob.add(0, 0, None)
        league.add(0, 0, None)
    b = m.base_probs(league, glob)
    # league: 30 draws; global: 70 home / 30 draws; m = 30
    assert b["res"][1] == pytest.approx((30 + m.BASE_M * 0.3) / (30 + m.BASE_M))
    assert b["ht"][1] == pytest.approx(1.0)  # no league halves: the global's
    assert m.base_probs(None, glob)["res"][0] == pytest.approx(0.7)


def _history(n: int, flip: int | None = None) -> list[fr.FootballResult]:
    rng = np.random.default_rng(3)
    teams = list(range(1, 9))
    out = []
    for k in range(n):
        h, a = rng.choice(teams, 2, replace=False)
        x, y = int(rng.poisson(1.5)), int(rng.poisson(1.1))
        if k == flip:
            x, y = 9, 0
        hx, hy = min(x, int(rng.poisson(0.7))), min(y, int(rng.poisson(0.5)))
        out.append(fr.FootballResult(
            event_id=k + 1, ts=1_750_000_000 + 3600 * k, competition_id=17,
            home_id=int(h), away_id=int(a),
            values={"goals_for": (float(x), float(y)),
                    "goals_1h_for": (float(hx), float(hy))}))
    return out


def test_walk_forward_rows_never_see_the_match_or_the_future() -> None:
    hist = _history(260)
    start = hist[150].ts
    rows = m.collect_rows(hist, start, hist[-1].ts + 1)
    assert len(rows["ts"]) > 50
    assert rows["ts"].min() >= start
    assert set(rows["link"].tolist()) == {0.0}  # one league: LINKED
    # changing a later match's score moves nothing priced before it
    flip = 220
    alt = m.collect_rows(_history(260, flip), start, hist[-1].ts + 1)
    before = rows["ts"] <= hist[flip].ts
    for key in ("lh", "la", "sh", "sa", "b_btts", "b_odd"):
        assert np.array_equal(rows[key][before], alt[key][before])
    assert np.array_equal(rows["b_res"][before], alt["b_res"][before])
    after = rows["ts"] > hist[flip].ts
    assert not np.array_equal(rows["lh"][after], alt["lh"][after])


def test_curve_maps_a_bucket_to_its_train_rate_and_keeps_thin_buckets() -> None:
    n = 4000
    p = np.full(n, 0.82)
    o = (np.arange(n) % 4 != 0).astype(float)  # realised 0.75
    rows = np.arange(n)
    sel = m.Selection("dnb", "home", p, o, rows)
    thin = m.Selection("dnb", "home", np.full(10, 0.55), np.ones(10), np.arange(10))
    curves = m.fit_curves([sel, thin])
    out = m.apply_curves([m.Selection("dnb", "home", np.array([0.81, 0.56]),
                                      np.zeros(2), np.arange(2))], curves)
    assert out[0].p[0] == pytest.approx(0.75)
    assert out[0].p[1] == pytest.approx(0.56)  # bucket under CURVE_MIN_N: p kept
