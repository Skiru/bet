"""Offline tests of the two measurement-only point models of 2026-11-06:
tennis games handicap read off the point model (bet.sofa.tennis_handicap_point)
and the volleyball rally-point model (bet.sofa.volleyball_point_model).
docs/sofa/evidence/tennis_handicap_point_model_2026-11-06.md,
docs/sofa/evidence/volleyball_point_model_2026-11-06.md."""

from __future__ import annotations

import math
import random
from pathlib import Path

import numpy as np
import pytest

from bet.sofa import volleyball_point_model as vpm
from bet.sofa.score_model import line_probability
from bet.sofa.shadow import SPORTS, ShadowLine
from bet.sofa.tennis_handicap_point import mean_sd, p_handicap
from bet.sofa.tennis_point_model import (
    MarketSim,
    MatchForecast,
    SideForecast,
    SimResult,
    market_sim,
)

REPO = Path(__file__).resolve().parents[2]


# --------------------------------------------------------------------------
# Tennis
# --------------------------------------------------------------------------


def _forecast(home: float = 0.4, away: float = 0.2) -> MatchForecast:
    side = SideForecast(home, 0.01, 0.06, 0.03, 5000.0)
    other = SideForecast(away, 0.01, 0.06, 0.03, 5000.0)
    return MatchForecast(side, other, False)


def _hand_sim() -> MarketSim:
    # three matches: 6-3 6-4; 4-6 7-6 6-2; 6-0 3-6 1-0 (a match tiebreak = 1 game)
    games = np.array([
        [[6, 3], [6, 4], [0, 0]],
        [[4, 6], [7, 6], [6, 2]],
        [[6, 0], [3, 6], [1, 0]],
    ], dtype=np.int64)
    sim = SimResult(games=games, sets_played=np.array([2, 3, 3]),
                    serve_points=np.zeros((3, 3, 2), dtype=np.int64),
                    home_won=np.array([True, True, True]))
    return MarketSim(_forecast(), sim)


def test_tennis_match_handicap_reads_the_game_margin() -> None:
    ms = _hand_sim()
    # home margins: +5 (12-7), +3 (17-14), +4 (10-6)
    assert p_handicap(ms, "handicap_games", 0, -4.5) == pytest.approx(1 / 3)
    assert p_handicap(ms, "handicap_games", 0, -3.5) == pytest.approx(2 / 3)
    assert p_handicap(ms, "handicap_games", 0, -2.5) == 1.0
    assert p_handicap(ms, "handicap_games", 1, 4.5) == pytest.approx(2 / 3)
    # an integer line landing exactly is a push, left out
    assert p_handicap(ms, "handicap_games", 0, -5.0) == pytest.approx(0.0)
    assert p_handicap(ms, "handicap_games", 0, -4.0) == pytest.approx(0.5)
    assert p_handicap(ms, "handicap_games", 0, -3.0) == pytest.approx(1.0)


def test_tennis_set_handicap_reads_the_set_margin() -> None:
    ms = _hand_sim()
    # set 1 home margins +3, -2, +6; set 2: +2, +1, -3
    assert p_handicap(ms, "handicap_games_won_set1", 0, -2.5) == pytest.approx(2 / 3)
    assert p_handicap(ms, "handicap_games_won_set1", 1, 1.5) == pytest.approx(1 / 3)
    assert p_handicap(ms, "handicap_games_won_set2", 0, 0.5) == pytest.approx(2 / 3)
    assert p_handicap(ms, "games_total", 0, 0.5) is None
    assert mean_sd(ms, "handicap_games", 0) == pytest.approx(
        (4.0, float(np.std([5, 3, 4]))))


def test_tennis_handicap_sides_are_complements_on_half_lines() -> None:
    ms = market_sim(_forecast(0.5, 0.1), n=2000, seed=3)
    for market in ("handicap_games", "handicap_games_won_set1",
                   "handicap_games_won_set2"):
        for line in (-5.5, -2.5, -0.5, 1.5, 3.5):
            a = p_handicap(ms, market, 0, line)
            b = p_handicap(ms, market, 1, -line)
            assert a is not None and b is not None
            assert a + b == pytest.approx(1.0)
    # the stronger server gives games: P(home -1.5) above P(away -1.5)
    home = p_handicap(ms, "handicap_games", 0, -1.5)
    away = p_handicap(ms, "handicap_games", 1, -1.5)
    assert home is not None and away is not None and home > away


# --------------------------------------------------------------------------
# Volleyball: the chain
# --------------------------------------------------------------------------


def test_stationary_share_is_half_at_level_and_monotone() -> None:
    assert vpm.stationary_share(0.0, 0.62) == pytest.approx(0.5)
    shares = [vpm.stationary_share(d, 0.62) for d in (-1.0, -0.2, 0.0, 0.3, 1.2)]
    assert shares == sorted(shares)


