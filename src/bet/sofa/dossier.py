"""A match dossier for the analysts: every pre-match fact the cache holds.

Operator 2026-10-20: an analyst read is more than identity and price - form,
rest, the table, head-to-head, the venue and its weather hour, the referee,
the ranking, the roster, how the Superbet lines moved, then a web pass for
what no statistic holds (news, conditions, morale, opinions). This module
gathers the first half **offline** (data/sofa.db read-only and the day's
artifacts; no request) into `runs/sofa/<d>/dossier/<sport>_<event id>.json`,
one file per match, and names the second half as a web checklist with the
match's own city, local hour and names filled in. Head-to-head is the one
block asked of Sofascore beforehand: the read-set writers fetch it into
`runs/sofa/<d>/h2h.json` (`bet.sofa.h2h`, operator 2026-10-21 - the cached
listings alone missed Real Madrid - RB Leipzig's four meetings); a match whose
h2h was not answered says so and the web checklist asks for it.

Display only: nothing here feeds a confidence, a gate or the coupon. Every
block says what it was built from; a block the cache cannot fill says so
(`missing`), never a guess. The league table is rebuilt from cached team
listings (both sides, then their opponents in the same season) - complete
only as far as those listings are, and it says how many games it counted.
"""

from __future__ import annotations

import json
import os
import sqlite3
import statistics
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from bet.sofa import h2h as h2h_fetch
from bet.sofa.comparability import is_friendly_event
from bet.sofa.contracts import GapReason
from bet.sofa.listing_index import entity_indexed_events, has_index
from bet.sofa.metrics import (
    CARD_INCIDENT_SCOPES,
    FOOTBALL_METRICS,
    TENNIS_METRICS,
    extract_flat_statistics,
    extract_metric,
)
from bet.sofa.settle import venue_timezone

SCHEMA_VERSION = 1
FORM_N = 10  # last games per side
H2H_N = 6
H2H_SCAN = 200  # a side's listed games searched for the opponent
TABLE_MAX_TEAMS = 40  # listings walked to rebuild a table
TABLE_SCAN = 80  # games per listing walked for the table
MARKET_ROWS_MAX = 160  # Superbet line rows per match
CS2_SERIES_N = 10
CS2_MAP_DAYS = 90
CS2_ROSTER_SERIES = 6
LOCAL_ZONE = ZoneInfo("Europe/Warsaw")
DB_PATH = os.environ.get("SOFA_DB_PATH", "data/sofa.db")
# Indoor sports: a weather line says nothing of the court.
INDOOR = frozenset({"basketball", "volleyball", "hockey", "cs2"})
TEAM_SPORTS = frozenset({"football", "hockey", "basketball", "volleyball"})


def connect(db_path: str | Path = DB_PATH) -> sqlite3.Connection:
    """Read-only; the daily loops keep writing beside it."""
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    con.execute("PRAGMA busy_timeout = 60000")
    return con


def dossier_path(run: Path, sport: str, event_id: int) -> Path:
    return run / "dossier" / f"{sport}_{event_id}.json"


# --- small readers ---------------------------------------------------------


def _iso(ts: int | float | None, zone: Any = UTC) -> str | None:
    if not isinstance(ts, int | float):
        return None
    return datetime.fromtimestamp(ts, tz=zone).strftime("%Y-%m-%d %H:%M")


def _parse_ts(value: object) -> int | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return int(dt.timestamp())


def _name(node: object) -> str | None:
    if isinstance(node, Mapping):
        value = node.get("name")
        return str(value) if value is not None else None
    return None


def _country(node: object) -> str | None:
    if isinstance(node, Mapping):
        country = node.get("country")
        if isinstance(country, Mapping) and country.get("name"):
            return str(country["name"])
    return None


