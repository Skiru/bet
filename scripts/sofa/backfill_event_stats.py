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
    competitions: set[int],
    already_asked: set[int],
    since_ts: int,
) -> list[dict[str, Any]]:
    """Finished football events in `competitions` since `since_ts` whose
    statistics were never asked for, newest first, one entry per event.

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
            sport = ((tournament.get("category") or {}).get("sport") or {}).get("slug")
            if sport != "football":
                continue
            comp = (tournament.get("uniqueTournament") or {}).get("id")
            if comp not in competitions:
                continue
            if statistics_are_hopeless(event):
                continue
            seen[event_id] = event
    return sorted(seen.values(), key=lambda e: -int(e["startTimestamp"]))


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


def _already_asked(db_path: str) -> set[int]:
    with get_connection(db_path) as conn:
        return {
            int(r["sofascore_event_id"])
            for r in conn.execute("SELECT sofascore_event_id FROM sofa_event_stats")
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

    def __init__(self, client: Any, cache: Any) -> None:
        self.client = client
        self.cache = cache
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
        if self.stop.is_set():
            return
        comp = _competition(event)
        if comp in self.exhausted():
            with self.lock:
                self.counts["skipped_barren"] += 1
            return
        event_id = int(event["id"])
        try:
            stats = self.client.event_statistics(event_id)
            incidents = self.client.event_incidents(event_id)
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
    args = ap.parse_args()

    config = SofaConfig.from_env()
    if not config.run_id:
        config = dataclasses.replace(
            config,
            run_id="backfill-stats-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ"),
        )

    comps = board_competitions(config.runs_dir)
    since = int(time.time()) - args.days * 86400
    targets = select_targets(
        _iter_listings(config.db_path), comps, _already_asked(config.db_path), since
    )
    if args.limit is not None:
        targets = targets[: args.limit]
    print(json.dumps({
        "run_id": config.run_id, "competitions": len(comps),
        "targets": len(targets), "requests": 2 * len(targets),
    }), flush=True)
    if args.dry_run or not targets:
        return 0

    runner = Backfill(SofascoreClient(config), SofaCache(config))
    with ThreadPoolExecutor(max_workers=max(1, config.max_concurrency)) as pool:
        list(pool.map(runner.fetch_one, targets))

    summary = {"final": True, "circuit_open": runner.stop.is_set(), **runner.counts,
               "competitions_given_up": len(runner.exhausted())}
    print(json.dumps(summary), flush=True)
    return 2 if runner.stop.is_set() else (1 if runner.counts["errors"] else 0)


if __name__ == "__main__":
    sys.exit(main())
