#!/usr/bin/env python3
"""Fetch /statistics and /incidents for finished football events we already know.

The cache holds the listings of every team that was ever on a board - 516,168
events on 2026-09-25 - but statistics for only 33,713 of them, because SAMPLES
only asks for the ten matches it needs. Goals come with the listing, so
`goals_*` baselines are fitted from 55-75k matches while corners, shots,
fouls and card points are fitted from 1-3k. A league that has goals but no
corners baseline shrinks its corners rows toward the global pool: on the
2026-09-25 sheet that was 3,542 of 7,560 football rows (47%).

This reads no listing and discovers no event. It only asks for the statistics
of events the cache already lists, restricted to the competitions that have
actually been on a board, newest first - so a run cut short has still filled
the part that matters most. `--board-days N` narrows it further to the
matches of the teams/players on the last N boards (backfill_listings'
board_entities), i.e. the sides we actually price. It is resumable: an event already in
`sofa_event_stats` (including an asked-and-404 row) is never asked again.

Same client, same token bucket, same bridge as SAMPLES - it cannot be faster
than the pipeline and must not try to be.

The measured sports (--sport hockey / basketball / volleyball, since
2026-10-02). The cache holds their results (listings) only; no model of a
player line or a team statistic can be fitted without /statistics and
/lineups (docs/sofa/MODELE_HOKEJ_KOSZ_SIATKA.md). They differ from
football/tennis in three ways, each on purpose:

  * a route is "asked" only when ITS column is written: SHADOW_SETTLE saves
    /lineups alone (statistics_json NULL), and the football rule "a row
    exists, so it was asked" would read every such game as a statistics 404.
    A /statistics 404 is therefore written as `{}` for these sports, so a
    NULL keeps meaning "never asked" (nothing reads their statistics yet);
  * --with-lineups also asks /lineups (cache.save_event_lineups; a 404 is
    the `{}` "asked, nothing published" fact). Barren competitions are kept
    per route: a league that publishes no box score may still publish team
    statistics, and the other way round;
  * a game younger than cache.PROVISIONAL_FETCH_HOURS is not asked: Sofascore's
    early snapshot can be wrong (2026-09-28) and SHADOW_SETTLE asks those
    fresh; --board-days reads the shadow boards (runs/sofa/shadow/<sport>/
    <date>/), not RESOLVE's, see shadow_board_entities.

Usage:
    PYTHONPATH=src:. .venv/bin/python scripts/sofa/backfill_event_stats.py --dry-run
    PYTHONPATH=src:. .venv/bin/python scripts/sofa/backfill_event_stats.py --days 400
    PYTHONPATH=src:. .venv/bin/python scripts/sofa/backfill_event_stats.py \\
        --sport tennis --days 365 --board-days 7 --max-minutes 7
    PYTHONPATH=src:. .venv/bin/python scripts/sofa/backfill_event_stats.py \\
        --sport hockey --days 730 --with-lineups --max-minutes 7
"""

from __future__ import annotations

import argparse
import dataclasses
import glob
import json
import sqlite3
import sys
import threading
import time
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bet.sofa.cache import PROVISIONAL_FETCH_HOURS, SofaCache
from bet.sofa.client import SofascoreClient
from bet.sofa.config import SofaConfig
from bet.sofa.errors import CircuitOpenError, ProviderError
from bet.sofa.listing_index import iter_indexed_events
from bet.sofa.names import normalize_name
from bet.sofa.samples import statistics_are_hopeless
from scripts.sofa.backfill_listings import (
    SPORT_SLUGS,
    board_entities,
    read_only_connection,
)

# The measured sports: results only in the cache, graded by SHADOW_SETTLE.
SHADOW_SPORTS = ("hockey", "basketball", "volleyball")


