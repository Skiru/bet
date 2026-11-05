"""bet.sofa.tennis_point_model: the bottom-up tennis model (plan B), offline.

Measured in docs/sofa/evidence/tennis_point_model_2026-11-05.md; SHEET reads
it only under epochs.TENNIS_POINT_MODEL (tests/sofa/test_tennis_point_wiring.py)."""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pytest

from bet.sofa.tennis_point_model import (
    LogitRating,
    MatchForecast,
    PointMatch,
    PointModel,
    RatingParams,
    SideForecast,
    SideServe,
    hold_probability,
    market_sim,
    nb_sf,
    parse_serve_stats,
    point_match_from_event,
    set_win_probability,
    simulate,
    tiebreak_probability,
    walk_forward,
)


def test_only_sheet_reads_the_model_and_only_through_the_switch() -> None:
    """epochs.TENNIS_POINT_MODEL: SHEET reads the model through
    bet.sofa.tennis_point_sheet (and the curve fit / backfill script); no
    other stage imports it."""
    root = Path(__file__).resolve().parents[2]
    readers = sorted(
        p.name for p in [*(root / "src" / "bet" / "sofa").glob("*.py"),
                         *(root / "scripts" / "sofa").glob("*.py")]
        if p.name not in ("tennis_point_model.py", "measure_tennis_point_model.py")
        and "tennis_point_model import" in p.read_text(encoding="utf-8")
    )
    assert readers == ["fit_tennis_point_curves.py", "run_sheet.py",
                       "tennis_point_sheet.py"]
    sheet = (root / "scripts" / "sofa" / "run_sheet.py").read_text(encoding="utf-8")
    assert "epochs.tennis_point_model(args.date)" in sheet


def test_hold_probability_known_values() -> None:
    assert hold_probability(0.5) == pytest.approx(0.5)
    # Textbook value: p = 0.6 holds 0.7357.
    assert hold_probability(0.6) == pytest.approx(0.7357, abs=1e-4)
    assert hold_probability(0.4) == pytest.approx(1 - 0.7357, abs=1e-4)


def test_tiebreak_and_set_symmetry() -> None:
    assert tiebreak_probability(0.6, 0.6) == pytest.approx(0.5)
    assert set_win_probability(0.62, 0.62) == pytest.approx(0.5, abs=1e-9)
    assert tiebreak_probability(0.7, 0.6) > 0.5
    assert set_win_probability(0.7, 0.6) > 0.5


def test_simulator_agrees_with_exact_set_probability() -> None:
    rng = np.random.default_rng(7)
    n = 40000
    pa, pb = np.full(n, 0.66), np.full(n, 0.60)
    sim = simulate(pa, pb, rng)
    exact = 0.5 * (set_win_probability(0.66, 0.60)
                   + 1 - set_win_probability(0.60, 0.66))
    won_set1 = (sim.games[:, 0, 0] > sim.games[:, 0, 1]).mean()
    assert won_set1 == pytest.approx(exact, abs=0.01)
    # Every set ends on a legal score; a third set only at one set all.
    for k in range(3):
        a, b = sim.games[:, k, 0], sim.games[:, k, 1]
        played = sim.sets_played > k
        hi, lo = np.maximum(a, b)[played], np.minimum(a, b)[played]
        assert (((hi == 6) & (lo <= 4)) | ((hi == 7) & ((lo == 5) | (lo == 6)))).all()
    assert set(np.unique(sim.sets_played)) <= {2, 3}


def test_simulator_serve_points_alternate() -> None:
    rng = np.random.default_rng(3)
    sim = simulate(np.full(5000, 0.62), np.full(5000, 0.62), rng)
    sp = sim.serve_points.sum(axis=(1, 2))
    # Equal players serve about equally often.
    a, b = sim.serve_points[:, :, 0].sum(), sim.serve_points[:, :, 1].sum()
    assert a / (a + b) == pytest.approx(0.5, abs=0.01)
    assert sp.min() >= 48  # 12 games of 4 points at least


