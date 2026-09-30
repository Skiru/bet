#!/usr/bin/env python3
"""Deepen every cached team's (or player's) listing to --days of history.

Why this exists. The football rating, its league-strength term and the tennis
rating are all replayed from the cached `/team/{id}/events/last/{page}`
listings, and SAMPLES only ever asks for the pages it needs - three for most
teams. On 2026-09-30 FK Aktobe's cached history began on 2026-04-27, so the
Kazakh women's league had 8 matches against other leagues in the cache and
its strength was unmeasured (football_rating.MIN_STRENGTH_LINKS = 10): the
fixture was UNLINKED because we had not asked, not because the teams are new.

This asks for the next pages of every entity the cache already lists, oldest
page first missing, until a page reaches back past --days or Sofascore says
there is no next page. Opponents come for free: every team a cached event
names is an entity to deepen (hop 1), so a league's cross-league matches get
their other side's history too.

Order: entities on the most recent boards first, then by how recently the
entity last played - so a run cut short by --max-minutes has filled what the
next sheet reads. Resumable: an entity whose deepest cached page already
reaches --days (or says hasNextPage: false) is never asked again, and a page
that answered 404 is recorded as a listing miss exactly as RESOLVE does.

Same client, same token bucket, same bridge as the pipeline; workers =
SOFA_MAX_CONCURRENCY. It cannot be faster than the pipeline and must not try.
CLAUDE.md: runs are short and resume (first Sofascore refusal on record came
after ~8 min at full width).

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/backfill_listings.py --dry-run
    PYTHONPATH=src:. .venv/bin/python scripts/sofa/backfill_listings.py \\
        --sport football --days 730 --max-minutes 7

Exit: 0 OK, 1 PARTIAL (errors, or the deadline cut it short), 2 FAILED (the
breaker opened).
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
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bet.sofa.cache import SofaCache
from bet.sofa.client import SofascoreClient
from bet.sofa.config import SofaConfig
from bet.sofa.db import get_connection
from bet.sofa.errors import CircuitOpenError, ProviderError

# Sofascore sport slug per --sport.
SPORT_SLUGS = {
    "football": "football",
    "tennis": "tennis",
    "hockey": "ice-hockey",
    "basketball": "basketball",
    "volleyball": "volleyball",
}
# A listing page past this is not asked: 25 pages is ~750 matches.
MAX_PAGE = 25
# The cache is one SQLite file in rollback-journal mode, shared with the daily
# loops and every reader; get_connection waits 30 s for a lock. A write that
# still finds it locked is retried, and a page that cannot be written is
# counted and left for the next run - never allowed to kill the chunk, which
# is what the first run on 2026-09-30 did.
DB_RETRIES = 4
DB_RETRY_SLEEP_S = 5.0


def _with_retry(write: Any) -> bool:
    for attempt in range(DB_RETRIES):
        try:
            write()
            return True
        except sqlite3.OperationalError as exc:
            if "locked" not in str(exc) or attempt == DB_RETRIES - 1:
                return False
            time.sleep(DB_RETRY_SLEEP_S)
    return False


@dataclass
class EntityState:
    """What the cache already holds for one entity's `last` listing."""

    entity_id: int
    deepest_page: int = -1
    oldest_ts: int | None = None  # oldest startTimestamp on the deepest page
    has_next: bool = True
    last_played: int = 0
    on_board: bool = False

    def done(self, since_ts: int) -> bool:
        if self.deepest_page < 0:
            return False
        if not self.has_next or self.deepest_page >= MAX_PAGE:
            return True
        return self.oldest_ts is not None and self.oldest_ts < since_ts


def _event_sport(event: dict[str, Any]) -> str | None:
    tournament = event.get("tournament") or {}
    return ((tournament.get("category") or {}).get("sport") or {}).get("slug")


def board_entities(runs_dir: str, sport: str) -> set[int]:
    """Entity ids on the RESOLVE artifacts of the last seven days."""
    paths = sorted(glob.glob(str(Path(runs_dir) / "*" / "02_fixtures.json")))[-7:]
    out: set[int] = set()
    for path in paths:
        try:
            fixtures = json.loads(Path(path).read_text())
        except (OSError, json.JSONDecodeError):
            continue
        for fx in fixtures:
            if fx.get("sport") == sport:
                for key in ("home_entity_id", "away_entity_id"):
                    if isinstance(fx.get(key), int):
                        out.add(fx[key])
    return out


