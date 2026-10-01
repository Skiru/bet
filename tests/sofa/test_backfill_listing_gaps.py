"""backfill_listings: cached pages that no longer join up are a gap, not done.

sofa_entity_events is keyed by page number and page 0 is always the newest, so
when SAMPLES/RESOLVE re-fetch pages 0-2 the deeper pages an older backfill
wrote no longer join up: the matches that slid across the boundary are on no
page. On 2026-10-01 player 65576's page 2 (fetched 09-28) reached back to
2025-10-31 while page 3 (fetched 09-18) began on 2025-10-03 - five finished
matches in neither - and EntityState.done() looked only at the deepest page.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from scripts.sofa.backfill_listings import (
    Deepen,
    plan,
    read_only_connection,
    scan,
    seed_cut,
)

DAY = 86400
NOW = 1_800_000_000
SINCE = NOW - 730 * DAY
RECENT = NOW - 400 * DAY


def _iso(ts: int) -> str:
    return datetime.fromtimestamp(ts, UTC).isoformat()


def _page(stamps: list[int], first_id: int, has_next: bool = True) -> str:
    events = [{"id": first_id + i, "startTimestamp": ts,
               "tournament": {"category": {"sport": {"slug": "football"}}},
               "homeTeam": {"id": 1}, "awayTeam": {"id": 900 + i}}
              for i, ts in enumerate(stamps)]
    return json.dumps({"events": events, "hasNextPage": has_next})


def _rows(page0_fetched: int, page1_fetched: int, page2_fetched: int):
    # Page 0 holds a match played a day ago; pages 1-2 are disjoint and older.
    return [
        (1, 0, _page([NOW - DAY, NOW - 20 * DAY], 100), _iso(page0_fetched)),
        (1, 1, _page([NOW - 30 * DAY, NOW - 60 * DAY], 200), _iso(page1_fetched)),
        (1, 2, _page([NOW - 70 * DAY, NOW - 100 * DAY], 300), _iso(page2_fetched)),
    ]


def test_fresh_page_0_over_a_stale_page_1_is_a_gap_from_page_1():
    # Page 1 was fetched ten days ago; the entity has played since, so the
    # listing moved and the match that slid off page 0 is on no cached page.
    states = scan(_rows(NOW, NOW - 10 * DAY, NOW - 10 * DAY), "football", RECENT)
    s = states[1]
    assert s.first_gap(SINCE) == 1
    assert not s.done(SINCE)
    todo = plan(states, board=set(), since_ts=SINCE, recent_since=RECENT)
    assert [t.entity_id for t in todo if t.entity_id == 1] == [1]
    assert s.start_page(SINCE) == 1


def test_pages_fetched_together_are_contiguous_and_done_when_they_reach_back():
    rows = _rows(NOW, NOW, NOW)
    rows.append((1, 3, _page([NOW - 200 * DAY, SINCE - DAY], 400), _iso(NOW)))
    states = scan(rows, "football", RECENT)
    s = states[1]
    assert s.first_gap(SINCE) is None
    assert s.done(SINCE)
    todo = plan(states, board={1}, since_ts=SINCE, recent_since=RECENT)
    assert 1 not in [t.entity_id for t in todo]


def test_a_stale_page_is_no_gap_when_the_entity_has_not_played_since():
    # Page 1 is ten days older than page 0, but nothing was played in between
    # (page 0's newest match is 20 days old): the listing did not move.
    rows = [
        (1, 0, _page([NOW - 20 * DAY, NOW - 25 * DAY], 100), _iso(NOW)),
        (1, 1, _page([NOW - 30 * DAY, SINCE - DAY], 200), _iso(NOW - 10 * DAY)),
    ]
    assert scan(rows, "football", RECENT)[1].first_gap(SINCE) is None


def test_overlapping_pages_join_up_and_a_deeper_page_fetched_later_is_fine():
    rows = [
        (1, 0, _page([NOW - DAY, NOW - 20 * DAY], 100), _iso(NOW - 10 * DAY)),
        # fetched later: the listing grew, so page 1 repeats page 0's oldest
        (1, 1, _page([NOW - 20 * DAY, NOW - 40 * DAY], 200), _iso(NOW)),
    ]
    assert scan(rows, "football", RECENT)[1].first_gap(SINCE) is None


def test_a_missing_page_inside_the_window_is_a_gap():
    rows = _rows(NOW, NOW, NOW)
    del rows[1]
    assert scan(rows, "football", RECENT)[1].first_gap(SINCE) == 1


def test_a_gap_past_the_window_is_not_judged():
    rows = [
        (1, 0, _page([NOW - DAY, SINCE - DAY], 100), _iso(NOW)),
        (1, 1, _page([SINCE - 400 * DAY], 200), _iso(NOW - 10 * DAY)),
    ]
    s = scan(rows, "football", RECENT)[1]
    assert s.first_gap(SINCE) is None and s.done(SINCE)


def test_a_gapped_entity_that_says_no_next_page_is_still_not_done():
    rows = _rows(NOW, NOW - 10 * DAY, NOW - 10 * DAY)
    rows[2] = (1, 2, _page([NOW - 70 * DAY], 300, has_next=False),
               _iso(NOW - 10 * DAY))
    assert not scan(rows, "football", RECENT)[1].done(SINCE)


class _Client:
    def __init__(self) -> None:
        self.asked: list[int] = []

    def entity_events(self, entity_id: int, kind: str, page: int) -> dict:
        self.asked.append(page)
        ts = NOW - 30 * DAY * (page + 1)
        return {"events": [{"id": page, "startTimestamp": ts}],
                "hasNextPage": page < 30}


class _Cache:
    def __init__(self) -> None:
        self.saved: list[int] = []

    def get_listing_miss(self, entity_id: int, kind: str, page: int) -> bool:
        return False

    def save_listing_miss(self, entity_id: int, kind: str, page: int) -> None:
        pass

    def save_entity_events(self, entity_id: int, kind: str, page: int,
                           payload: dict) -> None:
        self.saved.append(page)


def test_the_walk_restarts_at_the_gap_and_runs_on_to_the_window():
    s = scan(_rows(NOW, NOW - 10 * DAY, NOW - 10 * DAY), "football", RECENT)[1]
    client, cache = _Client(), _Cache()
    Deepen(client, cache, SINCE, None).run_one(s)
    # page 1 is re-fetched (not page 3), then the walk goes on until a page
    # reaches back past SINCE: 30 days a page -> page 24 is the first past it.
    assert client.asked[0] == 1
    assert client.asked == list(range(1, 25))
    assert cache.saved == client.asked


def test_planning_reads_open_the_cache_read_only(tmp_path: Path) -> None:
    db = tmp_path / "c.db"
    sqlite3.connect(db).execute("CREATE TABLE t (x INTEGER)").connection.commit()
    conn = read_only_connection(str(db))
    try:
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("INSERT INTO t VALUES (1)")
    finally:
        conn.close()


def test_a_dry_run_does_not_record_a_seed(tmp_path: Path) -> None:
    path = tmp_path / "seed.json"
    assert seed_cut(path, "football", "2026-10-01T00:00:00", record=False) == (
        "2026-10-01T00:00:00")
    assert not path.exists()