def board_competitions(runs_dir: str, sport: str = "football") -> set[int]:
    """Every competition id that has appeared in a RESOLVE artifact."""
    comps: set[int] = set()
    for path in glob.glob(str(Path(runs_dir) / "*" / "02_fixtures.json")):
        try:
            fixtures = json.loads(Path(path).read_text())
        except (OSError, json.JSONDecodeError):
            continue
        for fx in fixtures:
            if fx.get("sport") == sport and fx.get("competition_id") is not None:
                comps.add(int(fx["competition_id"]))
    return comps


def select_targets(
    listings: Iterable[list[dict[str, Any]]],
    competitions: set[int] | None,
    already_asked: set[int],
    since_ts: int,
    barren: set[int] | frozenset[int] = frozenset(),
    sport: str = "football",
    entities: set[int] | None = None,
) -> list[dict[str, Any]]:
    """Finished `sport` events in `competitions` since `since_ts` whose
    statistics were never asked for, newest first, one entry per event.

    `entities`, when given, keeps only events one of whose sides is in it
    (the teams/players on recent boards); None keeps every side.

    `competitions=None` takes every competition. Tennis passes it: a tennis
    competition id is one week of one tournament, so the board's ids say
    nothing about next week's, and the cache only lists players that were on
    a board anyway.

    An event a tournament is known never to publish statistics for is left
    out rather than asked: it is the same prediction SAMPLES makes, and the
    cache is not written for it, so a later run is still free to ask.
    """
    seen: dict[int, dict[str, Any]] = {}
    for events in listings:
        for event in events:
            event_id = event.get("id")
            if not isinstance(event_id, int) or event_id in already_asked:
                continue
            if (event.get("status") or {}).get("type") != "finished":
                continue
            if (event.get("startTimestamp") or 0) < since_ts:
                continue
            tournament = event.get("tournament") or {}
            category = tournament.get("category") or {}
            event_sport = (category.get("sport") or {}).get("slug")
            if event_sport != sport:
                continue
            comp = (tournament.get("uniqueTournament") or {}).get("id")
            if competitions is not None and comp not in competitions:
                continue
            if comp in barren:
                continue
            if entities is not None and not any(
                    (event.get(side) or {}).get("id") in entities
                    for side in ("homeTeam", "awayTeam")):
                continue
            if statistics_are_hopeless(event):
                continue
            seen[event_id] = event
    return sorted(seen.values(), key=lambda e: -int(e["startTimestamp"]))


def barren_competitions(
    listings: Iterable[list[dict[str, Any]]],
    asked: dict[int, bool],
    threshold: int | None = None,
) -> set[int]:
    """Competitions the cache has already asked `threshold`+ times with not
    one success - so a chunked run does not pay MAX_BARREN_MISSES again per
    competition on every chunk. `asked` maps event id -> it had statistics."""
    limit = MAX_BARREN_MISSES if threshold is None else threshold
    hits: dict[int, int] = {}
    misses: dict[int, int] = {}
    seen: set[int] = set()
    for events in listings:
        for event in events:
            event_id = event.get("id")
            if not isinstance(event_id, int) or event_id in seen:
                continue
            if event_id not in asked:
                continue
            seen.add(event_id)
            comp = _competition(event)
            if comp is None:
                continue
            bucket = hits if asked[event_id] else misses
            bucket[comp] = bucket.get(comp, 0) + 1
    return {c for c, n in misses.items() if n >= limit and not hits.get(c)}


