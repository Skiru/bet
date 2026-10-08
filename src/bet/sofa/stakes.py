"""What a football match is played for - a context flag, never a gate.

2026-10-07, Internacional - Corinthians: a relegation six-pointer, and the
page carried Corinthians' cards under 4.5 (0.88) beside the total cards over
3.5 (0.81). The analyst wrote "relegation stakes not in artifacts (caveat)":
the stakes were not in the artifacts. They are now, from what the pipeline
already holds - every finished football match of the history
(`football_rating.FootballResult`) - with no new data source.

A league season's table is rebuilt from the matches played before the kickoff.
A match is

* `STAKES_SIX_POINTER` when both clubs stand within `NEAR_POINTS` of the
  relegation line (halfway between the last safe club and the first one in the
  zone), and
* `STAKES_TOP4` when both stand within `NEAR_POINTS` of the line between 4th
  and 5th,

in a league of at least `MIN_TEAMS` clubs with at least `MIN_PROGRESS` of its
rounds played. The zone is three clubs in a league of up to 16 and four in a
larger one - an approximation: leagues with play-offs, splits and promotion
rounds are read as one table.

Measured (scripts/sofa/measure_peer_choice.py, section stakes; 23,172 matches
with statistics in 476 league-seasons, residual against the league-season
mean of the matches that are not flagged, bootstrap over league-seasons):
a six-pointer has +0.20 cards [+0.06, +0.33], +0.86 fouls [+0.43, +1.30],
-0.15 goals [-0.25, -0.05] and -0.96 shots [-1.36, -0.56] (corners -0.17
[-0.36, +0.04]: not distinguishable from nothing, so not in EFFECT); a top-4
contest +0.22 cards [+0.08, +0.38] and -0.19 goals [-0.28, -0.10] (fouls,
shots and corners not distinguishable). That is 0.08-0.16 of a standard
deviation: real, and small. It is shown beside
the leg, in the direction it pushes it, and **never moves a confidence or
gates a leg** (the same footing as `schedule`'s MAKEUP_FIXTURE / LONG_LAYOFF /
CONGESTED). Not measured: that the effect survives the weakness of the clubs
that fill a relegation zone (the residual is against the league, not against
the clubs' own samples) - which is why it is not a correction.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

NEAR_POINTS = 3.0
MIN_TEAMS = 12
MIN_PROGRESS = 0.55
SIX_POINTER = "STAKES_SIX_POINTER"
TOP4 = "STAKES_TOP4"

# The direction the measured effect pushes a count, for the leg's note.
# Keys are the football metrics' families; "+" = more of it in such a match.
EFFECT = {
    SIX_POINTER: {"cards": "+", "fouls": "+", "goals": "-", "shots": "-"},
    TOP4: {"cards": "+", "goals": "-"},
}


def _family(market: str) -> str:
    return market.split("_", 1)[0]


def build_tables(
    history: Iterable[Any],
) -> dict[tuple[int, int], list[tuple[int, int, int, int, int]]]:
    """(competition, season) -> its finished matches in time order, as
    (ts, home_id, away_id, home_goals, away_goals). `history` is
    FootballResult-like: event_id, ts, competition_id, season_id, home_id,
    away_id, values['goals_for'] = (home, away)."""
    out: dict[tuple[int, int], list[tuple[int, int, int, int, int]]] = defaultdict(list)
    for r in history:
        season = getattr(r, "season_id", None)
        goals = (getattr(r, "values", None) or {}).get("goals_for")
        if season is None or goals is None:
            continue
        out[(int(r.competition_id), int(season))].append(
            (int(r.ts), int(r.home_id), int(r.away_id), int(goals[0]), int(goals[1])))
    for matches in out.values():
        matches.sort()
    return out


def _table(matches: Sequence[tuple[int, int, int, int, int]], before_ts: int,
           ) -> tuple[dict[int, int], dict[int, int]]:
    pts: dict[int, int] = defaultdict(int)
    played: dict[int, int] = defaultdict(int)
    for ts, h, a, hg, ag in matches:
        if ts >= before_ts:
            break
        pts[h] += 3 if hg > ag else 1 if hg == ag else 0
        pts[a] += 3 if ag > hg else 1 if hg == ag else 0
        played[h] += 1
        played[a] += 1
    return dict(pts), dict(played)


def flags(
    tables: Mapping[tuple[int, int], Sequence[tuple[int, int, int, int, int]]],
    competition_id: int, season_id: int | None, home_id: int, away_id: int,
    kickoff_ts: int,
) -> list[str]:
    """STAKES_* for one fixture, or []."""
    if season_id is None:
        return []
    matches = tables.get((int(competition_id), int(season_id)))
    if not matches:
        return []
    pts, played = _table(matches, kickoff_ts)
    n = len(pts)
    if n < MIN_TEAMS or home_id not in pts or away_id not in pts:
        return []
    full = 2 * (n - 1)
    progress = sum(played.values()) / n / full
    if progress < MIN_PROGRESS:
        return []
    order = sorted(pts, key=lambda t: -pts[t])
    zone = 3 if n <= 16 else 4
    line = (pts[order[n - zone - 1]] + pts[order[n - zone]]) / 2
    top = (pts[order[3]] + pts[order[4]]) / 2
    out: list[str] = []
    if all(abs(pts[t] - line) <= NEAR_POINTS for t in (home_id, away_id)):
        out.append(f"{SIX_POINTER}({progress:.0%} sezonu)")
    if all(abs(pts[t] - top) <= NEAR_POINTS for t in (home_id, away_id)):
        out.append(f"{TOP4}({progress:.0%} sezonu)")
    return out


def effect_note(flag_list: Sequence[str], market: str, direction: str) -> str:
    """Which way the measured effect pushes this leg: '' when it says
    nothing about the market, 'za' (for the leg) or 'przeciw'."""
    fam = _family(market)
    plus_means_over = direction == "OVER"
    for f in flag_list:
        key = f.split("(", 1)[0]
        sign = EFFECT.get(key, {}).get(fam)
        if sign is None:
            continue
        pushes_over = sign == "+"
        return "za" if pushes_over == plus_means_over else "przeciw"
    return ""


Tables = dict[tuple[int, int], list[tuple[int, int, int, int, int]]]


def load_tables(path: Any) -> Tables | None:
    """The league tables' matches from the parsed football history SHEET left
    on disk (`data/cache/football_history.pkl`, `football_rating.load_history`),
    read without the fingerprint check (which counts the whole database): the
    table of a day's fixtures is the one as of the day's SHEET. None when the
    pickle is absent or unreadable - the flags are then simply not shown."""
    import pickle
    from pathlib import Path

    try:
        _fp, history = pickle.loads(Path(path).read_bytes())
    except (OSError, pickle.PickleError, EOFError, ValueError, TypeError,
            AttributeError, ImportError):
        return None
    return build_tables(history)


def for_day(fixtures: Iterable[Mapping[str, Any]],
            tables: Mapping[tuple[int, int], Sequence[tuple[int, int, int, int, int]]],
            ) -> dict[int, list[str]]:
    """sofascore_event_id -> STAKES_* flags, for the day's football fixtures
    that have any (02_fixtures.json rows)."""
    from datetime import datetime

    out: dict[int, list[str]] = {}
    for f in fixtures:
        if f.get("sport") != "football" or not f.get("kickoff_utc"):
            continue
        try:
            ts = int(datetime.fromisoformat(
                str(f["kickoff_utc"]).replace("Z", "+00:00")).timestamp())
            got = flags(tables, int(f["competition_id"]), f.get("season_id"),
                        int(f["home_entity_id"]), int(f["away_entity_id"]), ts)
        except (KeyError, TypeError, ValueError):
            continue
        if got:
            out[int(f["sofascore_event_id"])] = got
    return out