def test_set_score_table_is_a_distribution_and_symmetric_at_level() -> None:
    for target in (25, 15):
        table = vpm.set_score_table(0.0, 0.62, target)
        assert sum(table.values()) == pytest.approx(1.0, abs=1e-8)
        assert table[(target, 10)] == pytest.approx(table[(10, target)])
        assert all(vpm.set_over(a, b, target) for a, b in table)


def test_set_score_table_without_serve_effect_is_the_binomial_race() -> None:
    # so = 0.5 and d = 0: every rally a coin, P(25:k) = C(24 + k, k) / 2^(25 + k)
    table = vpm.set_score_table(0.0, 0.5, 25, True)
    for k in (0, 7, 23):
        expected = math.comb(24 + k, k) / 2 ** (25 + k)
        assert table[(25, k)] == pytest.approx(expected, rel=1e-9)


def test_higher_sideout_makes_sets_closer() -> None:
    def p_close(so: float) -> float:
        t = vpm.set_score_table(0.4, so, 25)
        return sum(v for (a, b), v in t.items() if abs(a - b) == 2)
    assert p_close(0.68) > p_close(0.5)


def test_simulated_matches_follow_the_rules() -> None:
    f = vpm.VbForecast(mu=0.3, var=0.02, sideout=0.62, women=False)
    sim = vpm.simulate(f, vpm.VbParams(set_var=0.01), n=3000, seed=7)
    for s in range(len(sim.sets_played)):
        k = int(sim.sets_played[s])
        assert 3 <= k <= 5
        wins = [0, 0]
        for i in range(k):
            a, b = (int(x) for x in sim.points[s, i])
            target = 15 if i == 4 else 25
            assert vpm.set_over(a, b, target)
            assert max(a, b) == target or abs(a - b) == 2
            wins[0 if a > b else 1] += 1
        assert max(wins) == 3 and sim.points[s, k:].sum() == 0


def test_simulation_agrees_with_the_exact_set_table() -> None:
    f = vpm.VbForecast(mu=0.25, var=0.0, sideout=0.62, women=False)
    sim = vpm.simulate(f, vpm.VbParams(form_var=0.0, set_var=0.0), n=20000, seed=1)
    table = vpm.set_score_table(vpm._q(0.25), 0.62, 25)
    p_win = sum(v for (a, b), v in table.items() if a > b)
    mc = float((sim.points[:, 0, 0] > sim.points[:, 0, 1]).mean())
    assert mc == pytest.approx(p_win, abs=4 * math.sqrt(0.25 / 20000))
    mean_total = sum((a + b) * v for (a, b), v in table.items())
    assert float(sim.points[:, 0, :].sum(axis=1).mean()) == pytest.approx(
        mean_total, abs=0.15)


def test_line_p_matches_shadow_grading() -> None:
    sport = SPORTS["volleyball"]
    f = vpm.VbForecast(mu=0.15, var=0.03, sideout=0.6, women=True)
    sim = vpm.simulate(f, vpm.VbParams(set_var=0.01), n=600, seed=11)
    games = [sim.game(s) for s in range(600)]
    lines = [
        (745, 0, "", None, "T1"), (745, 0, "", None, "T2"),
        (230058, 0, "", 3.5, "OVER"), (230058, 0, "", 4.5, "UNDER"),
        (100082, 0, "", -1.5, "T1"), (100082, 0, "", 1.5, "T2"),
        (230060, 0, "", 180.5, "OVER"), (230060, 0, "", 170.5, "UNDER"),
        (230060, 0, "", 180.0, "OVER"),
        (1069, 0, "", -4.5, "T1"), (1069, 0, "", 6.5, "T2"), (1069, 0, "", -3.0, "T1"),
        (744, 1, "", None, "T1"), (744, 4, "", None, "T2"), (744, 5, "", None, "T1"),
        (782, 1, "", 45.5, "OVER"), (782, 4, "", 44.5, "UNDER"),
        (785, 0, "", None, "3:1"), (785, 0, "", None, "2:3"),
        (200896, 0, "", None, "ODD"), (781, 2, "", None, "EVEN"),
        (100077, 1, "", None, "YES"), (100077, 5, "", None, "NO"),
        (-11, 0, "", None, "YES"), (-12, 0, "", None, "NO"),
        (-13, 0, "", 1.0, "YES"), (-14, 0, "", 2.0, "NO"),
        (-15, 0, "", None, "SETS=4"), (-15, 0, "", None, "SETS=5"),
    ]
    for mid, period, subject, line, side in lines:
        sl = ShadowLine("x", mid, "f", period, subject, line, side, 1.9)
        want = line_probability(sl, games, sport)
        got = vpm.line_p(sim, mid, period, subject, line, side)
        if want is None:
            assert got is None, (mid, period, side)
        else:
            assert got == pytest.approx(want), (mid, period, line, side)
    swapped = sim.swapped()
    p = vpm.line_p(sim, 1069, 0, "", -4.5, "T1")
    q = vpm.line_p(swapped, 1069, 0, "", 4.5, "T2")
    assert p == pytest.approx(q)