def _iter_listings(db_path: str) -> Iterable[list[dict[str, Any]]]:
    # Planning only reads: the connection is read-only, so a --dry-run beside
    # a live pipeline run cannot write or migrate the cache.
    conn: sqlite3.Connection = read_only_connection(db_path)
    listed: set[int] = set()
    try:
        for row in conn.execute("SELECT events_json FROM sofa_entity_events"):
            try:
                payload = json.loads(row["events_json"])
            except (TypeError, json.JSONDecodeError):
                continue
            events = payload.get("events") if isinstance(payload, dict) else payload
            if isinstance(events, list):
                # Only finished copies hold an id back from the index: a stale
                # pre-match copy (a `next` page) is not a target, and must not
                # hide the finished indexed copy that is (F5).
                listed.update(e["id"] for e in events
                              if isinstance(e, dict) and isinstance(e.get("id"), int)
                              and (e.get("status") or {}).get("type") == "finished")
                yield events
        # Matches that slid out of every cached page (listing_index.py) still
        # want their statistics; nothing while the index is empty.
        extra: list[dict[str, Any]] = []
        for event in iter_indexed_events(conn, listed):
            extra.append(event)
            if len(extra) >= 1000:
                yield extra
                extra = []
        if extra:
            yield extra
    finally:
        conn.close()


def _already_asked(db_path: str) -> dict[int, bool]:
    """Event id -> whether the cached row carries statistics."""
    conn = read_only_connection(db_path)
    try:
        return {
            int(r["sofascore_event_id"]): r["has_stats"] == 1
            for r in conn.execute(
                "SELECT sofascore_event_id, statistics_json IS NOT NULL AS has_stats "
                "FROM sofa_event_stats"
            )
        }
    finally:
        conn.close()


# A competition whose first MAX_BARREN_MISSES events all answer 404 on
# /statistics, with not one success, publishes no statistics: asking for the
# rest of its season is bridge time spent on a known answer. Measured on the
# 2026-09-25 run: the 404 share rose from 39% to 83% as the run walked into
# older and lower-tier matches. One success keeps the competition in for good.
MAX_BARREN_MISSES = 25


def _competition(event: dict[str, Any]) -> int | None:
    unique = ((event.get("tournament") or {}).get("uniqueTournament") or {})
    comp = unique.get("id")
    return comp if isinstance(comp, int) else None


# --- the measured sports (hockey / basketball / volleyball) -------------------


def _shadow_day_dirs(runs_dir: str, sport: str, days: int) -> list[Path]:
    """The last `days` shadow day directories of `sport`, oldest first."""
    if days <= 0:
        return []
    root = Path(runs_dir) / "shadow" / sport
    dirs = [p for p in root.glob("????-??-??") if p.is_dir()]
    return sorted(dirs)[-days:]


