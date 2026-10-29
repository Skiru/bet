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
h2h was not answered says so and the web checklist asks for it. Sofascore's
pre-match line-up is the second (`bet.sofa.prematch_lineups` ->
`runs/sofa/<d>/lineups_prematch.json`): block `lineups` shows the predicted or
confirmed XI, the missing / doubtful list, each player leg's player and each
side's regulars (from cached post-match line-ups) not in the XI.

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

from rapidfuzz import fuzz

from bet.sofa import h2h as h2h_fetch
from bet.sofa import prematch_lineups
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
from bet.sofa.names import normalize_name
from bet.sofa.players import (
    is_player_metric,
    match_player,
    match_player_by_inner_surname,
    match_player_by_surname,
    match_player_by_tokens,
    match_player_by_transliteration,
)
from bet.sofa.settle import venue_timezone

# 2 (2026-10-29): football `style` with league rate, xG / blocked shots / long
# balls / throw-ins / goal kicks and `matchup[].metric`; an older dossier lacks them.
# 3 (2026-10-29): `matchup[]` rows carry the leg's key, `joint` and `price_gap`,
# a joint read as min(own, rival) as SETTLE grades it - a `RYNEK:` WATCH is
# checked against its row only from schema 3
SCHEMA_VERSION = 3
FORM_N = 10  # last games per side
H2H_N = 6
H2H_SCAN = 200  # a side's listed games searched for the opponent
TABLE_MAX_TEAMS = 40  # listings walked to rebuild a table
TABLE_SCAN = 80  # games per listing walked for the table
MARKET_ROWS_MAX = 160  # Superbet line rows per match
CS2_SERIES_N = 10
CS2_MAP_DAYS = 90
CS2_ROSTER_SERIES = 6
# style block (football): competitive games with statistics per side, how far
# back a side's listing is walked for them, and the subject-to-side match
STYLE_N = 10
STYLE_SCAN = 30
STYLE_SIDE_MATCH = 70
STYLE_POSSESSION_MIN = 4  # a possession bucket below it is a note, never a RYNEK WATCH
# a league's rate of a leg's metric: the newest games of the season walked
LEAGUE_RATE_GAMES = 200
LEAGUE_RATE_MIN = 30
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
    games, walked = _season_games(con, ut, season, [home, away], before_ts)
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
            "match_rule": p.get("match_rule"),
            "values": [o.get("value") for o in p.get("observations") or []],
        }
        for key, p in (sample.get("players") or {}).items()
        if isinstance(p, Mapping) and str(key).split("|")[-1].lower() in subjects
    }
    return {
        "schedule": sample.get("schedule"),
        "readiness": sample.get("readiness"),
        # The detail tells a kept ENTITY_CONFLICT cut ("sample cut at the
        # clash") from an emptied side, and a used PLAYER_HISTORY_ANY_TEAM
        # top-up from a refused THIN_SAMPLE.
        "gaps": [
            {"reason": g.get("reason"), "metric": g.get("metric"),
             "detail": str(g.get("detail") or "")[:160]}
            for g in sample.get("gaps") or [] if isinstance(g, Mapping)
        ][:20],
        "metrics": metrics,
        "players": players,
    }


def _stat_items(statistics: Mapping[str, Any] | None) -> dict[str, dict[str, Any]]:
    """{period: {key: item}} of a /statistics payload, raw items kept: the
    flat extractor drops `homeTotal` (crosses attempted)."""
    out: dict[str, dict[str, Any]] = {}
    for period in (statistics or {}).get("statistics") or []:
        bucket = out.setdefault(str(period.get("period", "ALL")), {})
        for group in period.get("groups") or []:
            for item in group.get("statisticsItems") or []:
                if isinstance(item, Mapping) and item.get("key"):
                    bucket.setdefault(str(item["key"]), dict(item))
    return out


def _pair(
    items: Mapping[str, Mapping[str, Any]], key: str, home: bool, field: str = "Value"
) -> list[float] | None:
    """[own, opponent] of one statistic from one side's view; None when the
    payload does not carry it (never a zero)."""
    item = items.get(key)
    if not item:
        return None
    own, opp = ("home", "away") if home else ("away", "home")
    a, b = item.get(own + field), item.get(opp + field)
    if not isinstance(a, int | float) or not isinstance(b, int | float):
        return None
    return [float(a), float(b)]


def _side_of_subject(subject: str, names: Mapping[str, str | None]) -> str | None:
    """'home' / 'away' for a Superbet team name, None when unclear (never the
    home side by default)."""
    norm = normalize_name(subject)
    if not norm:
        return None
    scores = {
        side: fuzz.token_sort_ratio(norm, normalize_name(name or ""))
        for side, name in names.items()
    }
    best = max(scores, key=lambda s: scores[s])
    other = min(scores, key=lambda s: scores[s])
    if scores[best] < STYLE_SIDE_MATCH or scores[best] - scores[other] < 15:
        return None
    return best


def _hits(values: Sequence[float], line: float, direction: str) -> int:
    return sum((v > line) if direction == "OVER" else (v < line) for v in values)


