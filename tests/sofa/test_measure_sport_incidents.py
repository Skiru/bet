"""measure_sport_incidents (2026-10-14): the order outcomes read from
Sofascore incidents and the model's probabilities for them - offline."""

from __future__ import annotations

import math
import random

import pytest

from scripts.sofa import measure_sport_incidents as ms


def _goal(t: int, home: bool, hs: int, as_: int, secs: int | None = None) -> dict:
    g = {"incidentType": "goal", "time": t, "isHome": home,
         "homeScore": hs, "awayScore": as_}
    if secs is not None:
        g["timeSeconds"] = secs
    return g


def test_hockey_goals_follow_the_running_score_not_the_clock() -> None:
    # 16836848-like: the clock runs backwards inside the period, the running
    # score (and the ids) forwards; the last goal is overtime's
    payload = {"incidents": [
        _goal(63, True, 3, 2), {"incidentType": "period", "text": "3rd"},
        _goal(45, False, 2, 2), _goal(30, True, 2, 1), _goal(4, False, 1, 1),
        _goal(19, True, 1, 0, secs=19 * 60 + 5)]}
    goals = ms.hockey_goals(payload)
    assert goals == ["H", "A", "H", "A", "H"]
    assert ms.first_goal(goals, 4) == "H"
    assert ms.first_goal(goals, 0) == "N"  # a 0-0 regulation / period 1
    assert ms.first_goal([], 0) == "N"
    # a running score that skips a goal, a side the score contradicts
    assert ms.hockey_goals({"incidents": [_goal(5, True, 2, 0)]}) is None
    assert ms.hockey_goals({"incidents": [_goal(5, False, 1, 0)]}) is None
    assert ms.hockey_goals({"incidents": [{"incidentType": "goal", "time": 5}]}) is None


def test_scoring_plays_and_race() -> None:
    inc = [{"incidentType": "goal", "homeScore": h, "awayScore": a}
           for h, a in [(0, 2), (3, 2), (3, 4), (4, 4), (6, 4), (6, 7)]]
    plays = ms.scoring_plays({"incidents": list(reversed(inc))})
    assert plays == [(0, 2), (3, 2), (3, 4), (4, 4), (6, 4), (6, 7)]
    assert ms.race_winner(plays, 3) == "H"
    assert ms.race_winner(plays, 7) == "A"
    assert ms.race_winner(plays, 2) == "A"
    assert ms.race_winner(plays, 10) is None
    assert ms.play_sizes(plays) == [2, 3, 2, 1, 2, 3]
    # a jump of 4 points in one play: a gap in the feed
    bad = [{"incidentType": "goal", "homeScore": 4, "awayScore": 0}]
    assert ms.scoring_plays({"incidents": bad}) is None


def test_hockey_first_goal_probabilities() -> None:
    p = ms.hockey_first_goal_probs([1.0, 1.0, 1.0], [0.5, 0.5, 0.5], 3)
    assert p["N"] == pytest.approx(math.exp(-4.5))
    assert p["H"] == pytest.approx(2 * p["A"])
    assert sum(p.values()) == pytest.approx(1.0)
    p1 = ms.hockey_first_goal_probs([1.0, 1.0, 1.0], [0.5, 0.5, 0.5], 1)
    assert p1["N"] == pytest.approx(math.exp(-1.5))


def test_race_probabilities() -> None:
    rng = random.Random(1)
    even = ms.race_probs([0.5] * 4000, [1.0, 1.0, 1.0], (10, 20), rng)
    assert even[10] == pytest.approx(0.5, abs=0.03)
    strong = ms.race_probs([0.6] * 4000, [1.0, 1.0, 1.0], (10, 30), rng)
    assert 0.5 < strong[10] < strong[30]


def test_market_base_is_the_running_share_before_the_game() -> None:
    m = ms.Market(("H", "A"))
    m.add({"H": 0.7, "A": 0.3}, "H")
    m.add({"H": 0.7, "A": 0.3}, "H")
    assert m.rows[0][1] == {"H": 0.5, "A": 0.5}
    assert m.rows[1][1] == pytest.approx({"H": 2 / 3, "A": 1 / 3})
    s = ms.summarise(m)
    assert s["games"] == 2 and s["share_ge_070"] == 0.5
    assert s["ge_070"]["n"] == 2 and s["ge_070"]["realised"] == 1.0


def _hk_event(eid: int, ts: int, home: int, away: int,
              hp: tuple[int, int, int], ap: tuple[int, int, int]) -> dict:
    score = {f"period{i + 1}": v for i, v in enumerate(hp)}
    ascore = {f"period{i + 1}": v for i, v in enumerate(ap)}
    score["current"], ascore["current"] = sum(hp), sum(ap)
    return {"id": eid, "startTimestamp": ts,
            "tournament": {"id": 5, "name": "Liga",
                           "uniqueTournament": {"id": 5, "name": "Liga"},
                           "category": {"sport": {"slug": "ice-hockey"}}},
            "status": {"type": "finished", "description": "Ended"},
            "winnerCode": 1 if sum(hp) > sum(ap) else 2,
            "homeTeam": {"id": home}, "awayTeam": {"id": away},
            "homeScore": score, "awayScore": ascore}


def test_replay_scores_only_games_with_goal_detail_one_step_ahead() -> None:
    from bet.sofa.shadow import SPORTS
    from bet.sofa.sport_confidence import parse_history

    events = {}
    teams = (1, 2, 3, 4)
    eid = 0
    for day in range(60):
        for k in range(2):
            eid += 1
            home, away = teams[(day + 2 * k) % 4], teams[(day + 2 * k + 1) % 4]
            events[eid] = _hk_event(eid, 1_000_000 + day * 86400 + k, home, away,
                                    (1, 1, 1), (0, 1, 0))
    history = parse_history(events, SPORTS["hockey"])
    assert len(history) == 120
    # the last two games: one with goal detail (home scores first), one with
    # periods only
    goals = [_goal(5, True, 1, 0), _goal(25, True, 2, 0), _goal(30, False, 2, 1),
             _goal(45, True, 3, 1)]
    incidents = {119: {"incidents": goals},
                 120: {"incidents": [{"incidentType": "period", "text": "1st"}]}}
    markets, stats = ms.replay(history, SPORTS["hockey"], incidents,
                               dist_start_ts=1_000_000 + 50 * 86400)
    assert stats["scored"] == 1 and stats["no_score_detail"] == 1, stats
    ((model_p, _, outcome),) = markets["first_goal"].rows
    assert outcome == "H" and sum(model_p.values()) == pytest.approx(1.0)
    assert stats["dist"]["first_goal"]["side_rows"] == 2 * 20
