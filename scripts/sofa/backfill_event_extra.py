"""Payloads beyond statistics / incidents / lineups for finished events, into
sofa_event_extra (bet.sofa.cache.EXTRA_KINDS).

    --kind shotmap --sport football     every shot of a match (player,
        coordinates, outcome, body part): the outside-box / header / foot
        markets Superbet prices and /lineups cannot split. Targets: football
        events whose cached lineups hold per-player statistics - the events
        a player sample is built from.
    --kind point_by_point --sport tennis   every point of every game: the
        "after N games" / "after N points" markets. Targets: tennis events
        with a cached /statistics row - the events the tennis model reads.

Measured before writing (2026-10-14, docs/sofa/history/RAPORT_LUKI_RYNKOW_
2026-10-14.md): 352 football shotmaps of 10-14's player samples, team
`totalShotsOutsideBox` reproduced on 87 of 90 sides by x > 17, the shot count
equal to the lineups' totalShots on 3,013 of 3,045 player-matches.

Same client, token bucket and bridge as the pipeline; workers =
SOFA_MAX_CONCURRENCY. Newest first, resumable (an event with a row is never
asked again; `{}` records an empty answer), run in short chunks:

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/backfill_event_extra.py \\
        --kind shotmap --sport football --days 365 --dry-run
    PYTHONPATH=src:. .venv/bin/python scripts/sofa/backfill_event_extra.py \\
        --kind shotmap --sport football --days 365 --max-minutes 7

A competition whose first MAX_BARREN_MISSES answers are all empty is skipped
for the rest of the run. Exit: 0 OK, 1 PARTIAL (requests failed), 2 FAILED
(the breaker opened - a refusal: slow down, never retry at once).
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
import threading
import time
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Any

from bet.sofa.cache import EXTRA_KINDS, PROVISIONAL_FETCH_HOURS, SofaCache
from bet.sofa.client import SofascoreClient, breaker_tripped
from bet.sofa.config import SofaConfig
from bet.sofa.errors import CircuitOpenError, ProviderError
from bet.sofa.samples import FRIENDLY_COMPETITION_IDS
from scripts.sofa.backfill_event_stats import MAX_BARREN_MISSES
from scripts.sofa.backfill_listings import read_only_connection

LINEUP_STATS_LIKE = '%"statistics": {"%'

# (kind, sport) -> the client method; the pairs this script knows how to judge.
SUPPORTED: dict[tuple[str, str], str] = {
    ("shotmap", "football"): "event_shotmap",
    ("point_by_point", "tennis"): "event_point_by_point",
}


def asked(db_path: str, kind: str) -> set[int]:
    """Events that already have a sofa_event_extra row of this kind."""
    conn = read_only_connection(db_path)
    try:
        return {int(r[0]) for r in conn.execute(
            "SELECT sofascore_event_id FROM sofa_event_extra WHERE kind = ?", (kind,))}
    finally:
        conn.close()


def eligible(db_path: str, kind: str) -> set[int]:
    """The events worth asking: football with per-player lineups for a
    shotmap, tennis with a /statistics row for point-by-point."""
    conn = read_only_connection(db_path)
    try:
        if kind == "shotmap":
            # A non-empty per-player statistics dict, as cache.save_event_lineups
            # writes it (json.dumps): the SQL form of has_player_statistics,
            # without parsing ~55k payloads (11 GB resident on 2026-10-14).
            return {int(r[0]) for r in conn.execute(
                "SELECT sofascore_event_id FROM sofa_event_stats "
                "WHERE lineups_json LIKE ?", (LINEUP_STATS_LIKE,))}
        return {int(r[0]) for r in conn.execute(
            "SELECT sofascore_event_id FROM sofa_event_stats "
            "WHERE statistics_json IS NOT NULL AND length(statistics_json) > 2")}
    finally:
        conn.close()


def candidate_events(
    db_path: str, wanted: set[int], since_ts: int, until_ts: int,
    sport: str, index_fallback: bool,
) -> list[dict[str, Any]]:
    """{id, startTimestamp, competition, status} of the wanted events, from
    the listing indexes in SQL - never the whole listing history in memory
    (the in-memory _sport_events read held 15 GB on 2026-10-14). An event the
    index lacks reads its start from sofa_listing_event with no competition;
    a cached lineups / statistics row exists only for a terminal match."""
    conn = read_only_connection(db_path)
    try:
        conn.execute("CREATE TEMP TABLE want (id INTEGER PRIMARY KEY)")
        conn.executemany("INSERT INTO want VALUES (?)", [(i,) for i in wanted])
        out: dict[int, dict[str, Any]] = {}
        for eid, ts, comp, status in conn.execute(
            "SELECT l.event_id, l.start_ts, "
            "json_extract(l.event_json, '$.tournament.uniqueTournament.id'), "
            "json_extract(l.event_json, '$.status.type') "
            "FROM sofa_listed_event l JOIN want w ON w.id = l.event_id "
            "WHERE l.sport = ?", (sport,)
        ):
            out[int(eid)] = {"id": int(eid), "startTimestamp": ts,
                             "competition": comp, "status": status or "finished"}
        fallback = conn.execute(
            "SELECT l.event_id, MIN(l.start_ts) FROM sofa_listing_event l "
            "JOIN want w ON w.id = l.event_id GROUP BY l.event_id"
        ) if index_fallback else []
        for eid, ts in fallback:
            out.setdefault(int(eid), {"id": int(eid), "startTimestamp": ts,
                                      "competition": None, "status": "finished"})
    finally:
        conn.close()
    return [e for e in out.values()
            if e["startTimestamp"] and since_ts <= int(e["startTimestamp"]) <= until_ts]


def select_targets(
    events: Iterable[dict[str, Any]], done: set[int]
) -> list[dict[str, Any]]:
    """Finished, non-friendly, never asked; newest first."""
    out = [e for e in events
           if e["id"] not in done
           and e.get("competition") not in FRIENDLY_COMPETITION_IDS
           and (e.get("status") or "finished") == "finished"]
    return sorted(out, key=lambda e: -int(e.get("startTimestamp") or 0))


def has_content(kind: str, payload: object) -> bool:
    """A payload worth having: at least one shot / one set of points."""
    if not isinstance(payload, dict):
        return False
    key = {"shotmap": "shotmap", "point_by_point": "pointByPoint",
           "incidents": "incidents"}[kind]
    return bool(payload.get(key))


class Backfill:
    def __init__(self, fetch: Callable[[int], Any], cache: Any, kind: str,
                 deadline: float | None, client: Any) -> None:
        self.fetch_one, self.cache, self.kind = fetch, cache, kind
        self.deadline, self.client = deadline, client
        self.stop = threading.Event()
        self.timed_out = threading.Event()
        self.lock = threading.Lock()
        self.counts = {"done": 0, "hit": 0, "empty": 0, "errors": 0,
                       "skipped_barren": 0}
        self.hits: dict[int | None, int] = {}
        self.misses: dict[int | None, int] = {}

    def _barren(self, comp: int | None) -> bool:
        with self.lock:
            return (self.misses.get(comp, 0) >= MAX_BARREN_MISSES
                    and not self.hits.get(comp))

    def fetch(self, event: dict[str, Any]) -> None:
        if self.stop.is_set() or self.timed_out.is_set():
            return
        if self.deadline is not None and time.monotonic() >= self.deadline:
            self.timed_out.set()
            return
        comp = event.get("competition")
        if self._barren(comp):
            with self.lock:
                self.counts["skipped_barren"] += 1
            return
        eid = int(event["id"])
        try:
            got = self.fetch_one(eid)
        except CircuitOpenError:
            self.stop.set()
            return
        except ProviderError:
            with self.lock:
                self.counts["errors"] += 1
            if breaker_tripped(self.client):
                self.stop.set()
            return
        ok = has_content(self.kind, got)
        self.cache.save_event_extra(eid, self.kind, got if ok else None, "finished")
        with self.lock:
            self.counts["done"] += 1
            self.counts["hit" if ok else "empty"] += 1
            bucket = self.hits if ok else self.misses
            bucket[comp] = bucket.get(comp, 0) + 1
            if self.counts["done"] % 500 == 0:
                print(json.dumps({"ts_utc": datetime.now(UTC).isoformat(),
                                  **self.counts}), flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--kind", required=True, choices=sorted(EXTRA_KINDS))
    ap.add_argument("--sport", required=True)
    ap.add_argument("--days", type=int, default=365)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--max-minutes", type=float, default=None,
                    help="start no new event after this many minutes")
    args = ap.parse_args()
    method = SUPPORTED.get((args.kind, args.sport))
    if method is None:
        print(f"unsupported --kind {args.kind} --sport {args.sport}; "
              f"known: {sorted(SUPPORTED)}", file=sys.stderr)
        return 2

    config = SofaConfig.from_env()
    if not config.run_id:
        config = dataclasses.replace(
            config, run_id=f"backfill-{args.kind}-"
            + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ"))
    cache = SofaCache(config)  # creates sofa_event_extra on first use
    now = int(time.time())
    # The listing index's sport slug; only a shotmap's wanted set (football
    # lineups) is one sport already, so only it may fall back to the
    # sport-less start index.
    events = candidate_events(
        config.db_path, eligible(config.db_path, args.kind),
        now - args.days * 86400, now - int(PROVISIONAL_FETCH_HOURS * 3600),
        args.sport, index_fallback=args.kind == "shotmap")
    targets = select_targets(events, asked(config.db_path, args.kind))
    if args.limit is not None:
        targets = targets[: args.limit]
    print(json.dumps({"run_id": config.run_id, "kind": args.kind,
                      "sport": args.sport, "days": args.days,
                      "targets": len(targets)}), flush=True)
    if args.dry_run or not targets:
        return 0

    client = SofascoreClient(config)
    deadline = time.monotonic() + args.max_minutes * 60 if args.max_minutes else None
    runner = Backfill(getattr(client, method), cache, args.kind, deadline, client)
    with ThreadPoolExecutor(max_workers=max(1, config.max_concurrency)) as pool:
        list(pool.map(runner.fetch, targets))
    print(json.dumps({"final": True, "circuit_open": runner.stop.is_set(),
                      "timed_out": runner.timed_out.is_set(),
                      "targets": len(targets), **runner.counts}), flush=True)
    return 2 if runner.stop.is_set() else (1 if runner.counts["errors"] else 0)


if __name__ == "__main__":
    sys.exit(main())