def style_profile(
    con: sqlite3.Connection, team_id: int, kickoff_ts: int
) -> dict[str, Any]:
    """One side's last STYLE_N competitive games with cached statistics: how
    it plays (possession, crosses, box touches, shots inside the box) beside
    what it wins and concedes (corners, shots), and its corners split by its
    own possession - a side whose corners vanish when it does not have the
    ball is a different bet against a possession side."""
    rows: list[dict[str, Any]] = []
    for event in team_games(con, team_id, kickoff_ts, STYLE_SCAN):
        if len(rows) >= STYLE_N:
            break
        if is_friendly_event(event):
            continue
        found = con.execute(
            "SELECT statistics_json FROM sofa_event_stats WHERE sofascore_event_id = ?",
            (event["id"],),
        ).fetchone()
        try:
            payload = json.loads(found[0]) if found and found[0] else None
        except (TypeError, ValueError):
            payload = None
        periods = _stat_items(payload)
        full = periods.get("ALL") or {}
        home = (event.get("homeTeam") or {}).get("id") == team_id
        corners = _pair(full, "cornerKicks", home)
        if corners is None:
            continue
        possession = _pair(full, "ballPossession", home)
        # a partial feed sends possession 0 / 0: a placeholder, not a game
        if possession is not None and not 98 <= sum(possession) <= 102:
            possession = None
        row: dict[str, Any] = {
            "date": (_iso(event.get("startTimestamp")) or "")[:10],
            "opponent": _name(event.get("awayTeam" if home else "homeTeam")),
            "venue": "dom" if home else "wyjazd",
            "competition": ((event.get("tournament") or {}).get("uniqueTournament")
                            or {}).get("name"),
            "corners": corners,
            "possession": possession[0] if possession else None,
            "crosses": _pair(full, "accurateCross", home, "Total"),
            "box_touches": _pair(full, "touchesInOppBox", home),
            "shots_inside_box": _pair(full, "totalShotsInsideBox", home),
            "shots": _pair(full, "totalShotsOnGoal", home),
            "shots_on_target": _pair(full, "shotsOnGoal", home),
        }
        for period, label in (("1ST", "corners_1h"), ("2ND", "corners_2h")):
            half = _pair(periods.get(period) or {}, "cornerKicks", home)
            if half is not None:
                row[label] = half
        for stat_key, label, field in (
                ("offsides", "offsides", "Value"), ("fouls", "fouls", "Value"),
                ("goalkeeperSaves", "saves", "Value"),
                ("blockedScoringAttempt", "blocked_shots", "Value"),
                ("totalShotsOutsideBox", "shots_outside_box", "Value"),
                ("bigChanceCreated", "big_chances", "Value"),
                ("expectedGoals", "xg", "Value"),
                ("finalThirdEntries", "final_third_entries", "Value"),
                ("accurateLongBalls", "long_balls", "Total"),
                ("throwIns", "throw_ins", "Value"),
                ("goalKicks", "goal_kicks", "Value")):
            got = _pair(full, stat_key, home, field)
            if got is not None:
                row[label] = got
        rows.append({k: v for k, v in row.items() if v is not None})
    out: dict[str, Any] = {"n": len(rows), "games": rows}
    if not rows:
        out["missing"] = "brak statystyk meczów w cache"
        return out
    means: dict[str, Any] = {}
    for label in ("corners", "crosses", "box_touches", "shots_inside_box", "shots",
                  "shots_on_target", "blocked_shots", "shots_outside_box",
                  "big_chances", "xg", "final_third_entries", "long_balls"):
        pairs = [r[label] for r in rows if label in r]
        digits = 2 if label == "xg" else 1
        if pairs:
            means[label] = {
                "za": round(statistics.fmean(p[0] for p in pairs), digits),
                "przeciw": round(statistics.fmean(p[1] for p in pairs), digits),
                "n": len(pairs),
            }
    poss = [r["possession"] for r in rows if "possession" in r]
    if poss:
        means["possession"] = round(statistics.fmean(poss), 1)
    out["means"] = means
    split: dict[str, Any] = {}
    for label, below in (("posiadanie_ponizej_50", True),
                         ("posiadanie_50_plus", False)):
        part = [r["corners"][0] for r in rows
                if "possession" in r and (r["possession"] < 50) == below]
        if part:
            split[label] = {"n": len(part), "rozne_za": part,
                            "srednia": round(statistics.fmean(part), 1)}
            if len(part) < STYLE_POSSESSION_MIN:
                split[label]["uwaga"] = (f"n < {STYLE_POSSESSION_MIN} - notatka, "
                                         "nigdy podstawa usunięcia")
    if split:
        out["corners_by_own_possession"] = split
    return out


def leg_metric(market: str) -> tuple[str, bool] | None:
    """(metric, both sides) a football leg is counted by - its own market as
    SAMPLES and SETTLE read it (`metrics.extract_metric`), a "każda z drużyn"
    market as its side metric; None for a market with no per-match count
    (score markets, players)."""
    known = set(FOOTBALL_METRICS) | set(CARD_INCIDENT_SCOPES)
    if market in known:
        return market, False
    if market.startswith("both_over_"):
        side = market[len("both_over_"):] + "_for"
        if side in known:
            return side, True
    return None


