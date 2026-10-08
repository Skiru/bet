"""scripts/sofa/measure_tennis_calibration.py - synthetic, offline checks of the
calibrators, the interval, the Klaassen-Magnus engine and the neighbour read."""

import json
import math

import numpy as np
import pytest

from scripts.sofa import fit_confidence
from scripts.sofa import measure_tennis_calibration as m


def test_edges_and_wilson_are_the_fits_own() -> None:
    assert tuple(m.EDGES) == tuple(fit_confidence.EDGES)
    assert m.wilson_lo(37, 50) == pytest.approx(fit_confidence.wilson_lo(37, 50))
    assert m.MIN_MARKET_BUCKET == fit_confidence.MIN_MARKET_BUCKET
    assert m.MIN_THIN_BUCKET == fit_confidence.MIN_THIN_BUCKET


def test_pav_is_monotone_and_pools_a_violation() -> None:
    out = m.pav(np.array([0.1, 0.5, 0.3, 0.9]), np.array([1.0, 1.0, 1.0, 1.0]))
    assert list(out) == pytest.approx([0.1, 0.4, 0.4, 0.9])
    assert np.all(np.diff(out) >= 0)


def _sample(n: int, seed: int = 1) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    p = rng.uniform(0.6, 0.97, n)
    truth = np.clip(p - 0.04 * (p - 0.6) / 0.37, 0, 1)  # over-confident model
    y = (rng.random(n) < truth).astype(np.float64)
    return p, y


def test_every_calibrator_beats_raw_on_an_overconfident_model() -> None:
    p, y = _sample(60_000)
    p_te, y_te = _sample(60_000, seed=2)
    raw = m.log_loss_terms(p_te, y_te).mean()
    for model in (
        m.Isotonic().fit(p, y),
        m.BetaCalibration().fit(p, y),
        m.MonotoneSpline().fit(p, y),
    ):
        assert m.log_loss_terms(model.predict(p_te), y_te).mean() < raw
    bucket = m.BucketCurve(100).fit(p, y).predict(p_te)
    assert m.log_loss_terms(bucket, y_te).mean() < raw


def test_spline_and_isotonic_are_monotone() -> None:
    p, y = _sample(20_000, seed=3)
    grid = np.linspace(0.6, 0.97, 400)
    for model in (m.Isotonic().fit(p, y), m.MonotoneSpline().fit(p, y)):
        assert np.all(np.diff(model.predict(grid)) >= -1e-12)


def test_beta_calibration_recovers_its_own_parameters() -> None:
    rng = np.random.default_rng(5)
    p = rng.uniform(0.55, 0.97, 200_000)
    c, a, b = 0.2, 0.8, 1.2
    q = 1 / (1 + np.exp(-(c + a * np.log(p) - b * np.log(1 - p))))
    y = (rng.random(p.size) < q).astype(np.float64)
    fitted = m.BetaCalibration().fit(p, y).beta
    assert fitted == pytest.approx([c, a, b], abs=0.08)


def test_bucket_curve_leaves_a_thin_bucket_to_the_pool() -> None:
    curve = m.BucketCurve(min_rows=400).fit(np.full(399, 0.72), np.ones(399))
    assert np.isnan(curve.predict(np.array([0.72]))[0])
    curve = m.BucketCurve(min_rows=400).fit(np.full(400, 0.72), np.ones(400))
    assert curve.predict(np.array([0.72]))[0] == 1.0
    assert curve.predict(np.array([0.72]), lower=True)[0] < 1.0  # Wilson bound


def test_ece_is_zero_for_a_perfect_bucket_and_positive_otherwise() -> None:
    p = np.full(1000, 0.80)
    y = np.concatenate([np.ones(800), np.zeros(200)])
    assert m.ece(p, y) == pytest.approx(0.0)
    assert m.ece(np.full(1000, 0.9), y) == pytest.approx(0.1)