def scan(
    rows: list[tuple[int, int, str]] | list[tuple[int, int, str, str]],
    slug: str, recent_since: int, seed_before: str | None = None,
) -> dict[int, EntityState]:
    """Entity states from (entity_id, page, events_json[, fetched_at]) rows.

    Every entity a cached event of this sport names that played since
    `recent_since` - the listed entity itself and every opponent. Opponents
    are read only from rows fetched before `seed_before`: the backfill's own
    pages name new opponents, whose pages name more, and without the cut the
    queue grew instead of shrinking (19,866 -> 20,079 on 2026-09-30) - one
    hop from what the pipeline had cached, not the whole world.
    """
    states: dict[int, EntityState] = {}

    def state(eid: int) -> EntityState:
        s = states.get(eid)
        if s is None:
            s = states[eid] = EntityState(eid)
        return s

    for row in rows:
        entity_id, page, events_json = row[0], row[1], row[2]
        seeds_opponents = (
            seed_before is None or len(row) < 4 or str(row[3]) < seed_before)
        try:
            payload = json.loads(events_json)
        except (TypeError, json.JSONDecodeError):
            continue
        events = payload.get("events") if isinstance(payload, dict) else None
        if not isinstance(events, list):
            continue
        sport_events = [e for e in events if _event_sport(e) == slug]
        if not sport_events and events:
            continue
        own = state(entity_id)
        if page > own.deepest_page:
            own.deepest_page = page
            stamps = [e.get("startTimestamp") for e in events
                      if isinstance(e.get("startTimestamp"), int)]
            own.oldest_ts = min(stamps) if stamps else None
            own.has_next = bool(payload.get("hasNextPage", True))
        for event in sport_events:
            if not seeds_opponents:
                continue
            ts = event.get("startTimestamp")
            if not isinstance(ts, int):
                continue
            for side in ("homeTeam", "awayTeam"):
                tid = (event.get(side) or {}).get("id")
                if isinstance(tid, int):
                    s = state(tid)
                    s.last_played = max(s.last_played, ts)
    return {
        eid: s for eid, s in states.items()
        if s.last_played >= recent_since or s.deepest_page >= 0
    }


def plan(
    states: dict[int, EntityState], board: set[int], since_ts: int,
    recent_since: int,
) -> list[EntityState]:
    """Entities still short of `since_ts`, board first, then most recent."""
    todo = []
    for eid, s in states.items():
        s.on_board = eid in board
        if s.last_played < recent_since and not s.on_board:
            continue
        if not s.done(since_ts):
            todo.append(s)
    return sorted(todo, key=lambda s: (not s.on_board, -s.last_played))


class Deepen:
    """One entity at a time, from any number of worker threads."""

    def __init__(self, client: Any, cache: Any, since_ts: int,
                 deadline: float | None) -> None:
        self.client = client
        self.cache = cache
        self.since_ts = since_ts
        self.deadline = deadline
        self.stop = threading.Event()
        self.timed_out = threading.Event()
        self.lock = threading.Lock()
        self.counts = {"entities": 0, "pages": 0, "events": 0, "misses": 0,
                       "errors": 0, "db_locked": 0, "completed": 0}

    def run_one(self, s: EntityState) -> None:
        page = s.deepest_page + 1
        while page <= MAX_PAGE:
            if self.stop.is_set() or self.timed_out.is_set():
                return
            if self.deadline is not None and time.monotonic() >= self.deadline:
                self.timed_out.set()
                return
            try:
                if self.cache.get_listing_miss(s.entity_id, "last", page):
                    break
            except sqlite3.OperationalError:
                with self.lock:
                    self.counts["db_locked"] += 1
                return
            try:
                payload = self.client.entity_events(s.entity_id, "last", page)
            except CircuitOpenError:
                self.stop.set()
                return
            except ProviderError:
                with self.lock:
                    self.counts["errors"] += 1
                return
            if not payload or not isinstance(payload, dict):
                if _with_retry(lambda: self.cache.save_listing_miss(
                        s.entity_id, "last", page)):
                    with self.lock:
                        self.counts["misses"] += 1
                break
            if not _with_retry(lambda: self.cache.save_entity_events(
                    s.entity_id, "last", page, payload)):
                with self.lock:
                    self.counts["db_locked"] += 1
                return
            events = payload.get("events") or []
            stamps = [e.get("startTimestamp") for e in events
                      if isinstance(e.get("startTimestamp"), int)]
            with self.lock:
                self.counts["pages"] += 1
                self.counts["events"] += len(events)
                if self.counts["pages"] % 500 == 0:
                    print(json.dumps({"ts_utc": datetime.now(UTC).isoformat(),
                                      **self.counts}), flush=True)
            if not payload.get("hasNextPage", False) or not stamps or (
                    min(stamps) < self.since_ts):
                break
            page += 1
        with self.lock:
            self.counts["entities"] += 1
            self.counts["completed"] += 1