def _metric_games(
    con: sqlite3.Connection,
    team_id: int,
    kickoff_ts: int,
    metrics: Sequence[str],
    cache: dict[tuple[int, int], dict[str, Any]],
) -> list[dict[str, Any]]:
    """The side's newest STYLE_N competitive games with cached statistics,
    each {metric: value from the side's view} (a `_for` metric as [own,
    opponent]); a value the extractor refuses is left out."""
    out: list[dict[str, Any]] = []
    for event in team_games(con, team_id, kickoff_ts, STYLE_SCAN):
        if len(out) >= STYLE_N:
            break
        if is_friendly_event(event):
            continue
        key = (int(event["id"]), team_id)
        if key not in cache:
            cache[key] = meeting_metrics(con, event, team_id, metrics, "football")
        values = cache[key]
        if not values:
            continue
        out.append({"_event": int(event["id"]),
                    **{m: v for m, v in values.items() if _numeric(v)}})
    return out


def _numeric(value: Any) -> bool:
    if isinstance(value, list):
        return all(isinstance(v, int | float) for v in value)
    return isinstance(value, int | float)


def _season_games(
    con: sqlite3.Connection, ut: int, season: int, seeds: Sequence[int],
    before_ts: int,
) -> tuple[dict[int, dict[str, Any]], int]:
    """Every cached game of one season of one competition reachable from the
    seed teams' listings (then their opponents'), and how many listings were
    walked."""
    queue, seen_teams = list(seeds), set(seeds)
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
    return games, walked


def league_rates(
    con: sqlite3.Connection,
    competitions: Sequence[tuple[int, int, str | None, int]],
    kickoff_ts: int,
    metrics: Sequence[str],
) -> dict[str, Any]:
    """The league's own values of the legs' metrics: the first competition
    of `competitions` ((ut, season, name, seed team)) whose season gives
    LEAGUE_RATE_MIN games with statistics - the match's own competition
    first, then each side's league (a cup tie reads its sides' leagues)."""
    for ut, season, name, seed in competitions:
        games, _ = _season_games(con, ut, season, [seed], kickoff_ts)
        newest = sorted(games.values(), key=lambda g: g["startTimestamp"],
                        reverse=True)[:LEAGUE_RATE_GAMES]
        per_game: list[dict[str, Any]] = []
        for g in newest:
            home = (g.get("homeTeam") or {}).get("id")
            if not isinstance(home, int):
                continue
            values = meeting_metrics(con, g, home, metrics, "football")
            values = {m: v for m, v in values.items() if _numeric(v)}
            if values:
                per_game.append(values)
        if len(per_game) >= LEAGUE_RATE_MIN:
            return {"competition": name, "games": len(per_game),
                    "values": per_game}
    return {}


def _competitions_for(
    detail: Mapping[str, Any], games: Mapping[str, Sequence[Mapping[str, Any]]],
    ids: Mapping[str, Any], con: sqlite3.Connection, kickoff_ts: int,
) -> list[tuple[int, int, str | None, int]]:
    """The match's competition, then each side's most frequent competition
    of its newest games (its league when tonight is a cup tie)."""
    out: list[tuple[int, int, str | None, int]] = []
    ut, season = _competition_key(detail)
    home = ids.get("home")
    if ut is not None and season is not None and isinstance(home, int):
        out.append((ut, season, (
            (detail.get("tournament") or {}).get("uniqueTournament") or {}
        ).get("name"), home))
    for side in ("home", "away"):
        team = ids.get(side)
        if not isinstance(team, int):
            continue
        counts: dict[tuple[int, int], int] = defaultdict(int)
        names: dict[tuple[int, int], str | None] = {}
        for event in team_games(con, team, kickoff_ts, STYLE_SCAN):
            key = _competition_key(event)
            if key[0] is None or key[1] is None or is_friendly_event(event):
                continue
            k = (int(key[0]), int(key[1]))
            counts[k] += 1
            names[k] = ((event.get("tournament") or {}).get("uniqueTournament")
                        or {}).get("name")
        if counts:
            best = max(counts, key=lambda k: counts[k])
            if all((best[0], best[1]) != (c[0], c[1]) for c in out):
                out.append((best[0], best[1], names[best], team))
    return out


