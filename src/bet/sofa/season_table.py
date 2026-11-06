"""The season table as of a match, from our own cached results (item 5 of the
refit 2026-11-05, docs/sofa/evidence/refit_replay_2026-11-05.md section 6).

A (competition, season) table counts every rated finished game noted before
the forecast - nothing fetched, nothing after the start. A fixture reads its
sides' rows in the competition's newest season the table has seen (a fixture
carries no season id; a new season restarts at zero games, where d is 0).

d (the frozen rule): the mean of three standardised differences home - away
- points per game (football 3 / 1 / 0, basketball the win share), table
position as (place - 1) / (teams - 1) with the sign turned so that higher is
better, and score difference per game - times n / (n + SHRINK_GAMES) with n
the fewer games of the two sides; 0 below MIN_GAMES. The centre then moves by
exp(+w d / 2) for the home side and exp(-w d / 2) for the away side.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

MIN_GAMES = 3
SHRINK_GAMES = 5.0


@dataclass(frozen=True)
class TableScales:
    """The standard deviations of the three differences, measured on the
    training window (one per sport); a difference is divided by its own."""

    ppg: float
    position: float
    diff: float


@dataclass
class _Row:
    games: int = 0
    points: float = 0.0
    diff: float = 0.0


@dataclass
class SeasonTable:
    """Rows by (competition, season); `win_points` (3.0 football, 1.0 a win
    share) and `draw_points` (1.0 football, 0.5 never used by basketball)."""

    win_points: float
    draw_points: float
    rows: dict[tuple[int, int], dict[int, _Row]] = field(default_factory=dict)
    # competition -> its newest season seen (by the game's start)
    newest: dict[int, tuple[int, int]] = field(default_factory=dict)

    def note(self, competition: int, season: int | None, home: int, away: int,
             home_score: float, away_score: float, ts: int) -> None:
        """Count one finished game (a game with no season id is not)."""
        if season is None:
            return
        seen = self.newest.get(competition)
        if seen is None or ts >= seen[0]:
            # only a later start moves the competition's season on
            self.newest[competition] = (ts, season)
        table = self.rows.setdefault((competition, season), {})
        for team, own, other in ((home, home_score, away_score),
                                 (away, away_score, home_score)):
            row = table.setdefault(team, _Row())
            row.games += 1
            row.diff += own - other
            if own > other:
                row.points += self.win_points
            elif own == other:
                row.points += self.draw_points

    def _season(self, competition: int) -> dict[int, _Row] | None:
        seen = self.newest.get(competition)
        return None if seen is None else self.rows.get((competition, seen[1]))

    def raw(self, competition: int, home: int, away: int
            ) -> tuple[float, float, float, int] | None:
        """(ppg diff, position diff, score diff per game, fewer games) home -
        away in the competition's newest season, or None when either side
        has no row there."""
        table = self._season(competition)
        if table is None or home not in table or away not in table:
            return None
        h, a = table[home], table[away]
        if h.games == 0 or a.games == 0:
            return None
        order = sorted(table, key=lambda t: (-table[t].points / table[t].games,
                                             -table[t].diff / table[t].games, t))
        span = max(len(order) - 1, 1)
        # higher is better: the first place reads 1, the last 0
        pos = {t: 1.0 - i / span for i, t in enumerate(order)}
        return (h.points / h.games - a.points / a.games,
                pos[home] - pos[away],
                h.diff / h.games - a.diff / a.games,
                min(h.games, a.games))

    def d(self, competition: int, home: int, away: int,
          scales: TableScales) -> float:
        """The frozen composite (module docstring); 0 without a table read."""
        got = self.raw(competition, home, away)
        if got is None:
            return 0.0
        ppg, position, diff, n = got
        if n < MIN_GAMES:
            return 0.0
        z = (ppg / scales.ppg + position / scales.position
             + diff / scales.diff) / 3.0
        return z * n / (n + SHRINK_GAMES)


def adjust(home_centre: float, away_centre: float, d: float, w: float
           ) -> tuple[float, float]:
    """The table's centre adjustment: exp(+w d / 2) home, exp(-w d / 2) away."""
    if d == 0.0 or w == 0.0:
        return home_centre, away_centre
    f = math.exp(w * d / 2.0)
    return home_centre * f, away_centre / f
