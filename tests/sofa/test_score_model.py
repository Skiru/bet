"""bet.sofa.score_model - the score model for the measured sports.

The model's probability of a line is the share of simulated games that the
SETTLE grader itself would call a win, so these tests pin the simulation's
shape (what a GameResult must look like for the grader to read it the way a
real game is read) and that the line probability goes through that grader.
"""

import random

import pytest

from bet.sofa import score_model as sm
from bet.sofa.football_rating import MIN_TEAM_MATCHES
from bet.sofa.shadow import MARKETS, SPORTS, GameResult, ShadowLine

HOCKEY = SPORTS["hockey"]
BASKETBALL = SPORTS["basketball"]
VOLLEYBALL = SPORTS["volleyball"]


def _event(slug, home, away, eid=1, ts=1000, desc="Ended", comp=5, name="League"):
    return {
        "id": eid, "startTimestamp": ts,
        "tournament": {"id": 9, "uniqueTournament": {"id": comp, "name": name},
                       "category": {"sport": {"slug": slug}}},
        "status": {"type": "finished", "description": desc},
        "homeTeam": {"id": 10, "gender": "M"}, "awayTeam": {"id": 20, "gender": "M"},
        "homeScore": {f"period{i + 1}": v for i, v in enumerate(home)},
        "awayScore": {f"period{i + 1}": v for i, v in enumerate(away)},
    }


def test_hockey_and_basketball_parse_their_regulation_periods():
    r = sm.parse_event(_event("ice-hockey", [1, 0, 2], [0, 0, 1]), HOCKEY)
    assert r is not None and r.values["p3_for"] == (2.0, 1.0)
    assert sm.parse_event(_event("ice-hockey", [1, 0], [0, 0]), HOCKEY) is None
    b = sm.parse_event(_event("basketball", [20, 22, 18, 25], [19, 21, 20, 30]),
                       BASKETBALL)
    assert b is not None and b.values["p4_for"] == (25.0, 30.0)


def test_volleyball_parses_points_per_set_and_refuses_a_level_set():
    v = sm.parse_event(_event("volleyball", [25, 23, 25, 25], [20, 25, 19, 22]),
                       VOLLEYBALL)
    assert v is not None and v.values[sm.VOLLEYBALL_METRIC] == (24.5, 21.5)
    assert sm.parse_event(_event("volleyball", [25, 24, 25], [20, 24, 19]),
                          VOLLEYBALL) is None


def test_friendlies_walkovers_and_negative_counts_are_not_history():
    assert sm.parse_event(_event("ice-hockey", [1, 0, 2], [0, 0, 1],
                                 name="Club Friendly Games"), HOCKEY) is None
    assert sm.parse_event(_event("ice-hockey", [1, 0, 2], [0, 0, 1],
                                 desc="Walkover"), HOCKEY) is None
    assert sm.parse_event(_event("ice-hockey", [1, -1, 2], [0, 0, 1]), HOCKEY) is None


def test_a_level_hockey_game_goes_to_overtime_and_the_winner_gets_the_goal():
    rng = random.Random(1)
    games = [sm._hockey(rng, [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]) for _ in range(50)]
    for g in games:  # 0-0 in regulation every time
        assert g.overtime and sum(g.t1_periods) == sum(g.t2_periods) == 0
        assert {g.t1_full, g.t2_full} == {0, 1}
        assert g.winner == ("T1" if g.t1_full > g.t2_full else "T2")


def test_basketball_never_ends_level():
    rng = random.Random(2)
    for _ in range(200):
        g = sm._basketball(rng, [20.0] * 4, [20.0] * 4, 6.0)
        assert g.t1_full != g.t2_full and len(g.t1_periods) == 4
        if not g.overtime:
            assert (g.t1_full, g.t2_full) == (sum(g.t1_periods), sum(g.t2_periods))


def test_a_volleyball_game_is_best_of_five_with_clear_sets():
    rng = random.Random(3)
    for _ in range(100):
        g = sm._volleyball(rng, 24.0, 22.0)
        assert max(g.t1_full, g.t2_full) == 3 and min(g.t1_full, g.t2_full) < 3
        for i, (a, b) in enumerate(zip(g.t1_periods, g.t2_periods, strict=True)):
            target = 15 if i == 4 else 25
            assert max(a, b) >= target and abs(a - b) >= 2


def _line(sport, family, side, line=None, subject="", period=0):
    market_id = next(mid for mid, spec in MARKETS[sport.key].items()
                     if spec.family == family)
    return ShadowLine("1", market_id, family, period, subject, line, side, 1.9)


