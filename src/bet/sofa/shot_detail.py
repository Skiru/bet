"""A footballer's shots split the way Superbet's player markets split them -
outside the box, header, left foot, right foot, each as all shots and as shots
on target - read from Sofascore's `/event/{id}/shotmap` (sofa_event_extra,
kind "shotmap"). `/lineups` gives only the totals, which is why these markets
sat in unmapped_markets as NOT_COMPUTABLE until 2026-10-14.

Measured, not assumed (docs/sofa/history/RAPORT_LUKI_RYNKOW_2026-10-14.md):
- the box: Sofascore's coordinates run 0..100 from the goal line; a shot is
  outside the penalty area when x > OUTSIDE_X or y outside BOX_Y. On 45
  matches this reproduced the team statistic `totalShotsOutsideBox` on 87 of
  90 sides (x > 15.7, the geometric 16.5 m of 105 m: 69 of 90; > 16.5: 84;
  > 17.5: 82);
- the count: a player's shotmap shots equal his /lineups `totalShots` on
  3,013 of 3,045 player-matches;
- on target: `shotType` goal or save, as Sofascore's own "shots on target"
  (a blocked shot, a miss and the woodwork are not).
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

OUTSIDE_X = 17.0
BOX_Y = (20.4, 79.6)
ON_TARGET = frozenset({"goal", "save"})

# Superbet's market name (folded, as market_mapper folds) -> metric.
MARKET_NAMES: dict[str, str] = {
    "zawodnik - liczba strzalow spoza pola karnego": "player_shots_outside_box_for",
    "zawodnik - liczba celnych strzalow spoza pola karnego":
        "player_sot_outside_box_for",
    "zawodnik - liczba strzalow glowa": "player_headed_shots_for",
    "zawodnik - liczba celnych strzalow glowa": "player_sot_headed_for",
    "zawodnik - liczba strzalow lewa noga": "player_left_foot_shots_for",
    "zawodnik - liczba celnych strzalow lewa noga": "player_sot_left_foot_for",
    "zawodnik - liczba strzalow prawa noga": "player_right_foot_shots_for",
    "zawodnik - liczba celnych strzalow prawa noga": "player_sot_right_foot_for",
}
METRICS = tuple(sorted(set(MARKET_NAMES.values())))


def is_outside_box(shot: Mapping[str, Any]) -> bool:
    c = shot.get("playerCoordinates") or {}
    x, y = c.get("x"), c.get("y")
    if not isinstance(x, int | float) or not isinstance(y, int | float):
        return False
    return x > OUTSIDE_X or not BOX_Y[0] <= y <= BOX_Y[1]


def _selects(metric: str, shot: Mapping[str, Any]) -> bool:
    part = shot.get("bodyPart")
    if "outside_box" in metric:
        where = is_outside_box(shot)
    elif "headed" in metric:
        where = part == "head"
    elif "left_foot" in metric:
        where = part == "left-foot"
    else:
        where = part == "right-foot"
    if not where:
        return False
    return not metric.startswith("player_sot_") or shot.get("shotType") in ON_TARGET


def is_football_shotmap(shots: list[Any]) -> bool:
    """A football shotmap places every shot by `playerCoordinates`; a hockey
    one (same endpoint, same cache kind) has top-level x / y instead."""
    return all(isinstance(s, dict) and "playerCoordinates" in s for s in shots)


def player_counts(
    payload: Mapping[str, Any] | None, player_id: int
) -> dict[str, int] | None:
    """Every METRIC for one player in one match, or None when the shotmap is
    missing, empty or not a football one (a player with no shot in a match
    that HAS a football shotmap counts zero - an empty shotmap is not
    evidence of no shots)."""
    shots = (payload or {}).get("shotmap")
    if not shots or not is_football_shotmap(shots):
        return None
    mine = [s for s in shots if (s.get("player") or {}).get("id") == player_id]
    return {m: sum(1 for s in mine if _selects(m, s)) for m in METRICS}


# The estimator measured by scripts/sofa/measure_shot_detail.py: the player's
# last WINDOW starts, shrunk to his position's mean with K pseudo-starts, read
# through a Poisson. K and the position means are fitted per metric
# (config/sofa_shot_detail.json, scripts/sofa/fit_shot_detail.py); a
# position the file does not know reads the metric's all-positions mean.
WINDOW = 10
MIN_STARTS = 5


def shrunk_mean(values: list[float], pool_mean: float, k: float) -> float:
    """The player's mean pulled toward the pool by k pseudo-starts."""
    return (sum(values) + k * pool_mean) / (len(values) + k)


def p_over(mean: float, line: float) -> float:
    """P(count > line) for a Poisson count with this mean; line is N - 0.5."""
    k = int(line)
    term = math.exp(-mean)
    below = term
    for j in range(1, k + 1):
        term *= mean / j
        below += term
    return max(0.0, 1.0 - below)


def forecast(
    values: list[float], position: str | None, metric: str, line: float,
    fitted: Mapping[str, Any],
) -> float | None:
    """P(OVER line) for one player from his own starts (newest last), or None
    when he has fewer than MIN_STARTS or the file lacks the metric."""
    spec = (fitted.get("metrics") or {}).get(metric)
    if spec is None or len(values) < MIN_STARTS:
        return None
    pools = spec.get("pool") or {}
    pool = pools.get(position or "", spec.get("pool_all"))
    if pool is None:
        return None
    return p_over(shrunk_mean(values[-WINDOW:], float(pool), float(spec["k"])), line)