def matchup_rows(
    legs: Sequence[Mapping[str, Any]],
    games: Mapping[str, Sequence[Mapping[str, Any]]],
    names: Mapping[str, str | None],
    league: Mapping[str, Any] | None = None,
) -> list[tuple[dict[str, Any], Mapping[str, Any]]]:
    """Every football count leg against both histories and the league: a
    side leg - how often the side reached the line and how often tonight's
    opponent CONCEDED it; a total - how often each side's games went over /
    under it; the league's share. A sample of the subject's own games alone
    does not see an opponent that gives nothing away (2026-10-28:
    Panathinaikos corners over 3.5 - own 9/10, Aris conceded it 3/10; lost
    with 2). A "każda z drużyn" joint (both_over_*) reads like a total on
    min(own, rival) per game, as SETTLE grades it (`run_settle.py`): OVER =
    both above the line, UNDER = not both - never each side's own count.
    Each row carries the leg's key (market / subject / line / direction),
    `joint` and `price_gap`, so a `RYNEK:` WATCH is checked against its own
    row (`bet.sofa.report_check.market_findings`)."""
    out: list[tuple[dict[str, Any], Mapping[str, Any]]] = []
    seen: set[tuple[Any, ...]] = set()
    league_values = (league or {}).get("values") or []
    for leg in legs:
        market = str(leg.get("market") or "")
        found = leg_metric(market)
        line, direction = leg.get("line"), str(leg.get("direction") or "")
        if found is None or not isinstance(line, int | float) or direction not in (
                "OVER", "UNDER"):
            continue
        metric, both = found
        key = (market, leg.get("subject"), line, direction)
        if key in seen:
            continue
        seen.add(key)
        row: dict[str, Any] = {
            "leg": f"{leg.get('superbet_market') or market}: "
                   f"{leg.get('superbet_selection') or f'{direction} {line}'}",
            "metric": metric,
            "confidence": leg.get("confidence"),
            "implied": round(1 / float(leg["offered_odds"]), 3)
            if isinstance(leg.get("offered_odds"), int | float)
            and leg["offered_odds"] > 1 else None,
            "sides": [],
            "market": market,
            "subject": leg.get("subject") or "",
            "line": line,
            "direction": direction,
        }
        if both:
            row["joint"] = True
        if leg.get("price_gap"):
            row["price_gap"] = True
        def hits(values: Sequence[float]) -> str | None:
            return (f"{_hits(values, float(line), direction)}/{len(values)}"
                    if values else None)
        if both:
            for side in ("home", "away"):
                totals = [min(g[metric]) for g in games.get(side, ()) if metric in g]
                cell = {"team": names.get(side), "games": hits(totals),
                        "values": totals}
                row["sides"].append({k: v for k, v in cell.items() if v})
            pool = [min(g[metric]) for g in league_values if metric in g]
        elif metric.endswith("_for"):
            found_side = _side_of_subject(str(leg.get("subject") or ""), names)
            if found_side is None:
                continue
            side = found_side
            opp = "away" if side == "home" else "home"
            own = [g[metric][0] for g in games.get(side, ()) if metric in g]
            conceded = [g[metric][1] for g in games.get(opp, ()) if metric in g]
            cell = {"team": names.get(side), "opponent": names.get(opp),
                    "own": hits(own), "own_values": own,
                    "opponent_conceded": hits(conceded),
                    "conceded_values": conceded}
            row["sides"].append({k: v for k, v in cell.items() if v})
            pool = [v for g in league_values if metric in g for v in g[metric]]
        else:
            for side in ("home", "away"):
                totals = [g[metric] for g in games.get(side, ()) if metric in g]
                cell = {"team": names.get(side), "games": hits(totals),
                        "values": totals}
                row["sides"].append({k: v for k, v in cell.items() if v})
            pool = [g[metric] for g in league_values if metric in g]
        if pool:
            row["league"] = {
                "competition": (league or {}).get("competition"),
                "share": round(_hits(pool, float(line), direction) / len(pool), 3),
                "n": len(pool),
                "mean": round(statistics.fmean(pool), 2),
            }
        out.append(({k: v for k, v in row.items() if v is not None}, leg))
    return out


def _leg_hit(
    leg: Mapping[str, Any], g: Mapping[str, Any], owner: str,
    names: Mapping[str, str | None],
) -> bool | None:
    """Whether one leg hit in one past game of the `owner` side's list: a
    total reads the game, a side leg the owner's own value when it is the
    leg's side, else what the owner conceded; None when the game cannot say."""
    found = leg_metric(str(leg.get("market") or ""))
    line, direction = leg.get("line"), str(leg.get("direction") or "")
    if found is None or not isinstance(line, int | float) or direction not in (
            "OVER", "UNDER"):
        return None
    metric, both = found
    if metric not in g:
        return None
    def hit(v: float) -> bool:
        return v > line if direction == "OVER" else v < line
    if not metric.endswith("_for"):
        return hit(float(g[metric]))
    own, conceded = float(g[metric][0]), float(g[metric][1])
    if both:
        # as SETTLE grades it: min of the two counts (UNDER = not both over)
        return hit(min(own, conceded))
    side = _side_of_subject(str(leg.get("subject") or ""), names)
    if side is None:
        return None
    return hit(own if side == owner else conceded)


def joint_history(
    run: Path,
    legs: Sequence[Mapping[str, Any]],
    *,
    db_path: str | Path = DB_PATH,
) -> dict[str, Any]:
    """How often EVERY leg of one match hit together in the two sides' last
    games (a side's leg read as its own count in its games and as what the
    opponent conceded in the opponent's): k/n games, the legs it could not
    read named. A frequency over ~20 games, never a probability or a price."""
    event = next((x.get("sofascore_event_id") for x in legs), None)
    fx = next((f for f in _load(run / "02_fixtures.json") or []
               if isinstance(f, Mapping) and f.get("sofascore_event_id") == event),
              None) or {}
    home, away = fx.get("home_entity_id"), fx.get("away_entity_id")
    kickoff = _parse_ts(fx.get("kickoff_utc"))
    if (not isinstance(home, int) or not isinstance(away, int) or kickoff is None
            or not Path(db_path).exists()):
        return {"missing": "brak meczu w 02_fixtures.json albo bazy"}
    names = {"home": fx.get("home_name"), "away": fx.get("away_name")}
    metrics = sorted({found[0] for x in legs
                      if (found := leg_metric(str(x.get("market"))))})
    cache: dict[tuple[int, int], dict[str, Any]] = {}
    con = connect(db_path)
    try:
        lists = {"home": _metric_games(con, home, kickoff, metrics, cache),
                 "away": _metric_games(con, away, kickoff, metrics, cache)}
    finally:
        con.close()
    unread = [x for x in legs if leg_metric(str(x.get("market"))) is None]
    read = [x for x in legs if x not in unread]
    k = n = 0
    seen: set[int] = set()
    for owner, games in lists.items():
        for g in games:
            if g["_event"] in seen:
                continue
            seen.add(g["_event"])
            hits = [_leg_hit(x, g, owner, names) for x in read]
            if not read or any(h is None for h in hits):
                continue
            n += 1
            k += all(hits)
    return {
        "k": k, "n": n,
        "legs_read": len(read),
        "legs_without_history": [
            f"{x.get('superbet_market')}: {x.get('superbet_selection')}"
            for x in unread],
    }


