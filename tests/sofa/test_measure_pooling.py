"""scripts/sofa/measure_pooling.py - the pooling measurement, on synthetic
hierarchical data (offline, fast)."""

import math
import random

import numpy as np
import pytest

from scripts.sofa import measure_pooling as mp

DAY = 86400


def synthetic_matches(
    n_leagues: int = 6, teams: int = 10, rounds: int = 14, *, s2_l: float = 1.0,
    s2_t: float = 0.5, seed: int = 3, start: int = 1_600_000_000,
) -> tuple[list, dict[int, float]]:
    """Corners = league level + team level + Poisson-ish noise, every team
    plays every round; returns the match tuples and the true league means."""
    rng = random.Random(seed)
    level: dict[int, float] = {}
    team_eff: dict[tuple[int, int], float] = {}
    matches = []
    eid = 0
    for lg in range(1, n_leagues + 1):
        level[lg] = 9.0 + rng.gauss(0, math.sqrt(s2_l))
        for t in range(teams):
            team_eff[(lg, t)] = rng.gauss(0, math.sqrt(s2_t))
    for r in range(rounds):
        for lg in range(1, n_leagues + 1):
            order = list(range(teams))
            rng.shuffle(order)
            for a in range(0, teams, 2):
                h, w = order[a], order[a + 1]
                mu_h = max(0.5, level[lg] / 2 + team_eff[(lg, h)])
                mu_a = max(0.5, level[lg] / 2 + team_eff[(lg, w)])
                hv = float(np.random.default_rng(eid).poisson(mu_h))
                av = float(np.random.default_rng(eid + 10**6).poisson(mu_a))
                eid += 1
                matches.append((start + r * 3 * DAY + eid, eid, lg * 100 + h,
                                lg * 100 + w, lg, "REGULAR",
                                {"corners": (hv, av)}))
    matches.sort()
    return matches, level


def cells_of(matches: list, base: str = "corners") -> mp.Cells:
    cells: mp.Cells = {}
    for _ts, _eid, h, a, comp, _k, vals in matches:
        hv, av = vals[base]
        for team, v in ((h, hv), (a, av)):
            c = cells.setdefault((comp, team), [0.0, 0.0, 0.0])
            c[0] += 1
            c[1] += v
            c[2] += v * v
    return cells


def test_size_class_edges():
    assert mp.size_class(10) == 0
    assert mp.size_class(mp.CLASS_EDGES[0]) == 1
    assert mp.size_class(mp.CLASS_EDGES[-1]) == mp.N_CLASSES - 1


def test_today_centre_is_the_fixed_k_shrink():
    snap = mp.Snap(G=9.0, s2_t=[1.0] * mp.N_CLASSES, today_prior={7: 12.0},
                   P={}, cls={})
    assert mp.today_centre(snap, 7, 8.0, 10) == pytest.approx(
        (10 * 8.0 + mp.K_TODAY * 12.0) / (10 + mp.K_TODAY))
    # a league without a baseline falls back to the global mean
    assert mp.today_centre(snap, 99, 8.0, 10) == pytest.approx(
        (10 * 8.0 + mp.K_TODAY * 9.0) / (10 + mp.K_TODAY))


def test_components_are_recovered_from_a_hierarchy():
    # many leagues and teams so the moment estimates are tight
    matches, _ = synthetic_matches(n_leagues=40, teams=16, rounds=30, s2_l=1.0,
                                   s2_t=0.5)
    snap = mp.build_snap(cells_of(matches), "for")
    # true: team effect var .5 (+ rounding of the floor), league var of the
    # per-team mean = 0.25 (level/2 has var s2_l / 4), Poisson noise ~ mean
    assert snap.s2_w == pytest.approx(4.5, abs=0.8)  # Poisson at ~4.5
    pooled_t = max(snap.s2_t)
    assert pooled_t == pytest.approx(0.5, abs=0.2)
    assert snap.s2_l == pytest.approx(0.25, abs=0.15)
    assert snap.k_team(0) > 0


def test_no_league_effect_gives_no_league_variance():
    matches, _ = synthetic_matches(n_leagues=30, teams=14, rounds=25, s2_l=0.0,
                                   s2_t=0.5, seed=9)
    snap = mp.build_snap(cells_of(matches), "for")
    assert snap.s2_l < 0.08