def test_quantile_lines_follow_synthetic_lines() -> None:
    f = vpm.VbForecast(mu=0.0, var=0.02, sideout=0.62, women=False)
    sim = vpm.simulate(f, vpm.VbParams(), n=500, seed=2)
    totals = np.sort(sim.points.sum(axis=(1, 2)))
    lines = vpm.quantile_lines(sim, 230060, 0, (0.1, 0.5, 0.9))
    assert lines == sorted({math.floor(totals[int(q * (len(totals) - 1))]) + 0.5
                            for q in (0.1, 0.5, 0.9)})


# --------------------------------------------------------------------------
# Volleyball: the rating
# --------------------------------------------------------------------------


def _match(eid: int, ts: int, home: int, away: int, hs: tuple[int, ...],
           as_: tuple[int, ...], comp: int = 1) -> vpm.VbMatch:
    return vpm.VbMatch(eid, ts, comp, home, away, False, hs, as_)


def _season(seed: int = 0) -> list[vpm.VbMatch]:
    rng = random.Random(seed)
    out = []
    for i in range(200):
        h, a = rng.sample(range(6), 2)
        # team 0 always wins 25-18 x 3; others 25-23 coin flips
        if 0 in (h, a):
            win, lose = (25, 25, 25), (18, 18, 18)
            hs, as_ = (win, lose) if h == 0 else (lose, win)
        else:
            hs, as_ = ((25, 23, 25), (23, 25, 23)) if rng.random() < 0.5 else (
                (23, 25, 23), (25, 23, 25))
        out.append(_match(i, 1_700_000_000 + i * 3600, h, a, hs, as_))
    return out


def test_rating_learns_the_strong_team_and_is_as_of() -> None:
    season = _season()
    rating = vpm.VbRating()
    for m in season:
        rating.update(m)
    assert rating.beliefs[0].mu > max(rating.beliefs[t].mu for t in range(1, 6)) + 0.2
    # the forecast of a match never reads its own result
    target = season[150]
    flipped = vpm.VbMatch(target.event_id, target.ts, target.competition,
                          target.home, target.away, False, target.away_sets,
                          target.home_sets)
    a = vpm.walk_forward(season, {target.event_id})[target.event_id]
    b = vpm.walk_forward([*season[:150], flipped, *season[151:]],
                         {target.event_id})[target.event_id]
    assert a == b


def test_new_team_prior_is_its_leagues_mean() -> None:
    rating = vpm.VbRating(vpm.VbParams(min_league_teams=2))
    for t, mu in ((1, 0.4), (2, 0.2)):
        rating.beliefs[t] = vpm._Belief(mu, 0.01, 0.0)
        rating.league.setdefault(7, set()).add(t)
    f = rating.forecast(_match(1, 10, 99, 1, (25,), (20,), comp=7))
    assert f.mu == pytest.approx(0.3 - 0.4 + rating.params.home)


def test_match_loglik_prefers_the_likely_result() -> None:
    f = vpm.VbForecast(mu=0.6, var=0.01, sideout=0.62, women=False)
    prm = vpm.VbParams()
    good = vpm.match_loglik(f, (25, 25, 25), (20, 21, 19), prm)
    bad = vpm.match_loglik(f, (20, 21, 19), (25, 25, 25), prm)
    assert good > bad


def _importers(module: str) -> list[str]:
    out = []
    for path in [*(REPO / "src" / "bet" / "sofa").glob("*.py"),
                 *(REPO / "scripts" / "sofa").glob("*.py")]:
        if path.name.startswith("measure_") or path.name == f"{module}.py":
            continue
        text = path.read_text(encoding="utf-8")
        if (f"import {module}" in text or f"{module} import" in text
                or f"{module} as " in text or f"\n    {module},\n" in text):
            out.append(path.name)
    return sorted(out)


def test_only_the_switched_readers_import_the_point_models() -> None:
    """epochs.VB_POINT_MODEL: SPORT_CONFIDENCE reads the rally model only
    through bet.sofa.vb_point_pricer; epochs.TENNIS_HANDICAP_POINT_MODEL:
    SHEET reads the handicap margins only through tennis_point_sheet."""
    assert _importers("volleyball_point_model") == ["vb_point_pricer.py"]
    assert _importers("vb_point_pricer") == [
        "backfill_vb_point_p.py", "fit_line_evidence.py",
        "run_sport_confidence.py"]
    sc = (REPO / "scripts" / "sofa" / "run_sport_confidence.py").read_text(
        encoding="utf-8")
    assert "epochs.vb_point_model(self._day, self.at)" in sc