def matchup_key(leg: Mapping[str, Any]) -> str:
    return "|".join(str(leg.get(k)) for k in (
        "sofascore_event_id", "market", "subject", "line", "direction"))


def matchup_text(row: Mapping[str, Any]) -> str:
    """One matchup row as the page shows it beside the leg."""
    parts = ["noga łączna (min obu stron)"] if row.get("joint") else []
    for cell in row.get("sides") or []:
        if "games" in cell:
            parts.append(f"mecze {cell.get('team')} {cell['games']}")
        else:
            parts.append(f"{cell.get('team')} {cell.get('own') or '?'}, "
                         f"{cell.get('opponent')} oddaje "
                         f"{cell.get('opponent_conceded') or '?'}")
    league = row.get("league")
    if league:
        parts.append(f"liga {round(100 * league['share'])}% (n={league['n']})")
    return "zestawienie: " + " · ".join(parts) if parts else ""


def matchups_for_legs(
    run: Path,
    legs: Iterable[Mapping[str, Any]],
    *,
    db_path: str | Path = DB_PATH,
) -> dict[str, str]:
    """{matchup_key(leg): text} for every football count leg of `legs` (the
    HTML view: every printed leg, read or not; no league rate - that walks a
    season per match). Teams from 02_fixtures.json; a match without both
    ids gets nothing - never a guess."""
    by_event: dict[int, list[Mapping[str, Any]]] = defaultdict(list)
    for leg in legs:
        if (leg.get("sport") or "football") == "football" and leg_metric(
                str(leg.get("market"))) is not None and isinstance(
                leg.get("sofascore_event_id"), int):
            by_event[int(leg["sofascore_event_id"])].append(leg)
    if not by_event or not Path(db_path).exists():
        return {}
    fixtures = {
        int(f["sofascore_event_id"]): f
        for f in _load(run / "02_fixtures.json") or []
        if isinstance(f, Mapping) and isinstance(f.get("sofascore_event_id"), int)
    }
    out: dict[str, str] = {}
    cache: dict[tuple[int, int], dict[str, Any]] = {}
    con = connect(db_path)
    try:
        for event_id, these in by_event.items():
            fx = fixtures.get(event_id) or {}
            home, away = fx.get("home_entity_id"), fx.get("away_entity_id")
            kickoff = _parse_ts(fx.get("kickoff_utc"))
            if (not isinstance(home, int) or not isinstance(away, int)
                    or kickoff is None):
                continue
            metrics = sorted({found[0] for x in these
                              if (found := leg_metric(str(x.get("market"))))})
            games = {"home": _metric_games(con, home, kickoff, metrics, cache),
                     "away": _metric_games(con, away, kickoff, metrics, cache)}
            names = {"home": fx.get("home_name"), "away": fx.get("away_name")}
            for row, leg in matchup_rows(these, games, names):
                text = matchup_text(row)
                if text:
                    out[matchup_key(leg)] = text
    finally:
        con.close()
    return out


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
    """What the analyst must look up on the web, with the match filled in:
    the sport's mandatory checks first (`sofa-analysis-core` references
    `sources-<sport>.md`, with the source that answers each), then the soft
    half. Weather only outdoors, and only the extreme counts."""
    home, away = sides.get("home") or "?", sides.get("away") or "?"
    city = header.get("city")
    local = header.get("kickoff_venue_local") or header.get("kickoff_utc")
    lang = header.get("country") or "kraj meczu"
    first = [f"czy się odbędzie: przełożenie, zmiana miejsca / godziny - "
             f"{home} - {away}"]
    if sport == "football":
        first += [
            "przewidywane / potwierdzone składy (~1 h przed)",
            f"absencje od wyceny: {home} / {away} (transfermarkt, sportsgambler, "
            f"prasa lokalna, {lang}); każdy gracz nogi zawodniczej - czy gra, "
            "na jakiej pozycji",
            "sędzia, jeśli ogłoszony (zmiana względem dossier = nowa informacja), "
            "przy nogach kartek / fauli",
        ]
    elif sport == "tennis":
        first += [
            "order of play, kort, hala / otwarty, format (Bo3 / Bo5)",
            "poprzedni mecz: długość, godzina końca, MTO, krecz (tennisexplorer)",
            "wycofania, lucky loser; słowa gracza, zmiana trenera",
        ]
    elif sport == "hockey":
        first += [
            "potwierdzony bramkarz startowy obu drużyn (dailyfaceoff, rotowire; "
            "Europa: zwykle UNVERIFIED)",
            "back-to-back, podróż; absencje top-6 / top-4 D; gracz nogi - linia, PP",
        ]
    elif sport == "basketball":
        first += [
            "raport kontuzji: Out / Doubtful / Questionable pierwszej piątki, "
            "ograniczenie minut (official.nba.com, rotowire; Euroliga: basketnews)",
            "back-to-back, podwójna kolejka Euroligi, podróż",
        ]
    elif sport == "volleyball":
        first += [
            "zapowiedziane urazy / odpoczynek atakującego, rozgrywającego, "
            "przyjmującego (szóstki przed meczem nikt nie publikuje)",
            "kalendarz: mecz między meczami CEV; format (złoty set, tie-break do 15)",
        ]
    elif sport == "cs2":
        first += [
            "HLTV (wyszukiwanie po domenie) / dust2.us / Liquipedia API: skład, "
            "stand-in, bootcamp, wizy; gracz nogi - czy w piątce",
            "LAN czy online, format (Bo1/Bo3/Bo5), map pool i veto",
        ]
    soft = [
        f"stawka: o co gra {home} i {away} (tabela, następny mecz, dwumecz) - "
        "liczy się tylko przez skład",
        f"nastroje i kulisy: {home} / {away} - trener, szatnia, pensje, spory",
        f"zapowiedzi i opinie: {home} - {away} (rozumowanie, nigdy sam typ)",
    ]
    if sport not in INDOOR:
        soft.insert(0, f"pogoda: {city or 'miasto meczu'} {local} (godzinowa, "
                       "open-meteo; liczy się tylko skrajna: ulewa, wichura, "
                       "śnieg, upał)")
    return first + soft


