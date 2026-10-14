"""bet.sofa.point_by_point on a real payload: Svyatoslav Gulin - Franco
Agamenone, 2026-10-13 (Sofascore 17318393), pinned against the set scores
Sofascore's own event detail gives (7-5, 6-2)."""

from __future__ import annotations

import json
from pathlib import Path

from bet.sofa import point_by_point as pbp

GOLDEN = (Path(__file__).parent / "golden"
          / "point_by_point_gulin_agamenone_2026-10-13.json")


def _games() -> list[pbp.Game]:
    got = pbp.games(json.loads(GOLDEN.read_text()))
    assert got is not None
    return got


def test_games_in_play_order_end_on_the_set_scores() -> None:
    g = _games()
    assert len(g) == 20
    s1, s2 = pbp.in_set(g, 1), pbp.in_set(g, 2)
    assert [x.game_no for x in s1] == list(range(1, 13))
    assert (s1[-1].home_games, s1[-1].away_games) == (7, 5)
    assert (s2[-1].home_games, s2[-1].away_games) == (6, 2)


def test_first_games_server_winner_and_score_after() -> None:
    s1 = pbp.in_set(_games(), 1)
    first = s1[0]
    assert (first.server, first.winner, first.held) == (2, 2, True)
    assert first.points[-1] == ("15", "40")  # the winning point is implied
    assert s1[1].server == 1  # service alternates
    assert pbp.score_after(s1, 4) == (2, 2)
    assert pbp.score_after(s1, 13) is None
    assert pbp.score_after(s1, 0) is None


def test_partial_feed_is_not_a_record() -> None:
    assert pbp.games(None) is None
    assert pbp.games({"pointByPoint": []}) is None
    bad = {"pointByPoint": [{"set": 1, "games": [{"game": 1, "score": {}}]}]}
    assert pbp.games(bad) is None