def test_ndtri_ndtr_roundtrip() -> None:
    p = np.array([0.001, 0.2, 0.5, 0.8, 0.999])
    assert m._ndtr(m._ndtri(p)) == pytest.approx(p, abs=1e-6)


def test_p_lower_only_lowers_and_grows_with_z_and_shrinks_with_n() -> None:
    p = np.array([0.80, 0.80, 0.80])
    n = np.array([8.0, 10.0, 20.0])
    sd = np.array([2.0, 2.0, 2.0])
    p0 = m.p_lower(p, n, sd, 0.0)
    assert p0 == pytest.approx(p, abs=1e-6)
    p1 = m.p_lower(p, n, sd, 1.0)
    p2 = m.p_lower(p, n, sd, 2.0)
    assert np.all(p1 < p) and np.all(p2 < p1)
    # the shrunk standard error sqrt(n)/(n+K) is non-monotone in n (peaks near
    # n = K_CENTRE): n = 8 and 10 lose about the same, n = 20 less
    assert (p - p1)[2] < (p - p1)[1]


def test_cluster_bootstrap_contains_the_point_and_is_narrow_for_many_clusters() -> None:
    rng = np.random.default_rng(0)
    num = rng.normal(0.1, 1.0, 5000)
    den = np.ones(5000)
    pt, lo, hi = m.cluster_bootstrap_mean(num, den, reps=200)
    assert lo < pt < hi and hi - lo < 0.2


def test_window_lo_matches_the_production_greedy_expansion() -> None:
    rng = np.random.default_rng(1)
    keys = np.sort(rng.random(3000))
    ps = rng.random(100)
    got = m.window_lo(keys, ps, 600)

    def brute(p: float) -> int:
        i = int(np.searchsorted(keys, p))
        lo = hi = i
        while hi - lo < 600:
            left = p - keys[lo - 1] if lo > 0 else math.inf
            right = keys[hi] - p if hi < keys.size else math.inf
            if left <= right:
                lo -= 1
            else:
                hi += 1
        return lo

    assert list(got) == [brute(float(p)) for p in ps]


def test_neighbour_table_reads_a_known_distribution() -> None:
    # 1000 outcomes at p = 0.5: half 12-6 in two sets, half 14-12 in three sets
    n = 1000
    p = np.full(n, 0.5)
    gf = np.where(np.arange(n) % 2 == 0, 12, 14)
    ga = np.where(np.arange(n) % 2 == 0, 6, 12)
    ns = np.where(np.arange(n) % 2 == 0, 2, 3)
    table = m.NeighbourTable(
        p, gf.astype(np.int64), ga.astype(np.int64), ns.astype(np.int64)
    )
    probs = table.probs(np.array([0.5]), w=600)[0]
    # P(total > 24.5): only the 26-game half
    assert probs[m.GT_LINES.index(24.5)] == pytest.approx(0.5, abs=0.01)
    assert probs[m.GT_LINES.index(16.5)] == pytest.approx(1.0)
    assert probs[-1] == pytest.approx(0.5, abs=0.01)  # sets_total over 2.5
    assert probs[-2] == pytest.approx(1.0)  # margin > 0 always


def test_truth_matrix_matches_the_event_layout() -> None:
    t = m.truth_matrix(np.array([13]), np.array([8]), np.array([3]))
    assert t.shape == (1, m.N_EVENTS)
    assert t[0, m.GT_LINES.index(20.5)] == 1.0 and t[0, m.GT_LINES.index(21.5)] == 0.0
    assert t[0, -1] == 1.0 and t[0, -2] == 1.0


def test_game_and_tiebreak_symmetry_and_monotonicity() -> None:
    p = np.array([0.5, 0.6, 0.7])
    g = m.game_win(p)
    assert g[0] == pytest.approx(0.5) and np.all(np.diff(g) > 0)
    assert np.all(g[1:] > p[1:])  # a server edge compounds
    tb = m.tiebreak_win(p)
    assert tb[0] == pytest.approx(0.5) and np.all(np.diff(tb) > 0)
    assert m.game_win(np.array([0.3]))[0] + m.game_win(np.array([0.7]))[
        0
    ] == pytest.approx(1.0)