# --- Sofascore's pre-match line-up (lineups_prematch.json) -----------------

REGULARS_GAMES = 10  # last cached games read for a side's regulars
REGULAR_MIN_SHARE = 0.6  # starts / cached line-ups that make a regular
REGULARS_MIN_LINEUPS = 3  # fewer cached post-match line-ups: no regulars


def cached_lineups(con: sqlite3.Connection, event_id: int) -> dict[str, Any] | None:
    """The cached post-match /lineups answer of a finished game (read only)."""
    try:
        row = con.execute(
            "SELECT lineups_json FROM sofa_event_stats WHERE sofascore_event_id = ?",
            (event_id,),
        ).fetchone()
    except sqlite3.OperationalError:
        return None
    if not row or not row[0]:
        return None
    try:
        payload = json.loads(row[0])
    except (TypeError, ValueError):
        return None
    return payload if isinstance(payload, dict) and payload else None


def regulars(
    con: sqlite3.Connection, team_id: int, kickoff_ts: int
) -> dict[str, Any]:
    """A side's regulars: players who started at least REGULAR_MIN_SHARE of
    its last REGULARS_GAMES cached games that hold a post-match line-up."""
    starts: dict[int, int] = defaultdict(int)
    names: dict[int, str] = {}
    counted = 0
    for game in team_games(con, team_id, kickoff_ts, REGULARS_GAMES):
        payload = cached_lineups(con, int(game["id"]))
        side = "home" if (game.get("homeTeam") or {}).get("id") == team_id else "away"
        players = ((payload or {}).get(side) or {}).get("players")
        if not isinstance(players, list) or not players:
            continue
        counted += 1
        for entry in players:
            player = entry.get("player") if isinstance(entry, Mapping) else None
            if not isinstance(player, Mapping) or not isinstance(player.get("id"), int):
                continue
            if entry.get("substitute") is False:
                starts[player["id"]] += 1
                names[player["id"]] = str(player.get("name") or player["id"])
    basis = {"games_read": REGULARS_GAMES, "lineups_cached": counted,
             "min_share": REGULAR_MIN_SHARE}
    if counted < REGULARS_MIN_LINEUPS:
        return {**basis, "missing": f"tylko {counted} składów po meczu w cache"}
    need = REGULAR_MIN_SHARE * counted
    rows: list[dict[str, Any]] = [
        {"id": pid, "name": names[pid], "starts": n}
        for pid, n in sorted(starts.items(), key=lambda kv: (-kv[1], names[kv[0]]))
        if n >= need]
    return {**basis, "players": rows}


def _where(side: Mapping[str, Any], player_id: object) -> str | None:
    """XI / ławka / missing / doubtful for one player id on one side."""
    for row in side.get("starters") or []:
        if row.get("id") == player_id:
            return "XI"
    for row in side.get("substitutes") or []:
        if row.get("id") == player_id:
            return "ławka"
    for row in side.get("missing") or []:
        if row.get("id") == player_id:
            return str(row.get("type") or "missing")
    return None


def _is_player_leg(leg: Mapping[str, Any]) -> bool:
    market = str(leg.get("market") or "")
    return bool(leg.get("subject")) and (
        market.startswith("player_") or is_player_metric(market))


