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

Gaps. A page is keyed by its number and page 0 is always the newest, so
when SAMPLES/RESOLVE re-fetch pages 0-2 the deeper pages an older backfill
wrote no longer join up: the matches that slid across the boundary since the
deeper page was fetched are on no cached page (player 65576 on 2026-10-01:
page 2 fetched 09-28 reached back to 2025-10-31, page 3 fetched 09-18 began on
2025-10-03). An entity with such a gap inside the window is not done; it is
re-fetched from the first gapped page on, until the pages join up and reach
--days. See EntityState.first_gap for the test. Since the listed-event
index (src/bet/sofa/listing_index.py, filled once by
scripts/sofa/index_listing_events.py, then by every page save) a disjoint
pair is not re-walked when the index already holds the matches it lost; a
missing page still is. --dry-run reports gaps_covered_by_index.

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
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bet.sofa.cache import SofaCache
from bet.sofa.client import SofascoreClient, breaker_tripped
from bet.sofa.config import SofaConfig
from bet.sofa.errors import CircuitOpenError, ProviderError
from bet.sofa.listing_index import entity_indexed_count, has_index

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
# A match that started this long before a page was fetched may not have been
# on the listing yet (still playing, or listed late), so it still counts as
# having shifted the listing after that fetch. Erring wide costs a re-fetch;
# erring narrow leaves a silent gap. 6 h covers a finished football match and
# nearly every tennis match. Measured on the 2026-10-01 cache (football, 730
# days): gapped entities 874 at 0 h, 930 at 3 h, 940 at 6 h, 976 at 24 h - the
# gaps are not an artefact of the margin.
SHIFT_MARGIN_S = 6 * 3600


def _iso_ts(value: str) -> int | None:
    try:
        stamp = datetime.fromisoformat(value)
    except ValueError:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=UTC)
    return int(stamp.timestamp())


@dataclass(frozen=True)
class PageInfo:
    """One cached page: its newest and oldest startTimestamp, when fetched."""

    newest: int | None
    oldest: int | None
    fetched: int | None


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
    pages: dict[int, PageInfo] = dataclasses.field(default_factory=dict)
    # startTimestamps on this entity's own pages that are recent enough to
    # have shifted the listing after some cached page was fetched.
    recent_stamps: list[int] = dataclasses.field(default_factory=list)
    # (entity_id, after_ts, before_ts) -> how many of the entity's events the
    # listed-event index holds strictly between the two; None = no index.
    indexed: Callable[[int, int, int], int] | None = dataclasses.field(
        default=None, compare=False, repr=False)

    def _covered_by_index(self, newest: int, oldest: int, lo: int,
                          hi: int) -> bool:
        """A gap between two cached pages loses the m matches the entity
        played between their fetches, and those m sit strictly between the
        deeper page's newest start and the shallower page's oldest. The gap
        costs nothing when the index already holds at least m events there.
        m is counted with SHIFT_MARGIN_S, so it errs high (a re-walk), never
        low - except two matches sharing one start second, counted once."""
        if self.indexed is None:
            return False
        shifted = len({ts for ts in self.recent_stamps if lo < ts <= hi})
        return self.indexed(self.entity_id, newest, oldest) >= shifted

    def first_gap(self, since_ts: int, use_index: bool = True) -> int | None:
        """The first page whose cached copy does not join up with the page
        before it, inside the window; None when the cache is contiguous.

        Page k joins page k-1 when it overlaps it in time (page k's newest
        start >= page k-1's oldest). Disjoint pages are contiguous only if
        the listing did not move between their fetches: a page k fetched no
        earlier than page k-1 cannot have lost a match (the listing only
        grows at the front, which pushes matches *into* page k), while a page
        k fetched earlier lost one match per match the entity played after
        that fetch - and those are on the newer pages, so they are counted.
        A missing page inside the window is a gap. Pages past the one that
        already reaches `since_ts` are not judged: they are outside --days.

        Since the listed-event index (listing_index.py) a disjoint pair whose
        lost matches the index holds is not a gap (`use_index=False` judges
        the pages alone). A missing page always is: nothing says how many
        matches it held.
        """
        if self.deepest_page < 0 or not self.pages:
            return None
        for k in range(self.deepest_page + 1):
            cur = self.pages.get(k)
            if cur is None:
                return k
            if k == 0:
                continue
            prev = self.pages[k - 1]
            if prev.oldest is not None and prev.oldest < since_ts:
                return None
            if cur.newest is None or prev.oldest is None:
                continue
            if cur.newest >= prev.oldest:
                continue
            if cur.fetched is None or prev.fetched is None:
                continue
            if cur.fetched >= prev.fetched:
                continue
            lo, hi = cur.fetched - SHIFT_MARGIN_S, prev.fetched
            if any(lo < ts <= hi for ts in self.recent_stamps):
                if use_index and self._covered_by_index(
                        cur.newest, prev.oldest, lo, hi):
                    continue
                return k
        return None

    def start_page(self, since_ts: int) -> int:
        gap = self.first_gap(since_ts)
        return self.deepest_page + 1 if gap is None else gap

    def done(self, since_ts: int) -> bool:
        if self.deepest_page < 0:
            return False
        if self.first_gap(since_ts) is not None:
            return False
        if not self.has_next or self.deepest_page >= MAX_PAGE:
            return True
        return self.oldest_ts is not None and self.oldest_ts < since_ts


