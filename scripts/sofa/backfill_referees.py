"""Label finished football matches with their referee (bet.sofa.referees).

A snowball over two Sofascore routes, through the same client, token bucket,
breaker and bridge as the pipeline (workers = SOFA_MAX_CONCURRENCY):

  1. seed: every referee sofa_event_detail already names (RESOLVE /
     FIXTURE_CHECK cached /event payloads) becomes a label (source
     ``detail``) and a referee to page;
  2. page every known referee's /referee/{id}/events/last/{p} back to
     --days (each page labels up to 30 events, source ``referee_page``;
     progress in sofa_referee_page, a page read is never asked again);
  3. when no referee is left to page: ask /event/{id} for the football
     matches with statistics in the window that no label covers yet
     (competitions that have been on a board first, then newest first;
     the payload is also cached as sofa_event_detail, as RESOLVE caches it);
     a new referee goes back to 2. A competition whose first
     MAX_BARREN_MISSES /event asks named a referee less than MIN_HIT_RATE
     of the time is skipped (persistent: read from the labels); competitions
     are probed round robin.

Resumable and run in short chunks; never faster than the pipeline:

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/backfill_referees.py --dry-run
    PYTHONPATH=src:. .venv/bin/python scripts/sofa/backfill_referees.py \\
        --days 840 --max-minutes 20

Exit: 0 OK, 1 PARTIAL (requests failed), 2 FAILED (the breaker opened - a
refusal: slow down, pause 10+ minutes, never retry at once).
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
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO / "src"), str(_REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import referees as rf  # noqa: E402
from bet.sofa.cache import SofaCache  # noqa: E402
from bet.sofa.client import SofascoreClient, breaker_tripped  # noqa: E402
from bet.sofa.config import SofaConfig  # noqa: E402
from bet.sofa.errors import CircuitOpenError, ProviderError  # noqa: E402
from bet.sofa.samples import FRIENDLY_COMPETITION_IDS  # noqa: E402
from scripts.sofa.backfill_event_stats import (  # noqa: E402
    MAX_BARREN_MISSES,
    board_competitions,
)
from scripts.sofa.backfill_listings import read_only_connection  # noqa: E402

REFEREE_URL = "https://api.sofascore.com/api/v1/referee/{rid}/events/last/{page}"
DISCOVER_BATCH = 300
# A match younger than this is not asked by discovery: its payload may still
# change; RESOLVE / FIXTURE_CHECK ask the fresh ones.
MIN_AGE_H = 6.0


def seed_from_details(db_path: str) -> tuple[list[rf.EventReferee], list[rf.Referee]]:
    """Labels and referees of the cached /event payloads that name one."""
    conn = read_only_connection(db_path)
    labels: list[rf.EventReferee] = []
    refs: dict[int, rf.Referee] = {}
    try:
        for eid, raw in conn.execute(
                "SELECT sofascore_event_id, detail_json FROM sofa_event_detail "
                "WHERE json_extract(detail_json, '$.event.referee.id') IS NOT NULL"):
            label, ref = rf.from_event_detail(int(eid), json.loads(raw), "detail")
            labels.append(label)
            if ref is not None:
                refs[ref.referee_id] = ref
    finally:
        conn.close()
    return labels, list(refs.values())


def referee_state(db_path: str) -> tuple[dict[int, list[tuple[int, int | None, bool]]],
                                          dict[int, str | None]]:
    """(referee -> pages read, referee -> name) of every known referee."""
    conn = read_only_connection(db_path)
    pages: dict[int, list[tuple[int, int | None, bool]]] = {}
    names: dict[int, str | None] = {}
    try:
        for rid, name in conn.execute(
                "SELECT referee_id, MAX(referee_name) FROM sofa_event_referee "
                "WHERE referee_id IS NOT NULL GROUP BY referee_id"):
            pages.setdefault(int(rid), [])
            names[int(rid)] = name
        for rid, name in conn.execute("SELECT referee_id, name FROM sofa_referee"):
            pages.setdefault(int(rid), [])
            names[int(rid)] = name or names.get(int(rid))
        for rid, page, oldest, has_next in conn.execute(
                "SELECT referee_id, page, oldest_ts, has_next FROM sofa_referee_page"):
            pages.setdefault(int(rid), []).append(
                (int(page), oldest, bool(has_next)))
    finally:
        conn.close()
    return pages, names


def pending_referees(pages: dict[int, list[tuple[int, int | None, bool]]],
                     cutoff_ts: int) -> list[tuple[int, int]]:
    """(referee, next page) of every referee not paged back to the cutoff."""
    out = []
    for rid, read in pages.items():
        nxt = rf.next_page(read, cutoff_ts)
        if nxt is not None:
            out.append((rid, nxt))
    return sorted(out)


def eligible_events(db_path: str, since_ts: int, until_ts: int) -> list[dict[str, Any]]:
    """{id, ts, competition} of football matches with a statistics or
    incidents row in [since_ts, until_ts], from the listing index."""
    conn = read_only_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT l.event_id, l.start_ts, "
            "json_extract(l.event_json, '$.tournament.uniqueTournament.id') "
            "FROM sofa_listed_event l JOIN sofa_event_stats s "
            "ON s.sofascore_event_id = l.event_id "
            "WHERE l.sport = 'football' AND l.start_ts BETWEEN ? AND ? "
            "AND ((s.statistics_json IS NOT NULL AND length(s.statistics_json) > 2) "
            "OR (s.incidents_json IS NOT NULL AND length(s.incidents_json) > 2))",
            (since_ts, until_ts)).fetchall()
    finally:
        conn.close()
    return [{"id": int(e), "ts": int(t), "competition": c} for e, t, c in rows]


def labelled_state(db_path: str) -> tuple[set[int], dict[int | None, list[int]]]:
    """(labelled event ids, competition -> [hits, misses] of /event
    payloads: a hit names a referee - ours or RESOLVE's cached one - a miss
    is our ask that named nobody)."""
    conn = read_only_connection(db_path)
    done: set[int] = set()
    comp: dict[int | None, list[int]] = {}
    try:
        for eid, rid, ut, source in conn.execute(
                "SELECT event_id, referee_id, unique_tournament_id, source "
                "FROM sofa_event_referee"):
            done.add(int(eid))
            # a hit: any /event payload (ours or RESOLVE's) naming a referee;
            # a miss: our /event ask that named nobody
            if source in ("event", "detail") and (rid is not None
                                                  or source == "event"):
                cell = comp.setdefault(ut, [0, 0])
                cell[0 if rid is not None else 1] += 1
    finally:
        conn.close()
    return done, comp


# A competition whose /event asks name a referee less often than this, once
# MAX_BARREN_MISSES have been asked, is skipped (Sofascore keeps no referee
# for most lower leagues: 18 of the first 2,520 asks named one, 2026-10-20).
MIN_HIT_RATE = 0.05


def barren(comp_counts: dict[int | None, list[int]]) -> set[int | None]:
    out: set[int | None] = set()
    for c, (hits, misses) in comp_counts.items():
        asks = hits + misses
        if asks >= MAX_BARREN_MISSES and hits < MIN_HIT_RATE * asks:
            out.add(c)
    return out


def discovery_targets(
    events: Iterable[dict[str, Any]], done: set[int],
    skip: set[int | None], board: set[int],
) -> list[dict[str, Any]]:
    """Unlabelled, non-friendly, not barren; round robin over competitions
    (every competition is probed early), board competitions first, newest
    first inside a competition."""
    per: dict[Any, list[dict[str, Any]]] = {}
    for e in events:
        if (e["id"] in done or e.get("competition") in FRIENDLY_COMPETITION_IDS
                or e.get("competition") in skip):
            continue
        per.setdefault(e.get("competition"), []).append(e)
    ranked: list[tuple[bool, int, int, dict[str, Any]]] = []
    for comp, evs in per.items():
        evs.sort(key=lambda e: -e["ts"])
        ranked.extend((comp not in board, i, -e["ts"], e) for i, e in enumerate(evs))
    ranked.sort(key=lambda t: t[:3])
    return [t[3] for t in ranked]


class Runner:
    def __init__(self, get: Callable[[str], Any], event: Callable[[int], Any],
                 store: rf.RefereeStore, cache: Any, client: Any,
                 cutoff_ts: int, deadline: float | None) -> None:
        self.get, self.event = get, event
        self.store, self.cache, self.client = store, cache, client
        self.cutoff_ts, self.deadline = cutoff_ts, deadline
        self.stop = threading.Event()
        self.timed_out = threading.Event()
        self.lock = threading.Lock()
        self.counts = {"pages": 0, "page_labels": 0, "referees_done": 0,
                       "events_asked": 0, "events_with_referee": 0,
                       "new_referees": 0, "errors": 0}
        self.found: set[int] = set()

    def _halt(self) -> bool:
        if self.stop.is_set() or self.timed_out.is_set():
            return True
        if self.deadline is not None and time.monotonic() >= self.deadline:
            self.timed_out.set()
            return True
        return False

    def _call(self, fn: Callable[[], Any]) -> tuple[bool, Any]:
        try:
            return True, fn()
        except CircuitOpenError:
            self.stop.set()
        except ProviderError:
            with self.lock:
                self.counts["errors"] += 1
            if breaker_tripped(self.client):
                self.stop.set()
        return False, None

    def page_referee(self, item: tuple[int, int, str | None]) -> None:
        rid, page, name = item
        while not self._halt():
            ok, payload = self._call(
                lambda: self.get(REFEREE_URL.format(rid=rid, page=page)))
            if not ok:
                return
            labels, oldest, has_next = rf.from_referee_page(rid, payload, name)
            self.store.save_labels(labels)
            self.store.save_page(rid, page, len(labels), oldest, has_next)
            with self.lock:
                self.counts["pages"] += 1
                self.counts["page_labels"] += len(labels)
                self._progress()
            if rf.next_page([(page, oldest, has_next)], self.cutoff_ts) is None:
                with self.lock:
                    self.counts["referees_done"] += 1
                return
            page += 1

    def discover(self, target: dict[str, Any]) -> None:
        if self._halt():
            return
        eid = int(target["id"])
        ok, detail = self._call(lambda: self.event(eid))
        if not ok:
            return
        if detail:
            status = ((detail.get("event") or {}).get("status") or {}).get("type")
            self.cache.save_event_detail(eid, detail, status)
        label, ref = rf.from_event_detail(eid, detail, "event")
        if label.unique_tournament_id is None:
            label = dataclasses.replace(
                label, unique_tournament_id=target.get("competition"),
                start_ts=label.start_ts or target.get("ts"), sport="football")
        self.store.save_labels([label])
        if ref is not None:
            self.store.save_referee(ref)
        with self.lock:
            self.counts["events_asked"] += 1
            if ref is not None:
                self.counts["events_with_referee"] += 1
                if ref.referee_id not in self.found:
                    self.found.add(ref.referee_id)
            self._progress()

    def _progress(self) -> None:
        n = self.counts["pages"] + self.counts["events_asked"]
        if n and n % 250 == 0:
            print(json.dumps({"ts_utc": datetime.now(UTC).isoformat(),
                              **self.counts}), flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("--days", type=int, default=840,
                    help="page referees and discover matches this far back")
    ap.add_argument("--max-minutes", type=float, default=None,
                    help="start no new request after this many minutes")
    ap.add_argument("--discover-batch", type=int, default=DISCOVER_BATCH)
    ap.add_argument("--no-discover", action="store_true",
                    help="only page the referees already known")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    config = SofaConfig.from_env()
    if not config.run_id:
        config = dataclasses.replace(
            config, run_id="backfill-referees-"
            + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ"))
    nowts = int(time.time())
    cutoff = nowts - args.days * 86400
    store = rf.RefereeStore(config.db_path)
    labels, refs = seed_from_details(config.db_path)
    if not args.dry_run:
        store.save_labels(labels)
        for ref in refs:
            store.save_referee(ref)
    pages, names = referee_state(config.db_path)
    for ref in refs:
        pages.setdefault(ref.referee_id, [])
        names.setdefault(ref.referee_id, ref.name)
    events = eligible_events(config.db_path, cutoff, nowts - int(MIN_AGE_H * 3600))
    board = board_competitions(config.runs_dir)
    done, comp_counts = labelled_state(config.db_path)
    done |= {lb.event_id for lb in labels}
    print(json.dumps({
        "run_id": config.run_id, "days": args.days,
        "seed_labels": len(labels), "known_referees": len(pages),
        "referees_to_page": len(pending_referees(pages, cutoff)),
        "eligible_events": len(events),
        "labelled_eligible": sum(e["id"] in done for e in events),
        "board_competitions": len(board),
        "discovery_targets": len(discovery_targets(
            events, done, barren(comp_counts), board)),
    }), flush=True)
    if args.dry_run:
        return 0

    client = SofascoreClient(config)
    cache = SofaCache(config)
    deadline = time.monotonic() + args.max_minutes * 60 if args.max_minutes else None
    runner = Runner(client._execute, client.event, store, cache, client,
                    cutoff, deadline)
    workers = max(1, config.max_concurrency)
    rounds = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        while not runner.stop.is_set() and not runner.timed_out.is_set():
            rounds += 1
            pages, names = referee_state(config.db_path)
            todo = pending_referees(pages, cutoff)
            if todo:
                list(pool.map(runner.page_referee,
                              [(rid, p, names.get(rid)) for rid, p in todo]))
                continue
            if args.no_discover:
                break
            done, comp_counts = labelled_state(config.db_path)
            targets = discovery_targets(events, done, barren(comp_counts), board)
            if not targets:
                break
            before = len(runner.found)
            batch = targets[: args.discover_batch]
            list(pool.map(runner.discover, batch))
            print(json.dumps({"round": rounds, "discovered": len(batch),
                              "new_referees_in_round": len(runner.found) - before,
                              **runner.counts}), flush=True)
    runner.counts["new_referees"] = len(runner.found)
    print(json.dumps({"final": True, "rounds": rounds,
                      "circuit_open": runner.stop.is_set(),
                      "timed_out": runner.timed_out.is_set(), **runner.counts}),
          flush=True)
    return 2 if runner.stop.is_set() else (1 if runner.counts["errors"] else 0)


if __name__ == "__main__":
    sys.exit(main())