def player_leg_status(
    entry: Mapping[str, Any],
    legs: Sequence[Mapping[str, Any]],
    sample: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Each player leg's player in Sofascore's line-up: XI / ławka / missing /
    doubtful, or not on the list. First the person SAMPLES itself matched
    (the sample's `matched_name`, whatever rule found him - slug included,
    which a line-up without slugs cannot re-run); else the samples' name
    rules (fuzzy, whole tokens, surname + first-name prefix, transliteration,
    inner surname); a name no rule places is not on the list, never a guess."""
    candidates: dict[str, tuple[str, str]] = {}
    homonyms: set[str] = set()
    for label in ("home", "away"):
        side = entry.get(label) or {}
        for group, where in (("starters", "XI"), ("substitutes", "ławka"),
                             ("missing", None)):
            for listed in side.get(group) or []:
                name = listed.get("name")
                if not isinstance(name, str) or not name:
                    continue
                key = normalize_name(name)
                if key in candidates:
                    homonyms.add(key)
                candidates[key] = (
                    label, where or str(listed.get("type") or "missing"))
    for key in homonyms:
        del candidates[key]
    pool: dict[str, dict[str, Any]] = {k: {} for k in candidates}
    sampled = (sample or {}).get("players") or {}
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for leg in legs:
        if not _is_player_leg(leg):
            continue
        subject, market = str(leg["subject"]), str(leg.get("market"))
        if (subject, market) in seen:
            continue
        seen.add((subject, market))
        row: dict[str, Any] = {"subject": subject, "market": market}
        own = (sampled.get(f"{market}|{subject}")
               if isinstance(sampled, Mapping) else None)
        if isinstance(own, Mapping) and isinstance(own.get("matched_name"), str):
            key = normalize_name(str(own["matched_name"]))
            own_label = {"side_a": "home", "side_b": "away"}.get(
                str(own.get("side")))
            if key in candidates and own_label in (None, candidates[key][0]):
                side, where = candidates[key]
                row.update(status=where, side=side, matched_name=key,
                           match_rule=str(own.get("match_rule") or "fuzzy"))
                out.append(row)
                continue
        rules = (("fuzzy", match_player), ("tokens", match_player_by_tokens),
                 ("surname", match_player_by_surname),
                 ("transliteration", match_player_by_transliteration),
                 ("inner_surname", match_player_by_inner_surname))
        for rule, matcher in rules:
            found = matcher(subject, pool)
            if found:
                side, where = candidates[found]
                row.update(status=where, side=side, matched_name=found, match_rule=rule)
                break
        else:
            row["status"] = "nie ma na liście Sofascore (lub nazwa nie dopasowana)"
        out.append(row)
    return out


def lineups_block(
    con: sqlite3.Connection,
    sport: str,
    entry: Mapping[str, Any] | None,
    legs: Sequence[Mapping[str, Any]],
    team_ids: Mapping[str, object],
    kickoff_ts: int,
    sample: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """The dossier's `lineups`: Sofascore's predicted or confirmed XI, the
    missing / doubtful players, each player leg's player, and each side's
    regulars (from its cached post-match line-ups) not in the XI. Display
    only; what is not known says `missing`."""
    if sport not in prematch_lineups.SPORTS:
        return {"missing": f"Sofascore nie podaje składów w tym kształcie ({sport})"}
    entry = entry or {}
    status = str(entry.get("status") or "NOT_ASKED")
    out: dict[str, Any] = {
        "source": f"Sofascore /event/{{id}}/lineups ({prematch_lineups.FILE})",
        "status": status,
        "asked_at_utc": entry.get("asked_at_utc"),
    }
    if isinstance(entry.get("last_attempt"), Mapping):
        out["last_attempt"] = entry["last_attempt"]
    if status != prematch_lineups.OK:
        why = {"NOT_ASKED": "nie pytano (read_set --no-lineups, mecz rozpoczęty "
                            "lub brak odpowiedzi)",
               prematch_lineups.NOT_PUBLISHED: "Sofascore nie opublikował składu"}
        out["missing"] = why.get(status, f"zapytanie nieudane ({status})")
        return out
    confirmed = entry.get("confirmed") is True
    out["confirmed"] = confirmed
    out["kind"] = "potwierdzony" if confirmed else "przewidywany (nie potwierdzony)"
    for label in ("home", "away"):
        side = entry.get(label) or {}
        view: dict[str, Any] = {}
        if side.get("missing_side"):
            view["missing"] = side["missing_side"]
        else:
            if side.get("formation"):
                view["formation"] = side["formation"]
            view["starters"] = [
                " ".join(str(x) for x in (r.get("name"), f"({r['position']})"
                         if r.get("position") else None) if x)
                for r in side.get("starters") or []]
            view["substitutes"] = [
                str(r.get("name")) for r in side.get("substitutes") or []]
            view["missing_players"] = side.get("missing") or []
            if not side.get("missing_listed"):
                view["missing_players_note"] = "Sofascore nie podał listy absencji"
        team = team_ids.get(label)
        if isinstance(team, int) and "missing" not in view:
            reg = regulars(con, team, kickoff_ts)
            if "players" in reg:
                rows = [{**r, "status": _where(side, r["id"])
                         or "nie ma na liście Sofascore"} for r in reg["players"]]
                reg["players"] = rows
                view["regulars_not_in_xi"] = [
                    f"{r['name']} ({r['starts']}/{reg['lineups_cached']}):"
                    f" {r['status']}"
                    for r in rows if r["status"] != "XI"]
            view["regulars"] = reg
        elif "missing" not in view:
            view["regulars"] = {"missing": "brak id drużyny"}
        out[label] = view
    out["player_legs"] = player_leg_status(entry, legs, sample)
    return out


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
    lineup_entries: Mapping[str, Mapping[str, Any]] | None = None,
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
        "Sofascore pobrana przez read_set / build_slip; lineups_prematch.json: "
        "skład Sofascore przed meczem); bez zapytań",
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
    if sport == "football" and isinstance(home_id, int) and isinstance(away_id, int):
        profiles = {
            "home": style_profile(con, home_id, kickoff_ts),
            "away": style_profile(con, away_id, kickoff_ts),
        }
        metrics = sorted({found[0] for x in legs
                          if (found := leg_metric(str(x.get("market"))))})
        cache: dict[tuple[int, int], dict[str, Any]] = {}
        side_games = {
            "home": _metric_games(con, home_id, kickoff_ts, metrics, cache),
            "away": _metric_games(con, away_id, kickoff_ts, metrics, cache),
        }
        league = league_rates(
            con, _competitions_for(detail, side_games,
                                   {"home": home_id, "away": away_id},
                                   con, kickoff_ts),
            kickoff_ts, metrics) if metrics and detail else {}
        doc["style"] = {
            "source": "statystyki Sofascore ostatnich meczów o stawkę (bez "
            "towarzyskich), [za, przeciw] z perspektywy drużyny; crosses = "
            "dośrodkowania próbowane; matchup liczy rynek nogi tak jak SETTLE "
            "(metrics.extract_metric)",
            "home": profiles["home"],
            "away": profiles["away"],
            "league": {k: v for k, v in league.items() if k != "values"}
            or {"missing": "liga bez 30 meczów ze statystykami w cache"},
            "matchup": [row for row, _ in matchup_rows(
                legs, side_games, side_names, league)],
        }
    doc["market"] = market_block(run, sport, legs, offer, event_id)
    if sport in TEAM_SPORTS:
        doc["lineups"] = lineups_block(
            con, sport, (lineup_entries or {}).get(str(event_id)), legs,
            {"home": home_id, "away": away_id}, kickoff_ts,
            samples.get(event_id))
    doc["web_checklist"] = web_checklist(sport, header, side_names)
    lineup_line = _lineup_checklist(doc.get("lineups"))
    if lineup_line:
        doc["web_checklist"] = [
            lineup_line if x.startswith("przewidywane / potwierdzone składy") else x
            for x in doc["web_checklist"]]
        if lineup_line not in doc["web_checklist"]:
            doc["web_checklist"].append(lineup_line)
    if h2h_asked.get("status") != h2h_fetch.OK:
        asked = h2h_asked.get("status") or "NOT_ASKED"
        doc["web_checklist"].append(
            f"h2h: Sofascore nie odpowiedział ({asked})"
            f" - ostatnie spotkania {side_names['home'] or '?'} - "
            f"{side_names['away'] or '?'} i statystyki rynków nóg z sieci")
    return doc


def _lineup_checklist(block: Mapping[str, Any] | None) -> str | None:
    """The web checklist's line-up item, saying what the dossier already has."""
    if not isinstance(block, Mapping) or block.get("status") != prematch_lineups.OK:
        return None
    kind = "POTWIERDZONY" if block.get("confirmed") else "PRZEWIDYWANY"
    return (f"składy: dossier ma skład Sofascore ({kind}, {block.get('asked_at_utc')})"
            " - sprawdź tylko zmiany od tej godziny i absencje spoza listy Sofascore")


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
    out_dir: Path | None = None,
) -> dict[int, str]:
    """Write one dossier per match of `legs`, set each leg's `dossier` to its
    path; returns {event id: path}. A match whose dossier fails keeps no
    `dossier` field and is listed on stderr by the caller - never a guess.
    `out_dir` writes them there instead of `<run>/dossier` (a test or a
    scratch read never overwrites the day's dossiers)."""
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
    lineup_entries = prematch_lineups.load(run)
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
                lineup_entries=lineup_entries,
            )
            path = (out_dir / f"{sport}_{event_id}.json" if out_dir is not None
                    else dossier_path(run, sport, event_id))
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
    out_dir: Path | None = None,
) -> str:
    """write_for_legs for a read-set writer: one line for its output. A
    failure is reported, never raised - a read set without dossiers is still
    a read set (the analyst says "brak dossier")."""
    path = Path(db_path or DB_PATH)
    if not path.exists():
        return f"dossier: brak bazy {path} - nogi bez dossier"
    try:
        written = write_for_legs(run, legs, db_path=path, now=now, out_dir=out_dir)
    except (sqlite3.Error, OSError, ValueError, KeyError, TypeError) as exc:
        return f"dossier: BŁĄD {type(exc).__name__}: {exc} - nogi bez dossier"
    return f"dossier: {len(written)} meczów -> {out_dir or run / 'dossier'}"