def _event_sport(event: dict[str, Any]) -> str | None:
    tournament = event.get("tournament") or {}
    return ((tournament.get("category") or {}).get("sport") or {}).get("slug")


def board_entities(runs_dir: str, sport: str, boards: int = 7) -> set[int]:
    """Entity ids on the RESOLVE artifacts of the last `boards` days."""
    if boards <= 0:
        return set()
    paths = sorted(
        glob.glob(str(Path(runs_dir) / "*" / "02_fixtures.json")))[-boards:]
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
    # Only matches after the oldest fetch can have shifted a listing, so only
    # those stamps are kept per entity (a few, not the whole history).
    fetch_times = [_iso_ts(str(r[3])) for r in rows if len(r) >= 4]
    known = [t for t in fetch_times if t is not None]
    shift_floor = (min(known) - SHIFT_MARGIN_S) if known else None

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
        stamps = [e["startTimestamp"] for e in events
                  if isinstance(e.get("startTimestamp"), int)]
        own.pages[page] = PageInfo(
            max(stamps) if stamps else None, min(stamps) if stamps else None,
            _iso_ts(str(row[3])) if len(row) >= 4 else None)
        if shift_floor is not None:
            own.recent_stamps.extend(t for t in stamps if t >= shift_floor)
        if page > own.deepest_page:
            own.deepest_page = page
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
        page = s.start_page(self.since_ts)
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
                if breaker_tripped(self.client):
                    self.stop.set()  # the failure that opened it
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


def read_only_connection(db_path: str) -> sqlite3.Connection:
    """The planning reads open the cache read-only: a --dry-run beside a live
    pipeline run must not be able to write, migrate or lock it."""
    uri = Path(db_path).resolve().as_uri() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=30.0)
    conn.row_factory = sqlite3.Row
    return conn


class IndexCounter:
    """EntityState.indexed over a read-only connection, shared by the worker
    threads (start_page is asked again inside Deepen.run_one)."""

    def __init__(self, db_path: str) -> None:
        uri = Path(db_path).resolve().as_uri() + "?mode=ro"
        self.conn = sqlite3.connect(uri, uri=True, timeout=30.0,
                                    check_same_thread=False)
        self.lock = threading.Lock()
        self.memo: dict[tuple[int, int, int], int] = {}
        self.available = has_index(self.conn)

    def __call__(self, entity_id: int, after_ts: int, before_ts: int) -> int:
        key = (entity_id, after_ts, before_ts)
        with self.lock:
            if key not in self.memo:
                self.memo[key] = entity_indexed_count(
                    self.conn, entity_id, "last", after_ts, before_ts)
            return self.memo[key]

    def close(self) -> None:
        self.conn.close()


def _rows(db_path: str) -> list[tuple[int, int, str, str]]:
    conn = read_only_connection(db_path)
    try:
        return [
            (int(r["sofascore_entity_id"]), int(r["page"]), r["events_json"],
             str(r["fetched_at"]))
            for r in conn.execute(
                "SELECT sofascore_entity_id, page, events_json, fetched_at "
                "FROM sofa_entity_events WHERE kind = 'last'")
        ]
    finally:
        conn.close()


def seed_cut(path: Path, sport: str, default: str, record: bool = True) -> str:
    """The seed time for this sport's backfill: read if recorded, else
    recorded now (unless `record` is False - a dry run writes nothing).
    Every chunk of one backfill shares it."""
    doc: dict[str, Any] = {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            doc = loaded
        cut = doc.get(sport)
        if isinstance(cut, str):
            return cut
    except (OSError, ValueError):
        doc = {}
    if not record:
        return default
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
        Path(args.seed_file), args.sport, datetime.now(UTC).isoformat(),
        record=not args.dry_run)
    states = scan(_rows(config.db_path), SPORT_SLUGS[args.sport], recent, seed)
    counter = IndexCounter(config.db_path)
    if counter.available:
        for s in states.values():
            s.indexed = counter
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
        "gapped": sum(s.first_gap(since) is not None for s in todo),
        "gapped_on_board": sum(
            s.on_board and s.first_gap(since) is not None for s in todo),
        # Gapped by the pages alone, but the index holds what the gap lost.
        "gaps_covered_by_index": sum(
            s.first_gap(since, use_index=False) is not None
            and s.first_gap(since) is None for s in states.values()),
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