def test_set_distribution_is_a_distribution_and_symmetric_players_are_even() -> None:
    ph = np.array([0.62, 0.55])
    sd = m.point_to_set(ph, ph)
    assert sum(sd) == pytest.approx(np.ones(2))
    assert m.match_win_from_sets(sd) == pytest.approx([0.5, 0.5])
    stronger = m.point_to_set(np.array([0.66]), np.array([0.6]))
    assert m.match_win_from_sets(stronger)[0] > 0.5


def test_km_events_are_probabilities_with_the_right_monotonicity() -> None:
    sd = m.point_to_set(np.array([0.64, 0.58]), np.array([0.60, 0.62]))
    ev = m.km_match_events(sd)
    assert ev.shape == (2, m.N_EVENTS)
    assert np.all((ev >= -1e-12) & (ev <= 1 + 1e-12))
    gt = ev[:, : len(m.GT_LINES)]
    assert np.all(np.diff(gt, axis=1) <= 1e-12)  # P(total > L) falls with L
    hc = ev[:, -2 - len(m.HC_LINES) : -2]
    assert np.all(np.diff(hc, axis=1) <= 1e-12)
    # the margin>0 event equals the handicap ladder's midpoint
    assert ev[:, -2] == pytest.approx(hc[:, len(m.HC_LINES) // 2], abs=1e-9)


def test_km_hybrid_matches_the_target_win_probability() -> None:
    n = 3
    zeros = np.zeros(n)
    mu = np.full(n, -0.35)
    target = np.array([0.35, 0.5, 0.8])
    out = m.km_events(zeros, zeros, zeros, zeros, mu, p_target=target)
    # P(home wins the match) is the P(margin > 0) + the draws that are wins in sets;
    # the sets_total / margin events stay probabilities and move with the target
    assert out[0, -2] < out[1, -2] < out[2, -2]


def test_parse_serve_points_checks_its_identities() -> None:
    def item(name: str, h: str, a: str) -> dict[str, object]:
        return {"name": name, "home": h, "away": a}

    items = [
        item("First serve points", "30/45", "28/40"),
        item("Second serve points", "12/25", "10/30"),
        # return counts close on the opponent's serve counts
        item("First serve return points", "12/40", "15/45"),
        item("Second serve return points", "20/30", "13/25"),
    ]
    doc = json.dumps(
        {"statistics": [{"period": "ALL", "groups": [{"statisticsItems": items}]}]}
    )
    got = m.parse_serve_points(doc)
    assert got == (42, 70, 38, 70)
    bad = json.loads(doc)
    bad["statistics"][0]["groups"][0]["statisticsItems"][2]["home"] = "11/40"
    assert m.parse_serve_points(json.dumps(bad)) is None
    assert m.parse_serve_points("not json") is None


def test_surface_and_tier_codes() -> None:
    assert m.surface4("Hardcourt indoor") == 1 and m.surface4("Red clay") == 2
    assert m.surface4("Grass") == 3 and m.surface4(None) == 0
    assert (
        m.tier_code("ITF Women") == m.TIER_ITF and m.tier_code("WTA 125") == m.TIER_CH
    )
    assert m.tier_code("ATP") == m.TIER_TOUR


def test_current_confidence_reads_the_family_bucket_lower_bound() -> None:
    rng = np.random.default_rng(0)
    p = rng.uniform(0.72, 0.74, 5000)
    y = (rng.random(5000) < 0.70).astype(np.float64)
    fam = {0: m.BucketCurve(400).fit(p, y)}
    pool = m.BucketCurve(200).fit(p, y)
    got = m.current_confidence(np.array([0.73]), np.array([0]), fam, pool, {})
    assert got[0] == pytest.approx(m.wilson_lo(float(y.sum()), float(y.size)), abs=1e-6)