def test_unobserved_league_prior_is_the_global_mean():
    matches, _ = synthetic_matches(n_leagues=3, rounds=4)
    snap = mp.build_snap(cells_of(matches), "for")
    centre = mp.team_centre(snap, 4242, 7.0, 10)
    assert centre == pytest.approx(
        snap.G + 10 / (10 + snap.k_team(0)) * (7.0 - snap.G))


def test_league_table_flags_a_reliably_high_league():
    matches, _ = synthetic_matches(n_leagues=20, teams=16, rounds=30, s2_l=0.0,
                                   s2_t=0.3, seed=5)
    # inflate league 1 by 2.5 corners a team
    boosted = []
    for ts, eid, h, a, comp, kind, vals in matches:
        hv, av = vals["corners"]
        if comp == 1:
            hv, av = hv + 2.5, av + 2.5
        boosted.append((ts, eid, h, a, comp, kind, {"corners": (hv, av)}))
    cells = cells_of(boosted)
    snap = mp.build_snap(cells, "for")
    rows = mp.league_table(cells, snap, {1: "boosted"}, "for", min_matches=20)
    by = {r["comp"]: r for r in rows}
    assert by[1]["flag"] == "HIGH"
    assert by[1]["material"] and by[1]["bound_dev"] > 0
    assert by[1]["lo"] > snap.G
    # shrinkage moves a league toward the global mean, never past its raw mean
    assert abs(by[1]["shrunk"] - snap.G) <= abs(by[1]["raw"] - snap.G) + 1e-9
    assert sum(1 for r in rows if r["flag"]) <= 3


def test_a_match_is_never_in_its_own_sample():
    start = 1_600_000_000
    matches = []
    for i in range(12):  # team 1 and 2 always 5-5
        matches.append((start + i * DAY, i, 1, 2, 7, "REGULAR",
                        {"corners": (5.0, 5.0)}))
    matches.append((start + 20 * DAY, 99, 1, 2, 7, "REGULAR",
                    {"corners": (100.0, 100.0)}))
    matches.append((start + 21 * DAY, 100, 1, 2, 7, "REGULAR",
                    {"corners": (4.0, 4.0)}))
    rep = mp.replay(matches, cut_ts=start + 19 * DAY, acc_from_ts=start + 8 * DAY)
    rows = list(zip(rep.meta["ev"], rep.meta["unit"], rep.meta["y"],
                    rep.meta["mean"], strict=True))
    big = [r for r in rows if r[0] == 99 and r[1] == 0]
    assert big and big[0][2] == 100.0 and big[0][3] == pytest.approx(5.0)
    after = [r for r in rows if r[0] == 100 and r[1] == 0]
    assert after and after[0][3] > 5.0  # the 100 is in the NEXT sample


def test_friendlies_are_never_scored_nor_sampled():
    start = 1_600_000_000
    matches = [(start + i * DAY, i, 1, 2, 7, "REGULAR", {"corners": (5.0, 6.0)})
               for i in range(12)]
    matches.append((start + 15 * DAY, 50, 1, 2, 8, "FRIENDLY",
                    {"corners": (40.0, 40.0)}))
    matches.append((start + 16 * DAY, 51, 1, 2, 7, "REGULAR",
                    {"corners": (5.0, 6.0)}))
    rep = mp.replay(matches, cut_ts=start + 14 * DAY, acc_from_ts=start + 8 * DAY)
    assert 50 not in rep.meta["ev"]
    row = [i for i, e in enumerate(rep.meta["ev"])
           if e == 51 and rep.meta["unit"][i] == 0]
    assert rep.meta["mean"][row[0]] == pytest.approx(5.0)


def test_eb_beats_the_unpooled_mean_on_a_hierarchy():
    matches, _ = synthetic_matches(n_leagues=8, teams=12, rounds=40, s2_l=1.5,
                                   s2_t=0.3, seed=11)
    cut = matches[-1][0] - 20 * 3 * DAY
    rep = mp.replay(matches, cut, acc_from_ts=matches[0][0] + 10 * DAY)
    y = np.asarray(rep.meta["y"])
    ok = np.asarray(rep.meta["nmin"]) >= mp.MIN_SAMPLE
    unit = np.asarray(rep.meta["unit"])
    sel = ok & (unit < 2)
    assert sel.sum() > 300
    se = {v: float(np.mean((np.asarray(rep.cols[f"{v}_F"]) - y)[sel] ** 2))
          for v in ("nopool", "today", "eb")}
    assert se["eb"] < se["nopool"]
    assert se["today"] < se["nopool"]