def event_detail(con: sqlite3.Connection, event_id: int) -> dict[str, Any] | None:
    """The cached /event payload (TTL ignored: a pre-match fact sheet)."""
    try:
        row = con.execute(
            "SELECT detail_json FROM sofa_event_detail WHERE sofascore_event_id = ?",
            (event_id,),
        ).fetchone()
    except sqlite3.OperationalError:
        return None
    if not row:
        return None
    try:
        payload = json.loads(row[0])
    except (TypeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    event = payload.get("event", payload)
    return event if isinstance(event, dict) else None


def team_games(
    con: sqlite3.Connection, team_id: int, before_ts: int, limit: int
) -> list[dict[str, Any]]:
    """The newest `limit` cached games of one side before `before_ts`, newest
    first: the listing index, then the side's raw `last` pages (a page not yet
    indexed). Unfinished games are left out; friendlies kept (marked)."""
    found: dict[int, dict[str, Any]] = {}
    if has_index(con):
        for event in entity_indexed_events(con, team_id, "last", before_ts, limit * 2):
            if isinstance(event.get("id"), int):
                found[event["id"]] = event
    try:
        pages = con.execute(
            "SELECT events_json FROM sofa_entity_events "
            "WHERE sofascore_entity_id = ? AND kind = 'last'",
            (team_id,),
        ).fetchall()
    except sqlite3.OperationalError:
        pages = []
    for (events_json,) in pages:
        try:
            events = json.loads(events_json).get("events", [])
        except (TypeError, ValueError, AttributeError):
            continue
        for event in events:
            if isinstance(event, dict) and isinstance(event.get("id"), int):
                found.setdefault(event["id"], event)
    games = [
        e
        for e in found.values()
        if isinstance(e.get("startTimestamp"), int)
        and e["startTimestamp"] < before_ts
        and (e.get("status") or {}).get("type") == "finished"
    ]
    games.sort(key=lambda e: (e["startTimestamp"], e["id"]), reverse=True)
    return games[:limit]


def _periods(score: Mapping[str, Any]) -> list[int]:
    out: list[int] = []
    for n in range(1, 10):
        value = score.get(f"period{n}")
        if not isinstance(value, int):
            break
        out.append(value)
    return out


def game_row(event: Mapping[str, Any], team_id: int) -> dict[str, Any]:
    """One past game from one side's view."""
    home = (event.get("homeTeam") or {}).get("id") == team_id
    own, opp = ("homeTeam", "awayTeam") if home else ("awayTeam", "homeTeam")
    own_s = event.get("homeScore" if home else "awayScore") or {}
    opp_s = event.get("awayScore" if home else "homeScore") or {}
    winner = event.get("winnerCode")
    result = None
    if winner == 3:
        result = "R"
    elif winner in (1, 2):
        result = "W" if (winner == 1) == home else "P"
    tournament = event.get("tournament") or {}
    unique = tournament.get("uniqueTournament") or {}
    row: dict[str, Any] = {
        "date": _iso(event.get("startTimestamp")),
        "competition": unique.get("name") or tournament.get("name"),
        "venue": "dom" if home else "wyjazd",
        "opponent": _name(event.get(opp)),
        "score": [own_s.get("current"), opp_s.get("current")],
        "result": result,
    }
    if own_s.get("normaltime") is not None and own_s.get("normaltime") != own_s.get(
        "current"
    ):
        row["normaltime"] = [own_s.get("normaltime"), opp_s.get("normaltime")]
    own_p, opp_p = _periods(own_s), _periods(opp_s)
    # CS2 listings carry each map as a 1-0 "period" padded to five: the
    # cs2 block reads the maps themselves.
    esports = ((tournament.get("category") or {}).get("sport") or {}).get(
        "slug"
    ) == "esports"
    if own_p and len(own_p) == len(opp_p) and not esports:
        row["periods"] = [[a, b] for a, b in zip(own_p, opp_p, strict=True)]
    status = (event.get("status") or {}).get("description")
    if status and status not in ("Ended", "FT"):
        row["status"] = status
    if is_friendly_event(event):
        row["friendly"] = True
    return row


def side_summary(
    rows: Sequence[Mapping[str, Any]],
    games: Sequence[Mapping[str, Any]],
    kickoff_ts: int,
) -> dict[str, Any]:
    """Form, rest and averages over the listed games (newest first)."""
    out: dict[str, Any] = {"n": len(rows)}
    if not rows:
        return out
    results = [r["result"] for r in rows if r.get("result")]
    out["form"] = "".join(results)
    out["record"] = {k: results.count(k) for k in ("W", "R", "P")}
    streak = 0
    for r in results:
        if r != results[0]:
            break
        streak += 1
    out["streak"] = f"{results[0]}x{streak}" if results else None
    scores = [
        r["score"]
        for r in rows
        if all(isinstance(v, int | float) for v in r.get("score", []))
    ]
    if scores:
        out["avg_for"] = round(statistics.fmean(s[0] for s in scores), 2)
        out["avg_against"] = round(statistics.fmean(s[1] for s in scores), 2)
        out["totals"] = [s[0] + s[1] for s in scores]
    for where in ("dom", "wyjazd"):
        part = [
            r["result"] for r in rows if r.get("venue") == where and r.get("result")
        ]
        if part:
            out[f"record_{where}"] = {k: part.count(k) for k in ("W", "R", "P")}
    starts = [int(g["startTimestamp"]) for g in games]
    out["rest_days"] = round((kickoff_ts - starts[0]) / 86400, 1)
    out["games_7d"] = sum(kickoff_ts - s <= 7 * 86400 for s in starts)
    out["games_14d"] = sum(kickoff_ts - s <= 14 * 86400 for s in starts)
    periods = [r["periods"] for r in rows if r.get("periods")]
    if periods:
        width = min(len(p) for p in periods)
        out["avg_periods"] = [
            [
                round(statistics.fmean(p[i][0] for p in periods), 2),
                round(statistics.fmean(p[i][1] for p in periods), 2),
            ]
            for i in range(width)
        ]
    return out


def head_to_head(
    con: sqlite3.Connection,
    a: int,
    b: int,
    before_ts: int,
    fetched: Sequence[Mapping[str, Any]] = (),
    metrics: Sequence[str] = (),
    sport: str = "football",
) -> list[dict[str, Any]]:
    """The newest meetings from `a`'s view: the cached listings' and those
    Sofascore's h2h route returned (`bet.sofa.h2h`, `fetched`), one row per
    game; with `metrics`, each row carries the legs' metrics read off the
    meeting's cached statistics (a `_for` metric as [a, b])."""
    games: dict[int, Mapping[str, Any]] = {
        int(g["id"]): g
        for g in team_games(con, a, before_ts, H2H_SCAN)
        if b
        in ((g.get("homeTeam") or {}).get("id"), (g.get("awayTeam") or {}).get("id"))
    }
    for g in fetched:
        start = g.get("startTimestamp")
        if isinstance(g.get("id"), int) and isinstance(start, int) \
                and start < before_ts:
            games.setdefault(int(g["id"]), g)
    ordered = sorted(games.values(), key=lambda g: -int(g["startTimestamp"]))
    rows = []
    for g in ordered[:H2H_N]:
        row = game_row(g, a)
        values = meeting_metrics(con, g, a, metrics, sport)
        if values:
            row["metrics"] = values
        rows.append(row)
    return rows


def meeting_metrics(
    con: sqlite3.Connection,
    event: Mapping[str, Any],
    a: int,
    metrics: Sequence[str],
    sport: str,
) -> dict[str, Any]:
    """{metric: value} of one meeting off its cached statistics, as SAMPLES
    reads them (`metrics.extract_metric`); a value it refuses is its gap
    reason, a meeting never fetched has no `metrics`."""
    if not metrics:
        return {}
    try:
        row = con.execute(
            "SELECT statistics_json, incidents_json FROM sofa_event_stats "
            "WHERE sofascore_event_id = ?",
            (event.get("id"),),
        ).fetchone()
    except sqlite3.OperationalError:
        return {}
    if not row:
        return {}
    try:
        statistics = json.loads(row[0]) if row[0] else None
        incidents = json.loads(row[1]) if row[1] else None
    except (TypeError, ValueError):
        return {}
    flat = extract_flat_statistics(statistics)
    a_home = (event.get("homeTeam") or {}).get("id") == a
    listing = dict(event)
    out: dict[str, Any] = {}
    for metric in metrics:
        sides = (a_home, not a_home) if metric.endswith("_for") else (True,)
        values = [
            _metric_value(extract_metric(
                metric, sport, flat, incidents or None, listing, is_home))
            for is_home in sides
        ]
        out[metric] = values if len(values) > 1 else values[0]
    return out


def _metric_value(value: float | GapReason) -> Any:
    if isinstance(value, GapReason):
        return str(value)
    return int(value) if float(value).is_integer() else round(value, 2)


def h2h_metrics(sport: str, legs: Sequence[Mapping[str, Any]]) -> list[str]:
    """The legs' markets that are a metric of a past match, in leg order."""
    if sport == "football":
        known = set(FOOTBALL_METRICS) | set(CARD_INCIDENT_SCOPES)
    elif sport == "tennis":
        known = set(TENNIS_METRICS)
    else:
        return []
    return [m for m in dict.fromkeys(str(x.get("market")) for x in legs) if m in known]


def cache_listings_from(
    con: sqlite3.Connection, team_id: int, before_ts: int
) -> str | None:
    """The oldest cached game of a side (H2H_SCAN deep): how far back the
    cache's own h2h search reached."""
    games = team_games(con, team_id, before_ts, H2H_SCAN)
    starts = [int(g["startTimestamp"]) for g in games]
    first = _iso(min(starts)) if starts else None
    return first[:10] if first else None


def _competition_key(event: Mapping[str, Any]) -> tuple[int | None, int | None]:
    tournament = event.get("tournament") or {}
    unique = tournament.get("uniqueTournament") or {}
    season = event.get("season") or {}
    ut = unique.get("id") if isinstance(unique, Mapping) else None
    sid = season.get("id") if isinstance(season, Mapping) else None
    return (
        int(ut) if isinstance(ut, int) else None,
        int(sid) if isinstance(sid, int) else None,
    )


def league_table(
    con: sqlite3.Connection, detail: Mapping[str, Any], sport: str, before_ts: int
) -> dict[str, Any]:
    """The season's table rebuilt from cached listings, or why not."""
    ut, season = _competition_key(detail)
    home = (detail.get("homeTeam") or {}).get("id")
    away = (detail.get("awayTeam") or {}).get("id")
    if (
        ut is None
        or season is None
        or not isinstance(home, int)
        or not isinstance(away, int)
    ):
        return {"missing": "brak turnieju / sezonu w payloadzie meczu"}
    queue, seen_teams = [home, away], {home, away}
    games: dict[int, dict[str, Any]] = {}
    walked = 0
    while queue and walked < TABLE_MAX_TEAMS:
        team = queue.pop(0)
        walked += 1
        for g in team_games(con, team, before_ts, TABLE_SCAN):
            if _competition_key(g) != (ut, season) or is_friendly_event(g):
                continue
            games[g["id"]] = g
            for side in ("homeTeam", "awayTeam"):
                tid = (g.get(side) or {}).get("id")
                if isinstance(tid, int) and tid not in seen_teams:
                    seen_teams.add(tid)
                    queue.append(tid)
    if not games:
        return {"missing": "brak meczów tego sezonu w cache listingów"}
    table: dict[int, dict[str, Any]] = {}
    for g in games.values():
        hs, as_ = g.get("homeScore") or {}, g.get("awayScore") or {}
        h, a = hs.get("current"), as_.get("current")
        if not isinstance(h, int) or not isinstance(a, int):
            continue
        winner = g.get("winnerCode")
        for side, opp_side, own, opp, code in (
            ("homeTeam", "awayTeam", h, a, 1),
            ("awayTeam", "homeTeam", a, h, 2),
        ):
            team = g[side]
            row = table.setdefault(
                team["id"],
                {
                    "team": team.get("name"),
                    "P": 0,
                    "W": 0,
                    "R": 0,
                    "L": 0,
                    "for": 0,
                    "against": 0,
                },
            )
            row["P"] += 1
            row["for"] += own
            row["against"] += opp
            if winner == 3:
                row["R"] += 1
            elif winner == code:
                row["W"] += 1
            elif winner in (1, 2):
                row["L"] += 1
    rows = list(table.values())
    for row in rows:
        row["pts"] = 3 * row["W"] + row["R"] if sport == "football" else None
        row["win_pct"] = round(row["W"] / row["P"], 3) if row["P"] else 0.0
    if sport == "football":
        rows.sort(key=lambda r: (-r["pts"], -(r["for"] - r["against"]), -r["for"]))
    else:
        rows.sort(key=lambda r: (-r["win_pct"], -(r["for"] - r["against"])))
    for i, row in enumerate(rows, 1):
        row["pos"] = i
        if row["pts"] is None:
            del row["pts"]
    names = {home: None, away: None}
    for tid, row in table.items():
        if tid in names:
            names[tid] = row["pos"]
    return {
        "source": "odtworzona z listingów w cache - nie oficjalna tabela",
        "games_counted": len(games),
        "teams": len(rows),
        "listings_walked": walked,
        "positions": {"home": names[home], "away": names[away]},
        "rows": [
            {
                k: r[k]
                for k in ("pos", "team", "P", "W", "R", "L", "for", "against")
                if k in r
            }
            | ({"pts": r["pts"]} if "pts" in r else {})
            for r in rows
        ],
    }


# --- per-sport blocks ------------------------------------------------------


def cs2_block(
    con: sqlite3.Connection, home: int, away: int, before_ts: int
) -> dict[str, Any]:
    """Series, map pool, roster and player form of both CS2 teams."""
    out: dict[str, Any] = {}
    for label, team in (("home", home), ("away", away)):
        try:
            series = con.execute(
                """SELECT sofascore_event_id, start_ts, tournament, home_id, home_name,
                          away_id, away_name, home_maps, away_maps, best_of
                   FROM cs2_series WHERE status_type = 'finished' AND start_ts < ?
                     AND (home_id = ? OR away_id = ?)
                   ORDER BY start_ts DESC LIMIT ?""",
                (before_ts, team, team, max(CS2_SERIES_N, CS2_ROSTER_SERIES)),
            ).fetchall()
        except sqlite3.OperationalError:
            return {"missing": "brak tabel CS2 w bazie"}
        rows = []
        for sid, ts, tour, h, hn, a, an, hm, am, bo in series[:CS2_SERIES_N]:
            home_side = h == team
            rows.append(
                {
                    "date": _iso(ts),
                    "tournament": tour,
                    "opponent": an if home_side else hn,
                    "maps": [hm, am] if home_side else [am, hm],
                    "best_of": bo,
                }
            )
        maps = con.execute(
            """SELECT m.map_name, s.home_id, m.home_rounds, m.away_rounds, m.winner_code
               FROM cs2_map m JOIN cs2_series s USING (sofascore_event_id)
               WHERE m.status_type = 'finished' AND s.start_ts < ? AND s.start_ts >= ?
                 AND (s.home_id = ? OR s.away_id = ?)""",
            (before_ts, before_ts - CS2_MAP_DAYS * 86400, team, team),
        ).fetchall()
        pool: dict[str, dict[str, Any]] = defaultdict(
            lambda: {"n": 0, "won": 0, "rounds": []}
        )
        for name, h, hr, ar, winner in maps:
            cell = pool[str(name or "?")]
            cell["n"] += 1
            if winner in (1, 2) and (winner == 1) == (h == team):
                cell["won"] += 1
            if isinstance(hr, int) and isinstance(ar, int):
                cell["rounds"].append(hr + ar)
        map_pool = {
            k: {
                "n": v["n"],
                "won": v["won"],
                "avg_rounds": round(statistics.fmean(v["rounds"]), 1)
                if v["rounds"]
                else None,
            }
            for k, v in sorted(pool.items(), key=lambda kv: -kv[1]["n"])
        }
        roster: list[list[str]] = []
        player_rows: dict[str, list[tuple[int, int]]] = defaultdict(list)
        for sid, _ts, _tour, h, *_ in series[:CS2_ROSTER_SERIES]:
            side = "home" if h == team else "away"
            names = con.execute(
                """SELECT DISTINCT p.player_name, p.kills, p.deaths, p.game_id
                   FROM cs2_player_map p JOIN cs2_map m USING (game_id)
                   WHERE m.sofascore_event_id = ? AND p.side = ?""",
                (sid, side),
            ).fetchall()
            roster.append(sorted({str(n[0]) for n in names}))
            for name, kills, deaths, _gid in names:
                if isinstance(kills, int) and isinstance(deaths, int):
                    player_rows[str(name)].append((kills, deaths))
        latest = set(roster[0]) if roster else set()
        earlier = set().union(*map(set, roster[1:])) if len(roster) > 1 else set()
        out[label] = {
            "series": rows,
            "map_pool_90d": map_pool,
            "roster_latest": sorted(latest),
            "roster_new_vs_previous": sorted(latest - earlier) if earlier else [],
            "players_last_series_maps": {
                k: {
                    "maps": len(v),
                    "avg_kills": round(statistics.fmean(x[0] for x in v), 1),
                    "avg_deaths": round(statistics.fmean(x[1] for x in v), 1),
                }
                for k, v in sorted(player_rows.items())
                if k in latest
            },
        }
    return out


def samples_block(
    sample: Mapping[str, Any] | None, legs: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """Football / tennis: each metric's observed values per side (newest
    first, as SAMPLES stored them), the schedule block and the gaps."""
    if not sample:
        return {"missing": "brak wiersza w 03_samples.json"}
    metrics: dict[str, Any] = {}
    for metric, block in (sample.get("metrics") or {}).items():
        cell: dict[str, Any] = {}
        for side in ("side_a", "side_b", "h2h"):
            values = [
                o.get("value")
                for o in block.get(side) or []
                if isinstance(o.get("value"), int | float)
            ]
            if values:
                cell[side] = {
                    "values": values,
                    "mean": round(statistics.fmean(values), 2),
                    "median": statistics.median(values),
                }
        if cell:
            metrics[metric] = cell
    subjects = {str(leg.get("subject") or "").lower() for leg in legs}
    players = {
        key: {
            "matched_name": p.get("matched_name"),
            "side": p.get("side"),
            "values": [o.get("value") for o in p.get("observations") or []],
        }
        for key, p in (sample.get("players") or {}).items()
        if isinstance(p, Mapping) and str(key).split("|")[-1].lower() in subjects
    }
    return {
        "schedule": sample.get("schedule"),
        "readiness": sample.get("readiness"),
        "gaps": [g.get("reason") for g in sample.get("gaps") or []][:20],
        "metrics": metrics,
        "players": players,
    }


def market_block(
    run: Path,
    sport: str,
    legs: Sequence[Mapping[str, Any]],
    offer: Sequence[Mapping[str, Any]] | None,
    event_id: int,
) -> dict[str, Any]:
    """How Superbet's lines of this match moved (sports: every snapshot of the
    day; football / tennis: the offer's ladder of the legs' markets)."""
    if sport in TEAM_SPORTS - {"football"} or sport == "cs2":
        sb = next(
            (
                str(x.get("superbet_event_id"))
                for x in legs
                if x.get("superbet_event_id")
            ),
            None,
        )
        source_date = next(
            (str(x.get("source_date")) for x in legs if x.get("source_date")), None
        )
        if not sb or not source_date:
            return {"missing": "noga bez superbet_event_id / source_date"}
        base = (
            run.parent / ("cs2" if sport == "cs2" else f"shadow/{sport}") / source_date
        )
        path = base / "snapshots.jsonl"
        if not path.exists():
            return {"missing": f"brak {path}"}
        moves: dict[tuple[Any, ...], dict[str, Any]] = {}
        snaps = 0
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                if f'"{sb}"' not in line:
                    continue
                try:
                    snap = json.loads(line)
                except ValueError:
                    continue
                if str(snap.get("superbet_event_id")) != sb:
                    continue
                snaps += 1
                at = snap.get("fetched_at_utc")
                for row in snap.get("lines") or []:
                    key = (
                        row.get("family"),
                        row.get("period", row.get("map_nr")),
                        row.get("subject"),
                        row.get("line"),
                        row.get("side"),
                    )
                    cell = moves.setdefault(
                        key, {"first": row.get("odds"), "first_at": at, "n": 0}
                    )
                    cell.update(last=row.get("odds"), last_at=at)
                    cell["n"] += 1
        families = {x.get("family") or x.get("market") for x in legs}
        rows = [
            {
                "family": k[0],
                "period": k[1],
                "subject": k[2] or None,
                "line": k[3],
                "side": k[4],
                "first": v["first"],
                "last": v["last"],
                "seen": v["n"],
                "first_at": v["first_at"],
                "last_at": v["last_at"],
            }
            for k, v in moves.items()
        ]
        rows.sort(
            key=lambda r: (
                r["family"] not in families,
                str(r["family"]),
                str(r["period"]),
                str(r["line"]),
            )
        )
        moved = [r for r in rows if r["first"] != r["last"]]
        return {
            "source": str(path),
            "snapshots": snaps,
            "lines": len(rows),
            "moved": len(moved),
            "rows": rows[:MARKET_ROWS_MAX],
        }
    entry = next(
        (o for o in offer or [] if o.get("sofascore_event_id") == event_id), None
    )
    if not entry:
        return {"missing": "brak meczu w 04_offer.json"}
    markets = {x.get("market") for x in legs}
    rungs = [r for r in entry.get("rungs") or [] if r.get("market") in markets]
    return {
        "source": "04_offer.json",
        "status": entry.get("status"),
        "superbet_started_utc": entry.get("superbet_started_utc"),
        "rungs_of_leg_markets": rungs[:MARKET_ROWS_MAX],
    }


def leg_rows(legs: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    keep = (
        "position",
        "superbet_market",
        "superbet_selection",
        "confidence",
        "offered_odds",
        "x",
        "sample_k",
        "sample_n",
        "sample_size",
        "sample_hit_rate",
        "line_offset",
        "price_band_cap",
        "context_flags",
        "stakes",
        "calibrated_on",
        "forecast_p",
        "price_fetched_at_utc",
    )
    out = []
    for leg in legs:
        row = {k: leg[k] for k in keep if leg.get(k) is not None}
        if isinstance(leg.get("price_gap"), Mapping):
            row["price_gap"] = True
        peer = leg.get("peer")
        if isinstance(peer, Mapping) and peer.get("preferred"):
            row["peer_preferred"] = True
        reads = [
            f"{r.get('author')}:{r.get('verdict')}"
            for r in leg.get("reads") or []
            if isinstance(r, Mapping)
        ]
        if reads:
            row["reads"] = reads
        if leg.get("removed"):
            row["removed_by_reads"] = True
        out.append(row)
    return out


def web_checklist(
    sport: str, header: Mapping[str, Any], sides: Mapping[str, Any]
) -> list[str]:
    """What the analyst must look up on the web, with the match filled in."""
    home, away = sides.get("home") or "?", sides.get("away") or "?"
    city = header.get("city")
    local = header.get("kickoff_venue_local") or header.get("kickoff_utc")
    lang = header.get("country") or "kraj meczu"
    items = [
        f"newsy i absencje: {home} / {away} (prasa lokalna, {lang}; kanały klubów)",
        f"nastroje i kulisy: {home} / {away} - trener, szatnia, pensje, spory",
        f"stawka: o co gra {home} i {away} (tabela, następny mecz, dwumecz)",
        f"zapowiedzi i opinie: {home} - {away} (rozumowanie, nigdy sam typ)",
    ]
    if sport not in INDOOR:
        items.insert(
            1,
            f"pogoda: {city or 'miasto meczu'} {local} (godzinowa: deszcz, wiatr)",
        )
    if sport == "football":
        items += [
            "przewidywane / potwierdzone składy (~1 h przed)",
            "sędzia, jeśli ogłoszony, i jego kartki w sezonie",
        ]
    elif sport == "tennis":
        items += [
            "order of play, kort, hala / otwarty",
            "poprzedni mecz: długość, MTO, krecz",
            "wycofania; słowa gracza, zmiana trenera",
        ]
    elif sport == "hockey":
        items += ["potwierdzony bramkarz startowy obu drużyn", "back-to-back, podróż"]
    elif sport == "basketball":
        items += ["kontuzje i load management pierwszej piątki", "back-to-back, podróż"]
    elif sport == "volleyball":
        items += ["szóstka startowa; odpoczywający atakujący / rozgrywający"]
    elif sport == "cs2":
        items += [
            "HLTV / Liquipedia: skład, stand-in, bootcamp, wizy",
            "LAN czy online, format (Bo1/Bo3/Bo5), map pool i veto",
        ]
    return items


# --- the dossier -----------------------------------------------------------


def build(
    con: sqlite3.Connection,
    run: Path,
    sport: str,
    event_id: int,
    legs: Sequence[Mapping[str, Any]],
    *,
    fixtures: Mapping[int, Mapping[str, Any]],
    sport_fixtures: Mapping[int, Mapping[str, Any]],
    samples: Mapping[int, Mapping[str, Any]],
    status: Mapping[str, Any],
    offer: Sequence[Mapping[str, Any]] | None,
    now: datetime | None = None,
    h2h_entries: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """One match's dossier (a dict ready for JSON)."""
    detail = event_detail(con, event_id) or {}
    fixture = fixtures.get(event_id) or {}
    pinned = sport_fixtures.get(event_id) or {}
    kickoff = (
        detail.get("startTimestamp")
        or _parse_ts(fixture.get("kickoff_utc"))
        or _parse_ts(pinned.get("sofascore_start_utc") or pinned.get("kickoff_utc"))
        or next((_parse_ts(x.get("kickoff_utc")) for x in legs), None)
    )
    kickoff_ts = (
        int(kickoff)
        if isinstance(kickoff, int | float)
        else int((now or datetime.now(UTC)).timestamp())
    )
    home_t, away_t = detail.get("homeTeam") or {}, detail.get("awayTeam") or {}
    home_id = home_t.get("id") or fixture.get("home_entity_id") or pinned.get("home_id")
    away_id = away_t.get("id") or fixture.get("away_entity_id") or pinned.get("away_id")
    venue = detail.get("venue") or home_t.get("venue") or {}
    zone = venue_timezone(detail) if detail else UTC
    tournament = detail.get("tournament") or {}
    match = next((str(x.get("match")) for x in legs if x.get("match")), None)
    header: dict[str, Any] = {
        "match": match,
        "sport": sport,
        "sofascore_event_id": event_id,
        "competition": (tournament.get("uniqueTournament") or {}).get("name")
        or tournament.get("name")
        or fixture.get("competition_name"),
        "stage": tournament.get("name"),
        "category": (tournament.get("category") or {}).get("name"),
        "season": (detail.get("season") or {}).get("name"),
        "round": (detail.get("roundInfo") or {}).get("name")
        or (detail.get("roundInfo") or {}).get("round")
        or fixture.get("round_name"),
        "kickoff_utc": _iso(kickoff_ts),
        "kickoff_warsaw": _iso(kickoff_ts, LOCAL_ZONE),
        "kickoff_venue_local": _iso(kickoff_ts, zone) if zone is not UTC else None,
        "venue_zone": str(zone) if zone is not UTC else None,
        "venue": venue.get("name") if isinstance(venue, Mapping) else None,
        "city": _name((venue or {}).get("city"))
        if isinstance(venue, Mapping)
        else None,
        "country": _country(venue)
        or _country(tournament.get("category"))
        or (
            (tournament.get("category") or {}).get("name")
            if (tournament.get("category") or {}).get("alpha2")
            else None
        ),
        "capacity": venue.get("capacity") if isinstance(venue, Mapping) else None,
        "coordinates": venue.get("venueCoordinates")
        if isinstance(venue, Mapping)
        else None,
        "gender": ((detail.get("eventFilters") or {}).get("gender") or [None])[0],
        "status": (status.get(str(event_id)) or {}).get("status")
        or (detail.get("status") or {}).get("type"),
    }
    if detail.get("bestOf") or pinned.get("best_of"):
        header["best_of"] = detail.get("bestOf") or pinned.get("best_of")
    if detail.get("groundType") or fixture.get("ground_type"):
        header["surface"] = detail.get("groundType") or fixture.get("ground_type")
    if fixture.get("referee"):
        header["referee"] = fixture["referee"]
    elif isinstance(detail.get("referee"), Mapping):
        header["referee"] = {
            "name": detail["referee"].get("name"),
            "country": _country(detail["referee"]),
        }
    if fixture.get("previous_leg_event_id"):
        first = event_detail(con, int(fixture["previous_leg_event_id"])) or {}
        header["first_leg"] = {
            "event_id": fixture["previous_leg_event_id"],
            "score": [
                (first.get("homeScore") or {}).get("current"),
                (first.get("awayScore") or {}).get("current"),
            ],
            "home": _name(first.get("homeTeam")),
        }
    if pinned:
        header["identity"] = {
            k: pinned.get(k)
            for k in ("status", "match_method", "name_scores", "home_is_team1")
        }
    elif fixture.get("identity"):
        header["identity"] = fixture.get("identity")
    header = {k: v for k, v in header.items() if v not in (None, "", [], {})}

    sides: dict[str, Any] = {}
    side_names = {
        "home": _name(home_t)
        or fixture.get("home_name")
        or pinned.get("sofascore_home"),
        "away": _name(away_t)
        or fixture.get("away_name")
        or pinned.get("sofascore_away"),
    }
    for label, team, node in (("home", home_id, home_t), ("away", away_id, away_t)):
        if not isinstance(team, int):
            sides[label] = {"name": side_names[label], "missing": "brak id drużyny"}
            continue
        games = team_games(con, team, kickoff_ts, FORM_N)
        rows = [game_row(g, team) for g in games]
        info: dict[str, Any] = {
            "name": side_names[label],
            "id": team,
            "country": _country(node),
        }
        ranking = (
            (node.get("playerTeamInfo") or {}).get("currentRanking") if node else None
        )
        if ranking:
            info["ranking"] = ranking
        info["summary"] = side_summary(rows, games, kickoff_ts)
        info["last_games"] = rows
        if not rows:
            info["missing"] = "brak meczów w cache listingów"
        sides[label] = {k: v for k, v in info.items() if v is not None}

    doc: dict[str, Any] = {
        "schema": SCHEMA_VERSION,
        "built_at_utc": (now or datetime.now(UTC)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "data/sofa.db (tylko odczyt) + artefakty dnia (h2h.json: odpowiedź "
        "Sofascore pobrana przez read_set / build_slip); bez zapytań",
        "use": "kontekst do odczytu - nie zmienia pewności ani bramek",
        "header": header,
        "legs": leg_rows(legs),
        "sides": sides,
    }
    h2h_asked = (h2h_entries or {}).get(str(event_id)) or {}
    if isinstance(home_id, int) and isinstance(away_id, int):
        doc["head_to_head"] = head_to_head(
            con, home_id, away_id, kickoff_ts, h2h_asked.get("meetings") or (),
            h2h_metrics(sport, legs), sport)
        doc["head_to_head_source"] = {
            "sofascore_h2h": h2h_asked.get("status") or "NOT_ASKED",
            "fetched_at_utc": h2h_asked.get("fetched_at_utc"),
            "meetings_returned": len(h2h_asked.get("meetings") or []),
            "cache_listings_from": {
                "home": cache_listings_from(con, home_id, kickoff_ts),
                "away": cache_listings_from(con, away_id, kickoff_ts),
            },
        }
        if sport in TEAM_SPORTS and detail:
            doc["table"] = league_table(con, detail, sport, kickoff_ts)
        if sport == "cs2":
            doc["cs2"] = cs2_block(con, home_id, away_id, kickoff_ts)
    if sport in ("football", "tennis"):
        doc["samples"] = samples_block(samples.get(event_id), legs)
    doc["market"] = market_block(run, sport, legs, offer, event_id)
    doc["web_checklist"] = web_checklist(sport, header, side_names)
    if h2h_asked.get("status") != h2h_fetch.OK:
        asked = h2h_asked.get("status") or "NOT_ASKED"
        doc["web_checklist"].append(
            f"h2h: Sofascore nie odpowiedział ({asked})"
            f" - ostatnie spotkania {side_names['home'] or '?'} - "
            f"{side_names['away'] or '?'} i statystyki rynków nóg z sieci")
    return doc


def _load(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def write_for_legs(
    run: Path,
    legs: Iterable[dict[str, Any]],
    *,
    db_path: str | Path = DB_PATH,
    now: datetime | None = None,
) -> dict[int, str]:
    """Write one dossier per match of `legs`, set each leg's `dossier` to its
    path; returns {event id: path}. A match whose dossier fails keeps no
    `dossier` field and is listed on stderr by the caller - never a guess."""
    legs = list(legs)
    by_event: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for leg in legs:
        if isinstance(leg.get("sofascore_event_id"), int):
            by_event[leg["sofascore_event_id"]].append(leg)
    if not by_event:
        return {}
    coupon = _load(run / "11_coupon.json") or {}
    full: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for leg in coupon.get("singles") or []:
        full[leg.get("sofascore_event_id")].append(leg)
    for leg in coupon.get("removed_by_reads") or []:
        full[leg.get("sofascore_event_id")].append({**leg, "removed": True})
    fixtures = {
        int(f["sofascore_event_id"]): f
        for f in _load(run / "02_fixtures.json") or []
        if isinstance(f.get("sofascore_event_id"), int)
    }
    sport_fixtures = {
        int(f["sofascore_event_id"]): f
        for f in (_load(run / "sport_fixtures.json") or {}).get("fixtures") or []
        if isinstance(f.get("sofascore_event_id"), int)
    }
    samples = {
        int(s["sofascore_event_id"]): s
        for s in _load(run / "03_samples.json") or []
        if isinstance(s.get("sofascore_event_id"), int)
    }
    status = (_load(run / "fixture_status.json") or {}).get("events") or {}
    offer = _load(run / "04_offer.json")
    h2h_entries = h2h_fetch.load(run)
    written: dict[int, str] = {}
    con = connect(db_path)
    try:
        for event_id, these in by_event.items():
            sport = str(these[0].get("sport") or "football")
            match_legs = full.get(event_id) or these
            doc = build(
                con,
                run,
                sport,
                event_id,
                match_legs,
                fixtures=fixtures,
                sport_fixtures=sport_fixtures,
                samples=samples,
                status=status,
                offer=offer,
                now=now,
                h2h_entries=h2h_entries,
            )
            path = dossier_path(run, sport, event_id)
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".json.tmp")
            tmp.write_text(
                json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
            )
            tmp.replace(path)
            written[event_id] = str(path)
            for leg in these:
                leg["dossier"] = str(path)
    finally:
        con.close()
    return written


def attach(
    run: Path,
    legs: Iterable[dict[str, Any]],
    db_path: str | Path | None = None,
    now: datetime | None = None,
) -> str:
    """write_for_legs for a read-set writer: one line for its output. A
    failure is reported, never raised - a read set without dossiers is still
    a read set (the analyst says "brak dossier")."""
    path = Path(db_path or DB_PATH)
    if not path.exists():
        return f"dossier: brak bazy {path} - nogi bez dossier"
    try:
        written = write_for_legs(run, legs, db_path=path, now=now)
    except (sqlite3.Error, OSError, ValueError, KeyError, TypeError) as exc:
        return f"dossier: BŁĄD {type(exc).__name__}: {exc} - nogi bez dossier"
    return f"dossier: {len(written)} meczów -> {run / 'dossier'}"