def test_match_tiebreak_decider_counts_one_game() -> None:
    rng = np.random.default_rng(5)
    sim = simulate(np.full(4000, 0.6), np.full(4000, 0.6), rng, decider_tiebreak=True)
    third = sim.sets_played == 3
    assert third.any()
    assert (sim.games[third, 2, :].sum(axis=1) == 1).all()
    # The first two sets are full sets (found 2026-11-05 on the development
    # days: the second set had been played as a match tiebreak too).
    for k in (0, 1):
        assert (sim.games[:, k, :].sum(axis=1) >= 6).all()


def test_nb_sf_matches_poisson_limit_and_monotone() -> None:
    mean = np.array([5.0])
    pois = 1 - sum(math.exp(-5) * 5 ** k / math.factorial(k) for k in range(6))
    assert nb_sf(5.5, mean, math.inf)[0] == pytest.approx(pois)
    assert nb_sf(5.5, mean, 1e6)[0] == pytest.approx(pois, abs=1e-4)
    # Over-dispersion fattens the upper tail far from the mean.
    assert nb_sf(12.5, mean, 3.0)[0] > nb_sf(12.5, mean, math.inf)[0]


def _stats(home: tuple[int, int, int, int], away: tuple[int, int, int, int],
           aces: tuple[int, int] = (3, 1), dfs: tuple[int, int] = (2, 4)) -> str:
    # (first won, first played, second won, second played) per side.
    def item(key: str, h: str, a: str) -> dict[str, str]:
        return {"key": key, "home": h, "away": a}

    def frac(w: int, p: int) -> str:
        return f"{w}/{p} ({round(100 * w / p)}%)"

    hf, hp, hs, hsp = home
    af, ap, as_, asp = away
    items = [
        item("aces", str(aces[0]), str(aces[1])),
        item("doubleFaults", str(dfs[0]), str(dfs[1])),
        item("firstServePointsAccuracy", frac(hf, hp), frac(af, ap)),
        item("secondServePointsAccuracy", frac(hs, hsp), frac(as_, asp)),
        item("firstReturnPoints", frac(ap - af, ap), frac(hp - hf, hp)),
        item("secondReturnPoints", frac(asp - as_, asp), frac(hsp - hs, hsp)),
    ]
    set1 = [item("aces", "2", "0"), item("doubleFaults", "1", "3")]
    return json.dumps({"statistics": [
        {"period": "ALL", "groups": [{"statisticsItems": items}]},
        {"period": "1ST", "groups": [{"statisticsItems": set1}]},
    ]})


def test_parse_serve_stats_reads_counts_and_identities() -> None:
    parsed = parse_serve_stats(_stats((24, 31, 11, 17), (18, 37, 5, 10)))
    assert parsed is not None
    home, away = parsed
    assert (home.played, home.won, home.aces, home.dfs) == (48, 35, 3, 2)
    assert (away.played, away.won) == (47, 23)
    assert home.set_aces[:2] == (2, None)
    assert away.set_dfs[0] == 3


def test_parse_serve_stats_refuses_broken_identity() -> None:
    doc = json.loads(_stats((24, 31, 11, 17), (18, 37, 5, 10)))
    items = doc["statistics"][0]["groups"][0]["statisticsItems"]
    items[4]["home"] = "20/40 (50%)"  # return points no longer = serve points
    assert parse_serve_stats(json.dumps(doc)) is None
    assert parse_serve_stats(None) is None
    assert parse_serve_stats("not json") is None


def _event(eid: int, ts: int, status: str = "Ended",
           p3: tuple[int, int] | None = None) -> dict[str, object]:
    home_score: dict[str, object] = {"period1": 6, "period2": 3}
    away_score: dict[str, object] = {"period1": 4, "period2": 6}
    if p3:
        home_score["period3"], away_score["period3"] = p3
    return {
        "id": eid, "startTimestamp": ts, "winnerCode": 1,
        "status": {"type": "finished", "description": status},
        "tournament": {"name": "ITF M15", "uniqueTournament": {"id": 99},
                       "category": {"name": "ITF Men",
                                    "sport": {"slug": "tennis"}}},
        "homeTeam": {"id": 1, "type": 1, "name": "A"},
        "awayTeam": {"id": 2, "type": 1, "name": "B"},
        "homeScore": home_score, "awayScore": away_score,
        "groundType": "Clay",
    }