def test_total_additive_centre_is_prior_plus_both_deviations():
    snap = mp.Snap(G=9.0, s2_w=10.0, s2_t=[2.0] * mp.N_CLASSES, s2_t_nolg=2.0,
                   today_prior={}, P={5: 10.0}, cls={5: 0})
    unit = mp.Unit(2, 11.0, 5, 20, 10, 10.0, 12.0, [(11.0, 10), (13.0, 10)])
    out = mp.centres_for(unit, snap, mp.Acc.new())
    w = 10 / (10 + 10.0 / 2.0)
    assert out["eb"] == pytest.approx(10.0 + w * 1.0 + w * 3.0)
    assert out["ebavg"] == pytest.approx(
        10.0 + 20 / (20 + 5.0) * (10.0 - 10.0))


def test_bootstrap_interval_covers_a_known_difference():
    rng = np.random.default_rng(1)
    ev = np.repeat(np.arange(400), 3)
    d = rng.normal(0.5, 1.0, len(ev))
    boot = mp.Boot(ev, reps=200, seed=2)
    res = boot.ratio(d, np.ones(len(ev)), np.ones(len(ev), dtype=bool))
    assert res["lo"] < res["est"] < res["hi"]
    assert abs(res["est"] - 0.5) < 0.15
    assert res["hi"] - res["lo"] < 0.3
    assert res["matches"] == 400


def test_row_losses_use_sheets_own_estimator():
    from bet.sofa.engine import sheet_count_p_raw, sheet_predictive_sd

    se, res, ps, outs, hi = mp.row_losses(
        "corners_for", 5.0, 6.0, 10, 4.0, [5.0, 5.0], 5.0)
    assert se == [1.0, 1.0]
    assert res[0] == res[1]
    # one rung by hand: the 4.5 line of a grid anchored at 5.0 (lines 1.5..9.5)
    sd = sheet_predictive_sd("corners_for", "football", 5.0, 6.0, 10, 5.0)
    p = sheet_count_p_raw("corners_for", 5.0, sd, 4.5, "OVER")
    assert ps[0][3] == pytest.approx(min(1 - mp.P_CLIP, max(mp.P_CLIP, p)))
    assert outs[3] == 0.0 and outs[2] == 1.0  # y = 4: over 3.5, not over 4.5
    la, _ba, n_all, _lh, _bh, n_hi = res[0]
    assert n_all == 9 and la > 0 and n_hi == sum(hi)


def test_a_calibration_map_fitted_on_train_fixes_a_biased_p():
    rng = np.random.default_rng(4)
    n = 4000
    true_p = rng.uniform(0.2, 0.8, (n, 1, 9))
    o = (rng.uniform(size=(n, 9)) < true_p[:, 0, :]).astype(np.int8)
    biased = np.clip(true_p * 0.5 + 0.25, 0.02, 0.98)  # flattened toward 0.5
    loss = {"p": biased.astype(np.float32), "o": o,
            "hi": np.ones((n, 9), dtype=bool)}
    train = np.arange(n) < n // 2
    all_, hi = mp.calibrated_losses(loss, train, ~train, np.zeros(n, dtype=int))
    p = biased[~train, 0, :]
    oo = o[~train]
    raw = -(oo * np.log(p) + (1 - oo) * np.log(1 - p)).sum()
    assert all_[~train, 0].sum() < raw
    assert hi[~train, 0].sum() == pytest.approx(all_[~train, 0].sum())
    assert float(all_[train].sum()) == 0.0  # only evaluation rows are scored


def test_end_to_end_smoke_on_a_synthetic_hierarchy():
    matches, _ = synthetic_matches(n_leagues=8, teams=12, rounds=45, s2_l=1.5,
                                   s2_t=0.4, seed=21)
    cut = matches[-1][0] - 15 * 3 * DAY
    rep = mp.replay(matches, cut, acc_from_ts=matches[0][0] + 10 * DAY,
                    train_days=90)
    assert sum(rep.meta["train"]) > 0 and 0 in rep.meta["train"]
    loss = mp.ladder_pass(rep, procs=1)
    res = mp.assemble(rep, loss, {1: "L1"}, reps=20)
    assert res["meta"]["eval_matches"] > 100
    assert "corners_for" in res["strata"]
    f = res["strata"]["corners_for"]["F"]
    assert f["eb"]["se"]["lo"] <= f["eb"]["se"]["est"] <= f["eb"]["se"]["hi"]
    assert res["leagues"]["corners_for"]["rows"]
    # the league slope is positive on a world with real league effects
    assert res["league_info_slope"]["corners_for"]["est"] > 0
