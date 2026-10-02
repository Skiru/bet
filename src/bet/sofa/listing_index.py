"""Listed events by event id, beside the page-keyed listing cache.

Why. `sofa_entity_events` is keyed by (entity, kind, page) and page 0 is
always the newest, so whenever SAMPLES/RESOLVE re-fetch pages 0-2 the matches
that slid from the old page 2 into page 3's range are on no stored page: an
INSERT OR REPLACE of page 2 drops them and the older page 3 never had them.
backfill_listings re-walked such chains (EntityState.first_gap) - 962 football
and 550 tennis entities on 2026-10-01/02 - and the loss recurred every day.

What. Every event of every `last` page that is saved is also kept here, keyed
by event id, so a finished match seen on any page once is never lost again:

- `sofa_listed_event`: one payload per event id (the newest fetch wins - a
  status that moved from notstarted to finished, a corrected score), its sport
  slug and start time. One row per *match*, not per side: a match is on both
  sides' listings, and storing it per side would double ~8 GB of JSON.
- `sofa_listing_event`: which entity's listing showed which event, and when;
  what a per-entity reader (SAMPLES) needs.

Only `last` pages are indexed: they are the history. `next` pages are the
upcoming fixtures RESOLVE re-reads live, and a match that finishes moves to
`last`. The schema keeps `kind` so that can change without a migration.

Readers take the union of the pages and the index, deduplicated by event id,
and are byte-identical to the page-only read while the index is empty - so
this is safe before the one-time fill (scripts/sofa/index_listing_events.py).

Who reads the union (2026-10-02 review, F1): backfill_listings no longer
re-walks a page gap the index already covers, so a reader of the pages alone
loses those matches for good. Every reader that feeds a fit, a regrade or a
class therefore reads `listed_events_by_id` (or `iter_indexed_events`):
football_rating / tennis_rating / score_model load_history, SAMPLES,
calibrate_from_cache, backfill_event_stats, fit_confidence.load_event_classes,
regrade_settled.listing_events / match_tiebreak_events,
refetch_provisional_stats.kickoffs, find_women_competitions,
fit_tennis_tier_baselines, fit_no_stats_tournaments.

Still page-only, on purpose - measurements and audits whose numbers are
compared with earlier runs of themselves and decide nothing on their own:
measure_empirical_tennis_counts, measure_per_set_nb, measure_score_history,
measure_score_model, measure_set_games_distribution, measure_side_correlations,
measure_tennis_serve_model, price_tennis_serve_model, audit_stat_completeness
(audit_sample_bias reads the day's artifacts, not the listings). Moving one of
them to the union moves its numbers; say so in its report when you do.

The rating histories (football_rating, tennis_rating, score_model) take every
indexed id, including one Sofascore has since removed from every listing (F4:
the index never forgets). A match Sofascore re-listed under a new id and
removed the old one from is then in a history twice; one_listing_per_match
is not applied there. Suspected rare (the 09-27 duplicate listings were both
still listed), not measured. SAMPLES does not have this problem: it adds an
indexed event only in a gap between the pages it read, never inside a
page's own time span.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Collection, Iterator, Mapping, Set
from typing import Any, cast

LISTED_EVENT = "sofa_listed_event"
LISTING_EVENT = "sofa_listing_event"
FILL_PROGRESS = "sofa_listing_index_progress"
INDEXED_KINDS = frozenset({"last"})
# Event ids per `IN (...)` when payloads are fetched by id (SQLite's default
# variable limit is 32766; small chunks keep each read short).
_FETCH_CHUNK = 500

SCHEMA = [
    # event_json last: a scan of the small columns never reads the payload's
    # overflow pages.
    f"""
    CREATE TABLE IF NOT EXISTS {LISTED_EVENT} (
        event_id    INTEGER PRIMARY KEY,
        sport       TEXT,
        start_ts    INTEGER,
        fetched_at  TEXT    NOT NULL,
        event_json  TEXT    NOT NULL
    );
    """,
    # Covers the history readers' (event_id, fetched_at) scan of one sport and
    # makes the fingerprint's MAX(fetched_at) a seek.
    f"CREATE INDEX IF NOT EXISTS {LISTED_EVENT}_sport "
    f"ON {LISTED_EVENT} (sport, fetched_at, event_id);",
    f"""
    CREATE TABLE IF NOT EXISTS {LISTING_EVENT} (
        entity_id   INTEGER NOT NULL,
        kind        TEXT    NOT NULL,
        event_id    INTEGER NOT NULL,
        start_ts    INTEGER,
        fetched_at  TEXT    NOT NULL,
        PRIMARY KEY (entity_id, kind, event_id)
    );
    """,
    f"CREATE INDEX IF NOT EXISTS {LISTING_EVENT}_entity_ts "
    f"ON {LISTING_EVENT} (entity_id, kind, start_ts);",
    # Where the one-time fill (scripts/sofa/index_listing_events.py) stopped:
    # the last sofa_entity_events rowid it indexed. A page saved again gets a
    # new, higher rowid, so a later run picks up what changed meanwhile.
    f"""
    CREATE TABLE IF NOT EXISTS {FILL_PROGRESS} (
        name        TEXT    PRIMARY KEY,
        last_rowid  INTEGER NOT NULL,
        updated_at  TEXT    NOT NULL
    );
    """,
]

# The newer fetch wins. fetched_at is always SofaCache's now().isoformat() (UTC,
# +00:00), so text order is time order. An equal stamp is the same page save
# again (the one-time fill walking a page a new-code writer already indexed):
# nothing is rewritten, so the re-walk costs reads and no WAL.
_UPSERT_EVENT = f"""
    INSERT INTO {LISTED_EVENT} (event_id, sport, start_ts, fetched_at, event_json)
    VALUES (?, ?, ?, ?, ?)
    ON CONFLICT(event_id) DO UPDATE SET
        sport = excluded.sport,
        start_ts = excluded.start_ts,
        fetched_at = excluded.fetched_at,
        event_json = excluded.event_json
    WHERE excluded.fetched_at > {LISTED_EVENT}.fetched_at