def test_the_line_probability_is_the_graders_verdict():
    games = [GameResult((1, 1, 1), (0, 0, 0), 3, 0, "T1", False),
             GameResult((0, 0, 1), (1, 1, 1), 1, 3, "T2", False)]
    over = _line(HOCKEY, "total", "OVER", 3.5)
    assert sm.line_probability(over, games, HOCKEY) == pytest.approx(0.5)
    under_25 = _line(HOCKEY, "total", "UNDER", 2.5)
    assert sm.line_probability(under_25, games, HOCKEY) == 0.0
    # a push is left out, not counted as a loss
    over_3 = _line(HOCKEY, "total", "OVER", 3.0)
    assert sm.line_probability(over_3, games, HOCKEY) == 1.0


def test_players_have_no_model():
    from bet.sofa.shadow import PLAYER_MARKETS

    player = next(iter(PLAYER_MARKETS["hockey"]))
    line = ShadowLine("1", player, "player_points", 0, "x", 0.5, "OVER", 1.9)
    assert sm.line_probability(line, [], HOCKEY) is None


def test_the_model_rates_only_teams_with_history():
    history = []
    # a league rate needs 30 matches before any team is rated at all
    for i in range(80):
        history.append(sm.FootballResult(
            i, i, 5, 100 + i % 4, 200 + i % 4,
            {**{f"p{k}_for": (1.0, 0.8) for k in (1, 2, 3)},
             sm.REG_METRIC["hockey"]: (3.0, 2.4)}))
    model = sm.build_model(history, HOCKEY, cut_ts=10**9)
    assert model.expected(5, 100, 200) is not None
    assert model.expected(5, 100, 999) is None
    assert MIN_TEAM_MATCHES > 0


def test_periods_are_the_game_expectation_split_by_measured_shares():
    history = [sm.FootballResult(
        i, i, 5, 100 + i % 4, 200 + i % 4,
        {"p1_for": (1.0, 1.0), "p2_for": (1.0, 1.0), "p3_for": (2.0, 2.0),
         sm.REG_METRIC["hockey"]: (4.0, 4.0)}) for i in range(80)]
    model = sm.build_model(history, HOCKEY, cut_ts=10**9)
    exp = model.expected(5, 100, 200)
    assert exp is not None
    home, away = exp
    assert home == pytest.approx([1.0, 1.0, 2.0], rel=1e-6)
    assert sum(away) == pytest.approx(4.0, rel=1e-6)


def test_basketball_noise_is_fitted_by_moments_with_a_shared_game_shock():
    """A history whose two teams' quarters move together must come out with
    a game shock and a smaller independent quarter noise."""
    rng = random.Random(5)
    history = []
    for i in range(400):
        g = rng.gauss(0, 3.0)  # shared by both teams, every quarter
        hq = [20 + g + rng.gauss(0, 4.0) for _ in range(4)]
        aq = [19 + g + rng.gauss(0, 4.0) for _ in range(4)]
        vals = {f"p{k + 1}_for": (hq[k], aq[k]) for k in range(4)}
        vals[sm.REG_METRIC["basketball"]] = (sum(hq), sum(aq))
        history.append(sm.FootballResult(i, i * 3600, 5, 100 + i % 6, 200 + i % 6,
                                         vals))
    model = sm.build_model(history, BASKETBALL, cut_ts=10**9)
    prm = model.params
    assert prm.bb_game_sd is not None
    assert 2.0 < prm.bb_game_sd < 4.0
    assert 3.0 < prm.bb_quarter_sd < 5.0
    old = sm.build_model(history, BASKETBALL, cut_ts=10**9,
                         params=sm.SimParams(bb_fit_moments=False))
    assert old.params.bb_game_sd is None


def test_the_serve_model_keeps_the_ratings_point_share():
    for share in (0.45, 0.5, 0.56):
        pa, pb = sm.serve_probabilities(share, 0.62)
        pi = pb / (1 - pa + pb)
        assert pi * pa + (1 - pi) * pb == pytest.approx(share, abs=1e-6)
        assert pa < pb or share > 0.6  # the receiver is favoured on a rally
    rng = random.Random(9)
    pts = [0, 0]
    for _ in range(300):
        g = sm._volleyball(rng, 24.0, 22.0, sideout=0.62)
        pts[0] += sum(g.t1_periods)
        pts[1] += sum(g.t2_periods)
    assert pts[0] / sum(pts) == pytest.approx(24 / 46, abs=0.01)