def test_point_match_from_event_reads_format_and_retirement() -> None:
    m = point_match_from_event(_event(1, 1000, p3=(10, 7)))
    assert m is not None
    assert m.match_tiebreak_decider and m.completed and m.tournament == 99
    assert m.sets[2] == (1, 0)
    retired = point_match_from_event(_event(2, 1000, status="Retired", p3=(2, 1)))
    assert retired is not None and not retired.completed
    walkover = point_match_from_event(_event(3, 1000, status="Walkover"))
    assert walkover is None


def _match(eid: int, ts: int, hw: int = 45, hp: int = 70, aw: int = 35,
           ap: int = 70) -> PointMatch:
    return PointMatch(
        event_id=eid, ts=ts, tier="TOUR", surface="hard", female=False,
        tournament=5, home_id=1, away_id=2, home_won=True,
        sets=((6, 3), (6, 4)), completed=True, best_of=3,
        match_tiebreak_decider=False,
        home=SideServe(hp, hw, 6, 2, (3, 3, None), (1, 1, None)),
        away=SideServe(ap, aw, 2, 4, (1, 1, None), (2, 2, None)))


def test_rating_learns_and_forecast_is_as_of() -> None:
    matches = [_match(i, 1000 + i * 86400) for i in range(30)]
    fc = walk_forward(matches, {0, 29})
    # Before any match both sides sit at the same prior.
    assert fc[0].home.serve_logit == pytest.approx(fc[0].away.serve_logit)
    # After 29 matches in which 1 out-served 2, 1 is rated the better server.
    assert fc[29].home.serve_logit > fc[29].away.serve_logit
    assert fc[29].home.ace_rate > fc[29].away.ace_rate
    assert fc[29].home.df_rate < fc[29].away.df_rate
    # The forecast of match 29 did not see match 29.
    model = PointModel()
    for m in matches[:29]:
        model.update(m)
    again = model.forecast(matches[29])
    assert again.home.serve_logit == pytest.approx(fc[29].home.serve_logit)


def test_retired_match_teaches_nothing() -> None:
    model = PointModel()
    m = _match(1, 1000)
    retired = PointMatch(**{**m.__dict__, "completed": False})
    model.update(retired)
    assert not model.serve.servers


def test_logit_rating_shrinks_with_prior_variance() -> None:
    tight = LogitRating(RatingParams(0.001, 0.0, 0.0, returner_var=0.001))
    loose = LogitRating(RatingParams(1.0, 0.0, 0.0, returner_var=1.0))
    for r in (tight, loose):
        r.update(1, 2, ("M", "TOUR", "hard"), None, 0, 80, 100)
    assert abs(tight.servers[1].mean) < abs(loose.servers[1].mean)


def _forecast(home_logit: float, away_logit: float) -> MatchForecast:
    side = SideForecast(home_logit, 0.0, 0.08, 0.04, 1000.0)
    other = SideForecast(away_logit, 0.0, 0.05, 0.05, 1000.0)
    return MatchForecast(side, other, False)


def test_market_sim_reads_consistent_markets() -> None:
    ms = market_sim(_forecast(0.6, 0.3), n=4000, seed=1)
    assert ms.p_over("games_total", None, 0.5) == 1.0
    p20 = ms.p_over("games_total", None, 20.5)
    p23 = ms.p_over("games_total", None, 23.5)
    assert p20 is not None and p23 is not None and p20 > p23
    p_sets = ms.p_over("sets_total", None, 2.5)
    assert p_sets is not None and 0.0 < p_sets < 0.6
    ah = ms.p_over("aces_for", 0, 4.5)
    aa = ms.p_over("aces_for", 1, 4.5)
    assert ah is not None and aa is not None and ah > aa
    tot = ms.p_over("aces_total", None, 4.5)
    assert tot is not None and tot > ah
    both = ms.p_over("serve_points_for", 0, 4.5)
    assert both is not None and both > ah
    s1 = ms.p_over("aces_set1_for", 0, 2.5)
    assert s1 is not None and 0 < s1 < 1
    assert ms.p_over("aces_for", None, 4.5) is None
    assert ms.p_over("most_aces", None, 0.5) is None


def test_market_sim_is_reproducible() -> None:
    a = market_sim(_forecast(0.5, 0.4), n=1000, seed=11)
    b = market_sim(_forecast(0.5, 0.4), n=1000, seed=11)
    assert a.p_over("games_total", None, 21.5) == b.p_over("games_total", None, 21.5)