"""
_UPSERT_MEMBER = f"""
    INSERT INTO {LISTING_EVENT} (entity_id, kind, event_id, start_ts, fetched_at)
    VALUES (?, ?, ?, ?, ?)
    ON CONFLICT(entity_id, kind, event_id) DO UPDATE SET
        start_ts = excluded.start_ts,
        fetched_at = excluded.fetched_at
    WHERE excluded.fetched_at > {LISTING_EVENT}.fetched_at
"""


def event_sport(event: dict[str, Any]) -> str | None:
    """The sport slug, or None. Never raises: it runs inside the page save's
    transaction, and a payload with a non-dict tournament/category/sport must
    not roll the page write back."""
    node: Any = event
    for key in ("tournament", "category", "sport"):
        node = node.get(key) if isinstance(node, dict) else None
    slug = node.get("slug") if isinstance(node, dict) else None
    return slug if isinstance(slug, str) else None


def _events(payload: Any) -> list[dict[str, Any]]:
    events = payload.get("events") if isinstance(payload, dict) else payload
    if not isinstance(events, list):
        return []
    return [e for e in events if isinstance(e, dict) and isinstance(e.get("id"), int)]


def index_page(
    conn: sqlite3.Connection,
    entity_id: int,
    kind: str,
    fetched_at: str,
    payload: Any,
) -> int:
    """Upsert every event of one listing page; the caller commits.

    Returns the number of events written (0 for a kind that is not indexed).
    """
    if kind not in INDEXED_KINDS:
        return 0
    events = _events(payload)
    if not events:
        return 0
    rows = []
    members = []
    for event in events:
        start = event.get("startTimestamp")
        start_ts = start if isinstance(start, int) else None
        rows.append((event["id"], event_sport(event), start_ts, fetched_at,
                     json.dumps(event)))
        members.append((entity_id, kind, event["id"], start_ts, fetched_at))
    conn.executemany(_UPSERT_EVENT, rows)
    conn.executemany(_UPSERT_MEMBER, members)
    return len(events)


def has_index(conn: sqlite3.Connection) -> bool:
    """True when both index tables exist (a read-only reader of a file no
    migrate() has touched since the index shipped finds neither)."""
    found = {
        row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' "
            "AND name IN (?, ?)", (LISTED_EVENT, LISTING_EVENT))
    }
    return found == {LISTED_EVENT, LISTING_EVENT}


def iter_indexed_events(
    conn: sqlite3.Connection,
    held: Mapping[int, str] | Set[int],
    sport: str | None = None,
    only: Set[int] | None = None,
) -> Iterator[dict[str, Any]]:
    """Indexed payloads a page reader does not already hold, in event-id order.

    `held` is what the pages gave: a mapping event id -> the fetched_at of the
    page row that supplied it (an indexed payload fetched strictly later
    replaces it - the newest payload wins), or a plain set of ids for a reader
    whose tie rule is "first seen" (only ids it lacks are yielded). `only`
    restricts to those ids before any payload is read. Nothing is yielded
    while the index is empty or missing, so a reader is unchanged.
    """
    if not has_index(conn):
        return
    if sport is None:
        cursor = conn.execute(f"SELECT event_id, fetched_at FROM {LISTED_EVENT}")
    else:
        cursor = conn.execute(
            f"SELECT event_id, fetched_at FROM {LISTED_EVENT} WHERE sport = ?",
            (sport,))
    stamps = held if isinstance(held, Mapping) else None
    wanted: list[int] = []
    for event_id, fetched_at in cursor:
        if only is not None and event_id not in only:
            continue
        if event_id not in held:
            wanted.append(int(event_id))
        elif stamps is not None and str(fetched_at) > stamps[event_id]:
            wanted.append(int(event_id))
    wanted.sort()
    for i in range(0, len(wanted), _FETCH_CHUNK):
        chunk = wanted[i:i + _FETCH_CHUNK]
        marks = ",".join("?" * len(chunk))
        for (event_json,) in conn.execute(
            f"SELECT event_json FROM {LISTED_EVENT} WHERE event_id IN ({marks}) "
            "ORDER BY event_id", chunk):
            try:
                event = json.loads(event_json)
            except (TypeError, ValueError):
                continue
            if isinstance(event, dict):
                yield cast(dict[str, Any], event)


def _page_events(events_json: Any) -> list[dict[str, Any]]:
    try:
        payload = json.loads(events_json)
    except (TypeError, ValueError):
        return []
    events = payload.get("events") if isinstance(payload, dict) else payload
    if not isinstance(events, list):
        return []
    return [e for e in events if isinstance(e, dict)]


def listed_events_by_id[T](
    conn: sqlite3.Connection,
    project: Callable[[dict[str, Any]], T | None],
    *,
    kinds: Collection[str] | None = ("last",),
    like: str | None = None,
    sport: str | None = None,
    only: Set[int] | None = None,
) -> dict[int, T]:
    """Every listed event by id - the cached pages and the index - projected.

    `project(event)` is what the reader keeps of one copy, or None for a copy
    it does not accept (a pre-match copy, another class). Pages are read in
    rowid order and the first accepted copy of an id is kept - every reader
    this replaces kept the first copy, so with an empty index the result is
    exactly the page-only one, in the same insertion order. The index then
    adds every id the pages lack and replaces a page copy with its own when
    the index copy was fetched strictly later and is accepted: the newest
    payload wins.

    `kinds` - the page kinds read (None = every kind, as a reader that read
    `next` pages too); the index holds `last` only and is skipped when `last`
    is not among them. `like` - an `events_json LIKE ?` prefilter on the
    pages; `sport` - the index's sport column, its counterpart. `only` - ids
    outside it are neither projected nor read from the index.
    """
    where: list[str] = []
    args: list[Any] = []
    if kinds is not None:
        kind_list = sorted(kinds)
        where.append(f"kind IN ({','.join('?' * len(kind_list))})")
        args.extend(kind_list)
    if like is not None:
        where.append("events_json LIKE ?")
        args.append(like)
    # A hand-built table without fetched_at (older test fixtures, a partial
    # copy) reads as stamped "": any indexed copy is newer.
    columns = {str(r[1]) for r in conn.execute(
        "PRAGMA table_info(sofa_entity_events)")}
    stamp_col = "fetched_at" if "fetched_at" in columns else "''"
    sql = f"SELECT events_json, {stamp_col} FROM sofa_entity_events"
    if where:
        sql += " WHERE " + " AND ".join(where)
    out: dict[int, T] = {}
    stamps: dict[int, str] = {}
    rows: Iterator[tuple[Any, Any]] = (
        iter(conn.execute(sql, args)) if columns else iter(()))
    for events_json, fetched_at in rows:
        stamp = str(fetched_at)
        for event in _page_events(events_json):
            eid = event.get("id")
            if not isinstance(eid, int) or eid in out:
                continue
            if only is not None and eid not in only:
                continue
            value = project(event)
            if value is not None:
                out[eid] = value
                stamps[eid] = stamp
    if kinds is None or "last" in kinds:
        for event in iter_indexed_events(conn, stamps, sport=sport, only=only):
            value = project(event)
            if value is not None:
                out[event["id"]] = value
    return out


def entity_indexed_events(
    conn: sqlite3.Connection,
    entity_id: int,
    kind: str,
    before_ts: int,
    limit: int,
) -> list[dict[str, Any]]:
    """The newest `limit` indexed events of one entity's listing that started
    before `before_ts`, newest first."""
    if not has_index(conn):
        return []
    out: list[dict[str, Any]] = []
    for (event_json,) in conn.execute(
        f"""
        SELECT e.event_json
        FROM {LISTING_EVENT} m JOIN {LISTED_EVENT} e ON e.event_id = m.event_id
        WHERE m.entity_id = ? AND m.kind = ? AND m.start_ts < ?
        ORDER BY m.start_ts DESC, m.event_id DESC
        LIMIT ?
        """,
        (entity_id, kind, before_ts, limit),
    ):
        try:
            event = json.loads(event_json)
        except (TypeError, ValueError):
            continue
        if isinstance(event, dict):
            out.append(cast(dict[str, Any], event))
    return out


def entity_indexed_count(
    conn: sqlite3.Connection, entity_id: int, kind: str, after_ts: int,
    before_ts: int,
) -> int:
    """Indexed events of one entity's listing with after_ts < start < before_ts."""
    if not has_index(conn):
        return 0
    row = conn.execute(
        f"SELECT COUNT(*) FROM {LISTING_EVENT} WHERE entity_id = ? AND kind = ? "
        "AND start_ts > ? AND start_ts < ?",
        (entity_id, kind, after_ts, before_ts),
    ).fetchone()
    return int(row[0])


def index_fingerprint(conn: sqlite3.Connection, sport: str) -> str:
    """Row count and newest fetch of one sport's indexed events, read from the
    (sport, fetched_at, event_id) index - no table scan. Changes whenever an
    event is added or re-fetched; "" while the sport has none indexed."""
    if not has_index(conn):
        return ""
    row = conn.execute(
        f"SELECT COUNT(*), MAX(fetched_at) FROM {LISTED_EVENT} WHERE sport = ?",
        (sport,),
    ).fetchone()
    return f"{row[0]}|{row[1]}" if row[0] else ""
