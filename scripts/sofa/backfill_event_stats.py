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
the part that matters most. It is resumable: an event already in
`sofa_event_stats` (including an asked-and-404 row) is never asked again.

Same client, same token bucket, same bridge as SAMPLES - it cannot be faster
than the pipeline and must not try to be.

Usage:
    PYTHONPATH=src:. .venv/bin/python scripts/sofa/backfill_event_stats.py --dry-run
    PYTHONPATH=src:. .venv/bin/python scripts/sofa/backfill_event_stats.py --days 400
"""

from __future__ import annotations

import argparse
import dataclasses
import glob
import json
import sys
import threading
import time
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bet.sofa.cache import SofaCache
from bet.sofa.client import SofascoreClient
from bet.sofa.config import SofaConfig
from bet.sofa.db import get_connection
from bet.sofa.errors import CircuitOpenError, ProviderError
from bet.sofa.samples import statistics_are_hopeless


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
) -> list[dict[str, Any]]:
    """Finished `sport` events in `competitions` since `since_ts` whose
    statistics were never asked for, newest first, one entry per event.

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
    with get_connection(db_path) as conn:
        for row in conn.execute("SELECT events_json FROM sofa_entity_events"):
            try:
                payload = json.loads(row["events_json"])
            except (TypeError, json.JSONDecodeError):
                continue
            events = payload.get("events") if isinstance(payload, dict) else payload
            if isinstance(events, list):
                yield events


def _already_asked(db_path: str) -> dict[int, bool]:
    """Event id -> whether the cached row carries statistics."""
    with get_connection(db_path) as conn:
        return {
            int(r["sofascore_event_id"]): r["has_stats"] == 1
            for r in conn.execute(
                "SELECT sofascore_event_id, statistics_json IS NOT NULL AS has_stats "
                "FROM sofa_event_stats"
            )
        }


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

    def exhausted(self) -> set[int | None]:
        with self.lock:
            return {c for c, n in self.misses.items()
                    if n >= MAX_BARREN_MISSES and not self.hits.get(c)}

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
    ap.add_argument("--sport", choices=("football", "tennis"), default="football")
    ap.add_argument("--max-minutes", type=float, default=None,
                    help="start no new event after this many minutes")
    args = ap.parse_args()

    config = SofaConfig.from_env()
    if not config.run_id:
        config = dataclasses.replace(
            config,
            run_id="backfill-stats-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ"),
        )

    comps = board_competitions(config.runs_dir) if args.sport == "football" else None
    since = int(time.time()) - args.days * 86400
    asked = _already_asked(config.db_path)
    barren = barren_competitions(_iter_listings(config.db_path), asked)
    targets = select_targets(
        _iter_listings(config.db_path), comps, set(asked), since, barren,
        sport=args.sport,
    )
    if args.limit is not None:
        targets = targets[: args.limit]
    print(json.dumps({
        "run_id": config.run_id, "sport": args.sport,
        "competitions": None if comps is None else len(comps),
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


if __name__ == "__main__":
    sys.exit(main())
