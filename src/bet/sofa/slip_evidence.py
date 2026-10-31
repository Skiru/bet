"""A chat slip leg's statistical evidence beside its price - display only.

The /kupon table shows every signal of a football count leg next to 1/odds:
the match-up (`dossier.matchups_for_legs`: own / conceded, or both sides'
games), and here the league's share of the line, the head-to-head meetings
and the referee's last games (cards / fouls totals). Every one is cut at the
match's kickoff (`dossier.team_games(before_ts=kickoff)` keeps only games
that started before it; the referee's games by their own start), so a past
day rebuilt reads what was known then.

Measured 2026-10-31 (`docs/sofa/evidence/kupon_od_nowa_2026-10-31.md`, the
backtest built these signals with these functions): none of them - alone,
k of n, all above the price, their mean, their spread - told a good leg from
a bad one at the same price, so they are never a gate, never a ranking.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from bet.sofa import dossier as ds

REFEREE_GAMES = 20  # the referee's newest cached games read
REFEREE_MIN = 8  # fewer: no referee cell
H2H_MIN = 2
METRIC_WORDS = ("card", "foul")  # the referee cell's metrics


def _hits(values: Sequence[float], line: float, direction: str) -> str | None:
    if not values:
        return None
    k = sum(1 for v in values if (v > line if direction == "OVER" else v < line))
    return f"{k}/{len(values)}"


def leg_values(metric: str, both: bool, side: str | None,
               value: Any) -> float | None:
    """One game's value from the leg's view: a joint reads min(own, rival),
    a side metric its subject's half ([home, away] from the home view)."""
    if isinstance(value, list):
        if not all(isinstance(v, int | float) for v in value) or len(value) != 2:
            return None
        if both:
            return float(min(value))
        if side is None:
            return None
        return float(value[0] if side == "home" else value[1])
    return float(value) if isinstance(value, int | float) else None


def evidence_for_legs(
    run: Path,
    legs: Iterable[Mapping[str, Any]],
    *,
    db_path: str | Path = ds.DB_PATH,
) -> dict[str, dict[str, str]]:
    """{dossier.matchup_key(leg): {"league", "h2h", "referee"}} for every
    football count leg of `legs` with both team ids in 02_fixtures.json; a
    cell with too few games is left out, never guessed."""
    by_event: dict[int, list[Mapping[str, Any]]] = defaultdict(list)
    for leg in legs:
        if (leg.get("sport") or "football") == "football" and ds.leg_metric(
                str(leg.get("market"))) is not None and isinstance(
                leg.get("sofascore_event_id"), int):
            by_event[int(leg["sofascore_event_id"])].append(leg)
    if not by_event or not Path(db_path).exists():
        return {}
    fixtures = {
        int(f["sofascore_event_id"]): f
        for f in ds._load(run / "02_fixtures.json") or []
        if isinstance(f, Mapping) and isinstance(f.get("sofascore_event_id"), int)
    }
    out: dict[str, dict[str, str]] = {}
    cache: dict[tuple[int, int], dict[str, Any]] = {}
    con = ds.connect(db_path)
    try:
        for event_id, these in by_event.items():
            fx = fixtures.get(event_id) or {}
            home, away = fx.get("home_entity_id"), fx.get("away_entity_id")
            kickoff = ds._parse_ts(fx.get("kickoff_utc"))
            if (not isinstance(home, int) or not isinstance(away, int)
                    or kickoff is None):
                continue
            out.update(_event_evidence(con, event_id, these, home, away, kickoff,
                                       {"home": fx.get("home_name"),
                                        "away": fx.get("away_name")}, cache))
    finally:
        con.close()
    return out


def _event_evidence(
    con: sqlite3.Connection,
    event_id: int,
    legs: Sequence[Mapping[str, Any]],
    home: int,
    away: int,
    kickoff: int,
    names: Mapping[str, str | None],
    cache: dict[tuple[int, int], dict[str, Any]],
) -> dict[str, dict[str, str]]:
    metrics = sorted({found[0] for x in legs
                      if (found := ds.leg_metric(str(x.get("market"))))})
    awarded_out = ds.awarded_out_at(kickoff)
    games = {"home": ds._metric_games(con, home, kickoff, metrics, cache, awarded_out),
             "away": ds._metric_games(con, away, kickoff, metrics, cache, awarded_out)}
    detail = ds.event_detail(con, event_id) or {}
    comps = ds._competitions_for(detail, games, {"home": home, "away": away}, con,
                                 kickoff)
    league = ds.league_rates(con, comps, kickoff, metrics, awarded_out)
    h2h = ds.head_to_head(con, home, away, kickoff, metrics=metrics,
                          awarded_out=awarded_out)
    referee = _referee_games(con, event_id, kickoff,
                             [m for m in metrics if not m.endswith("_for")])
    out: dict[str, dict[str, str]] = {}
    for leg in legs:
        found = ds.leg_metric(str(leg.get("market")))
        line, direction = leg.get("line"), str(leg.get("direction") or "")
        if found is None or not isinstance(line, int | float) or direction not in (
                "OVER", "UNDER"):
            continue
        metric, both = found
        side = (ds._side_of_subject(str(leg.get("subject") or ""), names)
                if metric.endswith("_for") and not both else None)
        cell: dict[str, str] = {}
        pool: list[float] = []
        for g in league.get("values") or []:
            if metric not in g:
                continue
            value = g[metric]
            if isinstance(value, list) and not both:
                pool += [float(v) for v in value if isinstance(v, int | float)]
            elif (v := leg_values(metric, both, side, value)) is not None:
                pool.append(v)
        text = _hits(pool, float(line), direction)
        if text and len(pool) >= ds.LEAGUE_RATE_MIN:
            cell["league"] = f"{text} ({league.get('competition') or 'liga'})"
        meetings = [v for r in h2h if metric in (r.get("metrics") or {})
                    if (v := leg_values(metric, both, side, r["metrics"][metric]))
                    is not None]
        text = _hits(meetings, float(line), direction)
        if len(meetings) >= H2H_MIN and text:
            cell["h2h"] = text
        if any(w in metric for w in METRIC_WORDS) and not metric.endswith("_for"):
            values = [float(g[metric]) for g in referee
                      if isinstance(g.get(metric), int | float)]
            if len(values) >= REFEREE_MIN and (
                    text := _hits(values, float(line), direction)):
                cell["referee"] = text
        if cell:
            out[ds.matchup_key(leg)] = cell
    return out


def _referee_games(
    con: sqlite3.Connection, event_id: int, kickoff: int, metrics: Sequence[str],
) -> list[dict[str, Any]]:
    """The fixture's referee's newest REFEREE_GAMES cached games that started
    before the kickoff, each {metric: match total}; [] without a referee."""
    if not metrics:
        return []
    try:
        row = con.execute(
            "SELECT referee_id FROM sofa_event_referee WHERE event_id = ?",
            (event_id,)).fetchone()
    except sqlite3.OperationalError:
        return []
    if not row or row[0] is None:
        return []
    out: list[dict[str, Any]] = []
    for (eid,) in con.execute(
            "SELECT event_id FROM sofa_event_referee WHERE referee_id = ? "
            "AND start_ts < ? AND event_id <> ? ORDER BY start_ts DESC LIMIT ?",
            (row[0], kickoff, event_id, REFEREE_GAMES * 2)):
        values = ds.meeting_metrics(con, {"id": eid}, -1, metrics, "football")
        values = {m: v for m, v in values.items() if isinstance(v, int | float)}
        if values:
            out.append(values)
        if len(out) >= REFEREE_GAMES:
            break
    return out