def _rows(db_path: str) -> list[tuple[int, int, str, str]]:
    with get_connection(db_path) as conn:
        return [
            (int(r["sofascore_entity_id"]), int(r["page"]), r["events_json"],
             str(r["fetched_at"]))
            for r in conn.execute(
                "SELECT sofascore_entity_id, page, events_json, fetched_at "
                "FROM sofa_entity_events WHERE kind = 'last'")
        ]


def seed_cut(path: Path, sport: str, default: str) -> str:
    """The seed time for this sport's backfill: read if recorded, else
    recorded now. Every chunk of one backfill shares it."""
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        cut = doc.get(sport)
        if isinstance(cut, str):
            return cut
    except (OSError, ValueError):
        doc = {}
    doc[sport] = default
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    return default


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--sport", choices=sorted(SPORT_SLUGS), default="football")
    ap.add_argument("--days", type=int, default=730,
                    help="history to reach back to")
    ap.add_argument("--recent-days", type=int, default=400,
                    help="only entities that played inside this window")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--max-minutes", type=float, default=None,
                    help="start no new page after this many minutes")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--seed-file", default="runs/sofa/backfill/listings_seed.json",
                    help="per-sport seed time; opponents come only from pages "
                    "cached before it")
    ap.add_argument("--seed-before", default=None,
                    help="override the recorded seed time (ISO, UTC)")
    args = ap.parse_args()

    config = SofaConfig.from_env()
    if not config.run_id:
        config = dataclasses.replace(
            config, run_id="backfill-listings-"
            + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ"))
    now = int(time.time())
    since, recent = now - args.days * 86400, now - args.recent_days * 86400
    seed = args.seed_before or seed_cut(
        Path(args.seed_file), args.sport, datetime.now(UTC).isoformat())
    states = scan(_rows(config.db_path), SPORT_SLUGS[args.sport], recent, seed)
    board = board_entities(config.runs_dir, args.sport)
    todo = plan(states, board, since, recent)
    if args.limit is not None:
        todo = todo[: args.limit]
    print(json.dumps({
        "run_id": config.run_id, "sport": args.sport, "days": args.days,
        "seed_before": seed,
        "entities_known": len(states), "entities_to_deepen": len(todo),
        "on_board": sum(s.on_board for s in todo),
        "never_listed": sum(s.deepest_page < 0 for s in todo),
    }), flush=True)
    if args.dry_run or not todo:
        return 0
    deadline = time.monotonic() + args.max_minutes * 60 if args.max_minutes else None
    runner = Deepen(SofascoreClient(config), SofaCache(config), since, deadline)
    with ThreadPoolExecutor(max_workers=max(1, config.max_concurrency)) as pool:
        list(pool.map(runner.run_one, todo))
    print(json.dumps({"final": True, "circuit_open": runner.stop.is_set(),
                      "timed_out": runner.timed_out.is_set(),
                      "to_deepen": len(todo), **runner.counts}), flush=True)
    if runner.stop.is_set():
        return 2
    partial = (runner.counts["errors"] or runner.counts["db_locked"]
               or runner.timed_out.is_set())
    return 1 if partial else 0


if __name__ == "__main__":
    sys.exit(main())
