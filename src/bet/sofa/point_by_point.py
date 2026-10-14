"""Tennis point-by-point (Sofascore `/event/{id}/point-by-point`, cached in
sofa_event_extra as kind "point_by_point") read as an ordered list of games.

The payload holds, per set, every game with `score` = the games AFTER it
(`homeScore` / `awayScore`), `serving` (1 home / 2 away) and `scoring` (who
won it), and `points` = the running point score after each point except the
last (the game-winning point is implied by `scoring`). Sets and games come
newest first; `games()` returns them in play order.

This is what Superbet's "after N games" / "after N points" tennis markets
settle on (market_coverage tn.game_order, tn.points_in_game: 3,796 offered
2026-10-14), which the set scores in the listing cannot tell.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Game:
    set_no: int
    game_no: int
    server: int  # 1 home, 2 away
    winner: int  # 1 home, 2 away
    home_games: int  # games in the set after this one
    away_games: int
    points: tuple[tuple[str, str], ...]  # running score before the last point

    @property
    def held(self) -> bool:
        return self.server == self.winner


def games(payload: Mapping[str, Any] | None) -> list[Game] | None:
    """Every game in play order, or None when the payload holds none or a
    game lacks who served / who won (a partial feed is not a record)."""
    sets = (payload or {}).get("pointByPoint")
    if not sets:
        return None
    out: list[Game] = []
    for s in sorted(sets, key=lambda s: int(s.get("set") or 0)):
        for g in sorted(s.get("games") or [], key=lambda g: int(g.get("game") or 0)):
            score = g.get("score") or {}
            server, winner = score.get("serving"), score.get("scoring")
            if server not in (1, 2) or winner not in (1, 2):
                return None
            out.append(Game(
                set_no=int(s["set"]), game_no=int(g["game"]), server=int(server),
                winner=int(winner), home_games=int(score.get("homeScore") or 0),
                away_games=int(score.get("awayScore") or 0),
                points=tuple((str(p.get("homePoint")), str(p.get("awayPoint")))
                             for p in g.get("points") or [])))
    return out or None


def score_after(set_games: list[Game], n: int) -> tuple[int, int] | None:
    """(home, away) games of a set after its first n games; None if the set
    ended before n games were played."""
    if n < 1 or len(set_games) < n:
        return None
    g = set_games[n - 1]
    return g.home_games, g.away_games


def in_set(all_games: list[Game], set_no: int) -> list[Game]:
    return [g for g in all_games if g.set_no == set_no]