def shadow_board_sides(
    runs_dir: str, sport: str, days: int
) -> tuple[set[str], set[int]]:
    """What the last `days` shadow boards say about their games: every
    Superbet team name (snapshots.jsonl team1 / team2, normalised as RESOLVE
    keys sofa_entity) and every Sofascore event id SHADOW_SETTLE found
    (settled.json). The shadow boards carry no Sofascore team id: a snapshot
    is Superbet's, and a settled game names its event, not its sides."""
    names: set[str] = set()
    events: set[int] = set()
    for day in _shadow_day_dirs(runs_dir, sport, days):
        try:
            lines = (day / "snapshots.jsonl").read_text(encoding="utf-8").splitlines()
        except OSError:
            lines = []
        for line in lines:
            try:
                snap = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(snap, dict):
                continue
            for key in ("team1", "team2"):
                name = snap.get(key)
                if isinstance(name, str) and name.strip():
                    names.add(normalize_name(name))
        try:
            settled = json.loads((day / "settled.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        games = settled.get("events") if isinstance(settled, dict) else None
        for game in (games or {}).values() if isinstance(games, dict) else []:
            eid = game.get("sofascore_event_id") if isinstance(game, dict) else None
            if isinstance(eid, int):
                events.add(eid)
    return names, events


def shadow_board_entities(
    runs_dir: str, sport: str, days: int, db_path: str
) -> set[int]:
    """Sofascore team ids on the last `days` shadow boards, from the cache only.

    Two readings, both read-only: a settled game's cached /event payload
    (sofa_event_detail - its homeTeam / awayTeam ids, the surest), and a
    board name RESOLVE already verified (sofa_entity, status 'verified'), so
    today's unsettled board counts too. A name never resolved is not
    guessed at: it has no listing to backfill from anyway.
    """
    names, events = shadow_board_sides(runs_dir, sport, days)
    out: set[int] = set()
    if not names and not events:
        return out
    conn = read_only_connection(db_path)
    try:
        for eid in sorted(events):
            row = conn.execute(
                "SELECT detail_json FROM sofa_event_detail "
                "WHERE sofascore_event_id = ?",
                (eid,),
            ).fetchone()
            if row is None:
                continue
            try:
                payload = json.loads(row["detail_json"])
            except (TypeError, json.JSONDecodeError):
                continue
            event = payload.get("event") if isinstance(payload, dict) else None
            if not isinstance(event, dict):
                continue
            for side in ("homeTeam", "awayTeam"):
                tid = (event.get(side) or {}).get("id")
                if isinstance(tid, int):
                    out.add(tid)
        slug = SPORT_SLUGS[sport]
        for name in sorted(names):
            row = conn.execute(
                "SELECT sofascore_id FROM sofa_entity WHERE sport = ? "
                "AND query_key = ? AND status = 'verified'",
                (slug, name),
            ).fetchone()
            if row is not None and isinstance(row["sofascore_id"], int):
                out.add(int(row["sofascore_id"]))
    finally:
        conn.close()
    return out


@dataclass(frozen=True)
class RouteState:
    """What the cache holds for one event, per route: None never asked,
    True an answer with content, False asked and nothing (a 404 `{}`)."""

    stats: bool | None
    lineups: bool | None


def _column_state(raw: str | None) -> bool | None:
    if raw is None:
        return None
    try:
        return bool(json.loads(raw))
    except (TypeError, json.JSONDecodeError):
        return False


def _route_states(db_path: str) -> dict[int, RouteState]:
    """Event id -> RouteState, read per column (see the module docstring)."""
    conn = read_only_connection(db_path)
    try:
        return {
            int(r["sofascore_event_id"]): RouteState(
                _column_state(r["statistics_json"]), _column_state(r["lineups_json"])
            )
            for r in conn.execute(
                "SELECT sofascore_event_id, statistics_json, lineups_json "
                "FROM sofa_event_stats"
            )
        }
    finally:
        conn.close()


@dataclass(frozen=True)
class ShadowTarget:
    """One event and the routes it still needs."""

    event: dict[str, Any]
    stats: bool
    lineups: bool


def _sport_events(
    listings: Iterable[list[dict[str, Any]]], slug: str
) -> list[dict[str, Any]]:
    """Finished events of one Sofascore sport, once each (first copy kept)."""
    seen: dict[int, dict[str, Any]] = {}
    for events in listings:
        for event in events:
            event_id = event.get("id")
            if not isinstance(event_id, int) or event_id in seen:
                continue
            if (event.get("status") or {}).get("type") != "finished":
                continue
            tournament = event.get("tournament") or {}
            category = tournament.get("category") or {}
            if (category.get("sport") or {}).get("slug") != slug:
                continue
            seen[event_id] = event
    return list(seen.values())


def _is_friendly(event: dict[str, Any]) -> bool:
    """score_model._is_friendly: friendlies are out of the rating (CLAUDE.md),
    so their statistics would be bridge time nothing reads."""
    unique = (event.get("tournament") or {}).get("uniqueTournament") or {}
    return "friendly" in str(unique.get("name") or "").lower()


def route_barren(
    events: Iterable[dict[str, Any]],
    states: dict[int, RouteState],
    route: str,
    threshold: int | None = None,
) -> set[int]:
    """barren_competitions for one route of the measured sports."""
    asked: dict[int, bool] = {}
    for eid, st in states.items():
        got = st.stats if route == "stats" else st.lineups
        if got is not None:
            asked[eid] = got
    return barren_competitions([list(events)], asked, threshold)


def select_shadow_targets(
    events: Iterable[dict[str, Any]],
    states: dict[int, RouteState],
    since_ts: int,
    until_ts: int,
    with_lineups: bool,
    barren_stats: set[int] | frozenset[int] = frozenset(),
    barren_lineups: set[int] | frozenset[int] = frozenset(),
    entities: set[int] | None = None,
) -> list[ShadowTarget]:
    """Finished events started in [since_ts, until_ts) with a route never
    asked, newest first. `until_ts` keeps out a game young enough for its
    answer to be Sofascore's early snapshot. Friendlies are left out, as the
    rating leaves them out. No competition filter: the cache lists only
    teams a shadow board named, and their opponents."""
    out: list[ShadowTarget] = []
    for event in events:
        ts = event.get("startTimestamp") or 0
        if not isinstance(ts, int) or ts < since_ts or ts >= until_ts:
            continue
        if entities is not None and not any(
                (event.get(side) or {}).get("id") in entities
                for side in ("homeTeam", "awayTeam")):
            continue
        if _is_friendly(event):
            continue
        st = states.get(int(event["id"]), RouteState(None, None))
        comp = _competition(event)
        need_stats = st.stats is None and comp not in barren_stats
        need_lineups = (
            with_lineups and st.lineups is None and comp not in barren_lineups
        )
        if need_stats or need_lineups:
            out.append(ShadowTarget(event, need_stats, need_lineups))
    return sorted(out, key=lambda t: -int(t.event["startTimestamp"]))


class Backfill:
    """One event at a time, from any number of worker threads."""

    def __init__(
        self,
        client: Any,
        cache: Any,
        deadline: float | None = None,
        sport: str = "football",
    ) -> None:
        self.client = client
        # Tennis SAMPLES reads /statistics only (samples.py needs_incidents is
        # football-only), so a tennis backfill asks one route, not two.
        self.with_incidents = sport == "football"
        self.cache = cache
        # time.monotonic() after which no new event is started. On 2026-09-25
        # the bridge was refused after ~23-26 min of continuous work in each
        # of two runs, at 11 and at 5 req/s alike, so runs are chunked by time.
        self.deadline = deadline
        self.timed_out = threading.Event()
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.counts = {"done": 0, "stats": 0, "no_stats": 0, "errors": 0,
                       "skipped_barren": 0}
        self.hits: dict[int | None, int] = {}
        self.misses: dict[int | None, int] = {}
        # The measured sports keep barren competitions per route (fetch_shadow).
        self.route_hits: dict[str, dict[int | None, int]] = {
            "stats": {}, "lineups": {}}
        self.route_misses: dict[str, dict[int | None, int]] = {
            "stats": {}, "lineups": {}}
        if sport in SHADOW_SPORTS:
            self.counts.update({"lineups": 0, "no_lineups": 0})

    def exhausted(self) -> set[int | None]:
        with self.lock:
            return {c for c, n in self.misses.items()
                    if n >= MAX_BARREN_MISSES and not self.hits.get(c)}

    def exhausted_route(self, route: str) -> set[int | None]:
        with self.lock:
            hits = self.route_hits[route]
            return {c for c, n in self.route_misses[route].items()
                    if n >= MAX_BARREN_MISSES and not hits.get(c)}

    def fetch_shadow(self, target: ShadowTarget) -> None:
        """One event of a measured sport: each route it still needs, each
        saved on its own - an error on /lineups does not lose /statistics."""
        if self.stop.is_set() or self.timed_out.is_set():
            return
        if self.deadline is not None and time.monotonic() >= self.deadline:
            self.timed_out.set()
            return
        comp = _competition(target.event)
        routes = [r for r, want in (("stats", target.stats),
                                    ("lineups", target.lineups))
                  if want and comp not in self.exhausted_route(r)]
        if not routes:
            with self.lock:
                self.counts["skipped_barren"] += 1
            return
        event_id = int(target.event["id"])
        answered = False
        for route in routes:
            try:
                if route == "stats":
                    got = self.client.event_statistics(event_id)
                else:
                    got = self.client.event_lineups(event_id)
            except CircuitOpenError:
                self.stop.set()
                return
            except ProviderError:
                with self.lock:
                    self.counts["errors"] += 1
                continue
            ok = isinstance(got, dict) and bool(got)
            if route == "stats":
                # `{}`, not NULL: NULL is "never asked" for these sports.
                self.cache.save_event_stats(
                    event_id, got if ok else {}, None, "finished")
            else:
                self.cache.save_event_lineups(
                    event_id, got if ok else None, "finished")
            answered = True
            with self.lock:
                key = route if ok else f"no_{route}"
                self.counts[key] += 1
                bucket = (self.route_hits if ok else self.route_misses)[route]
                bucket[comp] = bucket.get(comp, 0) + 1
        if answered:
            with self.lock:
                self.counts["done"] += 1
                if self.counts["done"] % 500 == 0:
                    print(json.dumps({"ts_utc": datetime.now(UTC).isoformat(),
                                      **self.counts}), flush=True)

    def fetch_one(self, event: dict[str, Any]) -> None:
        if self.stop.is_set() or self.timed_out.is_set():
            return
        if self.deadline is not None and time.monotonic() >= self.deadline:
            self.timed_out.set()
            return
        comp = _competition(event)
        if comp in self.exhausted():
            with self.lock:
                self.counts["skipped_barren"] += 1
            return
        event_id = int(event["id"])
        try:
            stats = self.client.event_statistics(event_id)
            incidents = (
                self.client.event_incidents(event_id) if self.with_incidents else None
            )
        except CircuitOpenError:
            # Sofascore or the bridge is refusing: stop every worker, do not
            # hammer a breaker that is telling us to wait.
            self.stop.set()
            return
        except ProviderError:
            # Nothing is written: an error is not an answer, and a later run
            # must be free to ask again.
            with self.lock:
                self.counts["errors"] += 1
            return
        # None statistics is the asked-and-404 row SAMPLES reads the same way.
        self.cache.save_event_stats(event_id, stats, incidents, "finished")
        with self.lock:
            self.counts["done"] += 1
            self.counts["stats" if stats else "no_stats"] += 1
            bucket = self.hits if stats else self.misses
            bucket[comp] = bucket.get(comp, 0) + 1
            if self.counts["done"] % 500 == 0:
                print(json.dumps({"ts_utc": datetime.now(UTC).isoformat(),
                                  **self.counts}), flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--days", type=int, default=400)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--sport", choices=("football", "tennis", *SHADOW_SPORTS),
                    default="football")
    ap.add_argument("--max-minutes", type=float, default=None,
                    help="start no new event after this many minutes")
    ap.add_argument("--board-days", type=int, default=None,
                    help="only matches of the teams/players on the last N "
                    "boards (RESOLVE artifacts; for hockey/basketball/"
                    "volleyball the shadow boards)")
    ap.add_argument("--with-lineups", action="store_true",
                    help="hockey/basketball/volleyball: also ask /lineups "
                    "(the box score player lines are graded on)")
    args = ap.parse_args()
    if args.with_lineups and args.sport not in SHADOW_SPORTS:
        ap.error("--with-lineups is for " + "/".join(SHADOW_SPORTS))

    config = SofaConfig.from_env()
    if not config.run_id:
        config = dataclasses.replace(
            config,
            run_id="backfill-stats-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ"),
        )
    if args.sport in SHADOW_SPORTS:
        return _main_shadow(args, config)

    comps = board_competitions(config.runs_dir) if args.sport == "football" else None
    entities = (
        None if args.board_days is None
        else board_entities(config.runs_dir, args.sport, args.board_days)
    )
    since = int(time.time()) - args.days * 86400
    asked = _already_asked(config.db_path)
    barren = barren_competitions(_iter_listings(config.db_path), asked)
    targets = select_targets(
        _iter_listings(config.db_path), comps, set(asked), since, barren,
        sport=args.sport, entities=entities,
    )
    if args.limit is not None:
        targets = targets[: args.limit]
    print(json.dumps({
        "run_id": config.run_id, "sport": args.sport,
        "competitions": None if comps is None else len(comps),
        "board_days": args.board_days,
        "board_entities": None if entities is None else len(entities),
        "targets": len(targets),
        "requests": (2 if args.sport == "football" else 1) * len(targets),
        "barren_competitions_skipped": len(barren),
    }), flush=True)
    if args.dry_run or not targets:
        return 0

    deadline = (
        time.monotonic() + args.max_minutes * 60 if args.max_minutes else None
    )
    runner = Backfill(
        SofascoreClient(config), SofaCache(config), deadline, sport=args.sport
    )
    with ThreadPoolExecutor(max_workers=max(1, config.max_concurrency)) as pool:
        list(pool.map(runner.fetch_one, targets))

    summary = {"final": True, "circuit_open": runner.stop.is_set(),
               "timed_out": runner.timed_out.is_set(), "targets": len(targets),
               **runner.counts, "competitions_given_up": len(runner.exhausted())}
    print(json.dumps(summary), flush=True)
    return 2 if runner.stop.is_set() else (1 if runner.counts["errors"] else 0)


def _main_shadow(args: argparse.Namespace, config: SofaConfig) -> int:
    """--sport hockey / basketball / volleyball (see the module docstring)."""
    slug = SPORT_SLUGS[args.sport]
    entities = (
        None if args.board_days is None
        else shadow_board_entities(
            config.runs_dir, args.sport, args.board_days, config.db_path)
    )
    now = int(time.time())
    since = now - args.days * 86400
    until = now - int(PROVISIONAL_FETCH_HOURS * 3600)
    states = _route_states(config.db_path)
    events = _sport_events(_iter_listings(config.db_path), slug)
    barren_stats = route_barren(events, states, "stats")
    barren_lineups = route_barren(events, states, "lineups")
    targets = select_shadow_targets(
        events, states, since, until, args.with_lineups,
        barren_stats, barren_lineups, entities)
    if args.limit is not None:
        targets = targets[: args.limit]
    stats_requests = sum(t.stats for t in targets)
    lineups_requests = sum(t.lineups for t in targets)
    print(json.dumps({
        "run_id": config.run_id, "sport": args.sport, "slug": slug,
        "days": args.days, "with_lineups": args.with_lineups,
        "board_days": args.board_days,
        "board_entities": None if entities is None else len(entities),
        "finished_events_listed": len(events),
        "targets": len(targets),
        "stats_requests": stats_requests,
        "lineups_requests": lineups_requests,
        "requests": stats_requests + lineups_requests,
        "barren_competitions_skipped": len(barren_stats),
        "barren_lineups_competitions_skipped": len(barren_lineups),
    }), flush=True)
    if args.dry_run or not targets:
        return 0

    deadline = (
        time.monotonic() + args.max_minutes * 60 if args.max_minutes else None
    )
    runner = Backfill(
        SofascoreClient(config), SofaCache(config), deadline, sport=args.sport
    )
    with ThreadPoolExecutor(max_workers=max(1, config.max_concurrency)) as pool:
        list(pool.map(runner.fetch_shadow, targets))

    summary = {"final": True, "circuit_open": runner.stop.is_set(),
               "timed_out": runner.timed_out.is_set(), "targets": len(targets),
               **runner.counts,
               "competitions_given_up": len(runner.exhausted_route("stats")),
               "lineups_competitions_given_up": len(
                   runner.exhausted_route("lineups"))}
    print(json.dumps(summary), flush=True)
    return 2 if runner.stop.is_set() else (1 if runner.counts["errors"] else 0)


if __name__ == "__main__":
    sys.exit(main())
