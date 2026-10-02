#!/usr/bin/env python3
"""Fill the listed-event index from the listing pages already cached. One-time.

Every page save indexes its events since listing_index.py shipped; this
walks the `last` pages saved before that (and any a process still running old
code saves meanwhile) and upserts their events into sofa_listed_event /
sofa_listing_event, the newest fetch winning. No network, no bridge.

Live-safe by construction. The file is 22 GB in WAL mode, shared with the
daily loops and the backfills:

- pages are read in rowid order, --batch at a time, on a read-only
  connection, so every read is one short statement and holds nothing;
- each batch is written in one short transaction on its own connection,
  together with the cursor (sofa_listing_index_progress), so a run cut off
  anywhere - --max-minutes, Ctrl-C, a crash - resumes exactly where its last
  commit left it, and a re-run over indexed pages changes nothing
  (newer-fetch-wins upserts);
- a page saved again later gets a new, higher rowid (INSERT OR REPLACE), so a
  later run picks up whatever changed meanwhile. Run it until it reports
  `remaining_unindexed: 0` - pages after the cursor that a new-code writer
  (SofaCache.save_entity_events) saved have indexed themselves and do not
  count (`remaining_pages` is the raw count after the cursor).

Pacing (2026-10-02 review, F3). Other writers wait on SQLite's busy handler
(sleeps up to 100 ms, and RetryingConnection retries only COMMIT), so a write
transaction must stay short and the gap between two of them long enough for
a waiting writer to get in: --batch 10 pages (~230 upserts, ~1.4 MB of
payload) per transaction and --pause-ms 300 after each. Every
--checkpoint-every batches a PASSIVE checkpoint is run (it never blocks a
reader or a writer) and the WAL's live size is reported; when it stays above
--max-wal-mb (a long reader - SHEET parsing the history - pins it) the fill
waits for it to drain and, if it does not, stops cleanly with exit 1
(`stopped: wal_over_limit`) and resumes on the next run.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/index_listing_events.py --dry-run
    PYTHONPATH=src:. .venv/bin/python scripts/sofa/index_listing_events.py \\
        --max-minutes 10 --batch 10 --pause-ms 300 --checkpoint-every 20 \\
        --max-wal-mb 256

--dry-run opens the file read-only and writes nothing: it reads every page
still to index and counts pages, events, distinct events and the payload
bytes the index will add.

Exit: 0 done (no unindexed page left), 1 PARTIAL (the deadline or the WAL
guard cut it short), 2 FAILED.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bet.sofa.config import SofaConfig
from bet.sofa.db import get_connection, migrate
from bet.sofa.listing_index import (
    FILL_PROGRESS,
    LISTED_EVENT,
    LISTING_EVENT,
    has_index,
    index_page,
)

PROGRESS_NAME = "last_pages"
# Pages (~136 kB, ~23 events each) per read and per write transaction: ~230
# upserts, short enough that a writer waiting on the busy handler is not
# starved (50 pages was ~1,150 upserts and ~12 MB of WAL a transaction).
DEFAULT_BATCH = 10
# Between write transactions: several busy-handler sleeps (<= 100 ms each) of
# room for the other writers.
DEFAULT_PAUSE_MS = 300
MIN_PAUSE_MS = 300
# A PASSIVE checkpoint every this many batches.
DEFAULT_CHECKPOINT_EVERY = 20
# The live WAL above which the fill waits, then stops (MB).
DEFAULT_MAX_WAL_MB = 256.0
# How long the WAL guard waits for a pinned WAL to drain before it stops.
WAL_WAIT_S = 60.0
WAL_POLL_S = 5.0
# remaining_unindexed is counted exactly up to this many raw remaining pages;
# above it (a run cut short early) it is not counted and reads as remaining.
REMAINING_CHECK_LIMIT = 20_000


def read_only(db_path: str) -> sqlite3.Connection:
    uri = Path(db_path).resolve().as_uri() + "?mode=ro"
    return sqlite3.connect(uri, uri=True, timeout=30.0)


def read_cursor(conn: sqlite3.Connection) -> int:
    found = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (FILL_PROGRESS,)).fetchone()
    if found is None:
        return 0
    row = conn.execute(
        f"SELECT last_rowid FROM {FILL_PROGRESS} WHERE name = ?",
        (PROGRESS_NAME,)).fetchone()
    return int(row[0]) if row else 0


def remaining_pages(conn: sqlite3.Connection, cursor: int) -> int:
    row = conn.execute(
        "SELECT COUNT(*) FROM sofa_entity_events WHERE rowid > ? AND kind = 'last'",
        (cursor,)).fetchone()
    return int(row[0])


def remaining_unindexed(
    conn: sqlite3.Connection, cursor: int, limit: int = REMAINING_CHECK_LIMIT
) -> int | None:
    """`last` pages after the cursor whose events are not yet in the index.

    A page a new-code writer saved indexed itself in the same transaction:
    every event's membership row carries the page's own fetched_at (or a
    later one). A page with no readable event has nothing to index. Pages an
    old-code process saved have no such row and are counted. None when more
    than `limit` pages remain - too many to check; they count as remaining.
    """
    if remaining_pages(conn, cursor) > limit:
        return None
    if not has_index(conn):
        return remaining_pages(conn, cursor)
    unindexed = 0
    for entity_id, fetched_at, events_json in conn.execute(
        "SELECT sofascore_entity_id, fetched_at, events_json "
        "FROM sofa_entity_events WHERE rowid > ? AND kind = 'last'",
        (cursor,),
    ):
        payload = _payload(events_json)
        listed = payload.get("events") if isinstance(payload, dict) else None
        ids = sorted({e["id"] for e in listed or []
                      if isinstance(e, dict) and isinstance(e.get("id"), int)})
        if not ids:
            continue
        marks = ",".join("?" * len(ids))
        held = conn.execute(
            f"SELECT COUNT(*) FROM {LISTING_EVENT} WHERE entity_id = ? "
            f"AND kind = 'last' AND fetched_at >= ? AND event_id IN ({marks})",
            (entity_id, fetched_at, *ids)).fetchone()[0]
        if int(held) < len(ids):
            unindexed += 1
    return unindexed


def wal_mb(conn: sqlite3.Connection, db_path: str) -> tuple[float, float, int]:
    """PASSIVE checkpoint; returns (live WAL MB, WAL file MB, busy flag).

    Live = frames the WAL currently holds (it restarts from the top once a
    checkpoint has copied everything and no reader pins it); the file itself
    never shrinks, so it is reported but not what the guard reads."""
    busy, frames, _done = conn.execute("PRAGMA wal_checkpoint(PASSIVE)").fetchone()
    page_size = int(conn.execute("PRAGMA page_size").fetchone()[0])
    live = max(int(frames), 0) * (page_size + 24) / 1e6
    try:
        on_disk = os.path.getsize(db_path + "-wal") / 1e6
    except OSError:
        on_disk = 0.0
    return round(live, 1), round(on_disk, 1), int(busy)


def batches(
    conn: sqlite3.Connection, cursor: int, size: int
) -> Iterator[list[tuple[int, int, str, str]]]:
    """(rowid, entity_id, fetched_at, events_json) of `last` pages after
    `cursor`, `size` at a time; each batch is one short statement."""
    while True:
        rows = [
            (int(r[0]), int(r[1]), str(r[2]), str(r[3]))
            for r in conn.execute(
                "SELECT rowid, sofascore_entity_id, fetched_at, events_json "
                "FROM sofa_entity_events WHERE rowid > ? AND kind = 'last' "
                "ORDER BY rowid LIMIT ?", (cursor, size))
        ]
        if not rows:
            return
        yield rows
        cursor = rows[-1][0]


def _payload(events_json: str) -> Any:
    try:
        return json.loads(events_json)
    except (TypeError, ValueError):
        return None


def dry_run(db_path: str, batch: int) -> dict[str, Any]:
    conn = read_only(db_path)
    started = time.monotonic()
    try:
        cursor = read_cursor(conn)
        indexed = (conn.execute(f"SELECT COUNT(*) FROM {LISTED_EVENT}").fetchone()[0]
                   if has_index(conn) else 0)
        pages = events = unreadable = 0
        page_bytes = new_bytes = 0.0
        distinct: set[int] = set()
        for rows in batches(conn, cursor, batch):
            for _, _, _, events_json in rows:
                pages += 1
                payload = _payload(events_json)
                listed = payload.get("events") if isinstance(payload, dict) else None
                if not isinstance(listed, list):
                    unreadable += 1
                    continue
                ids = [e["id"] for e in listed
                       if isinstance(e, dict) and isinstance(e.get("id"), int)]
                events += len(ids)
                page_bytes += len(events_json)
                fresh = [i for i in ids if i not in distinct]
                distinct.update(fresh)
                if ids:
                    new_bytes += len(events_json) * len(fresh) / len(ids)
    finally:
        conn.close()
    elapsed = time.monotonic() - started
    return {
        "dry_run": True, "cursor_rowid": cursor, "pages_to_index": pages,
        "unreadable_pages": unreadable, "events": events,
        "distinct_events": len(distinct), "already_indexed_events": indexed,
        "page_json_gb": round(page_bytes / 1e9, 2),
        "index_payload_gb_estimate": round(new_bytes / 1e9, 2),
        "read_parse_seconds": round(elapsed, 1),
    }


def fill(
    db_path: str, batch: int, max_minutes: float | None, pause_ms: int,
    progress_every: int = 20,
    checkpoint_every: int = DEFAULT_CHECKPOINT_EVERY,
    max_wal_mb: float | None = DEFAULT_MAX_WAL_MB,
    wal_wait_s: float = WAL_WAIT_S,
    sleep: Any = time.sleep,
) -> dict[str, Any]:
    migrate(db_path)  # the index tables, if this file has not seen them yet
    reader = read_only(db_path)
    writer = get_connection(db_path)
    deadline = (time.monotonic() + max_minutes * 60) if max_minutes else None
    started = time.monotonic()
    counts = {"pages": 0, "events": 0, "unreadable_pages": 0, "batches": 0,
              "checkpoints": 0}
    timed_out = False
    stopped: str | None = None
    wal: dict[str, Any] = {}

    def wal_guard() -> bool:
        """Checkpoint, report; True when the WAL stayed over the limit."""
        waited = 0.0
        while True:
            live, on_disk, busy = wal_mb(writer, db_path)
            counts["checkpoints"] += 1
            wal.update(wal_live_mb=live, wal_file_mb=on_disk,
                       checkpoint_busy=busy)
            if max_wal_mb is None or live <= max_wal_mb:
                return False
            if waited >= wal_wait_s:
                return True
            sleep(WAL_POLL_S)
            waited += WAL_POLL_S

    try:
        cursor = read_cursor(reader)
        for rows in batches(reader, cursor, batch):
            for _, entity_id, fetched_at, events_json in rows:
                payload = _payload(events_json)
                if not isinstance(payload, dict):
                    counts["unreadable_pages"] += 1
                    continue
                counts["events"] += index_page(
                    writer, entity_id, "last", fetched_at, payload)
                counts["pages"] += 1
            cursor = rows[-1][0]
            writer.execute(
                f"INSERT INTO {FILL_PROGRESS} (name, last_rowid, updated_at) "
                "VALUES (?, ?, ?) ON CONFLICT(name) DO UPDATE SET "
                "last_rowid = excluded.last_rowid, updated_at = excluded.updated_at",
                (PROGRESS_NAME, cursor, datetime.now(UTC).isoformat()))
            writer.commit()
            counts["batches"] += 1
            if checkpoint_every and counts["batches"] % checkpoint_every == 0:
                if wal_guard():
                    stopped = "wal_over_limit"
            if counts["batches"] % progress_every == 0 or stopped:
                print(json.dumps({"ts_utc": datetime.now(UTC).isoformat(),
                                  "cursor_rowid": cursor, **counts, **wal}),
                      flush=True)
            if stopped:
                break
            if deadline is not None and time.monotonic() >= deadline:
                timed_out = True
                break
            if pause_ms:
                sleep(pause_ms / 1000.0)
        if stopped is None:
            wal_guard()  # the final size, and one checkpoint for the road
        left = remaining_pages(reader, cursor)
        unindexed = remaining_unindexed(reader, cursor)
    finally:
        writer.close()
        reader.close()
    return {"final": True, "cursor_rowid": cursor, "timed_out": timed_out,
            "stopped": stopped, "remaining_pages": left,
            "remaining_unindexed": unindexed,
            "seconds": round(time.monotonic() - started, 1), **counts, **wal}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", default=None, help="default: SOFA_DB_PATH / config")
    ap.add_argument("--batch", type=int, default=DEFAULT_BATCH)
    ap.add_argument("--max-minutes", type=float, default=None,
                    help="start no new batch after this many minutes")
    ap.add_argument("--pause-ms", type=int, default=DEFAULT_PAUSE_MS,
                    help=f"between write transactions (>= {MIN_PAUSE_MS})")
    ap.add_argument("--checkpoint-every", type=int,
                    default=DEFAULT_CHECKPOINT_EVERY,
                    help="PASSIVE checkpoint + WAL report every N batches")
    ap.add_argument("--max-wal-mb", type=float, default=DEFAULT_MAX_WAL_MB,
                    help="live WAL above which the fill waits, then stops")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if args.pause_ms < MIN_PAUSE_MS:
        ap.error(f"--pause-ms below {MIN_PAUSE_MS} starves the other writers")
    if args.batch < 1 or args.checkpoint_every < 1 or args.max_wal_mb <= 0:
        ap.error("--batch, --checkpoint-every and --max-wal-mb must be positive")
    db_path = args.db or SofaConfig.from_env().db_path
    if not Path(db_path).exists():
        print(json.dumps({"error": f"no database at {db_path}"}), flush=True)
        return 2
    if args.dry_run:
        print(json.dumps(dry_run(db_path, args.batch)), flush=True)
        return 0
    try:
        result = fill(db_path, args.batch, args.max_minutes, args.pause_ms,
                      checkpoint_every=args.checkpoint_every,
                      max_wal_mb=args.max_wal_mb)
    except (sqlite3.Error, OSError) as exc:
        # Whatever committed stays committed; the next run resumes from it.
        print(json.dumps({"failed": f"{type(exc).__name__}: {exc}"}), flush=True)
        return 2
    print(json.dumps(result), flush=True)
    done = result["stopped"] is None and result["remaining_unindexed"] == 0
    return 0 if done else 1


if __name__ == "__main__":
    sys.exit(main())
