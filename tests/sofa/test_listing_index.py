"""The listed-event index: a match that slides out of every cached page stays.

sofa_entity_events is keyed by page number and page 0 is always the newest, so
whenever SAMPLES/RESOLVE re-save pages 0-2 the match that slid from the old
page 2 into page 3's range is on no stored page (the old page 3 never had
it). On 2026-10-01/02 backfill_listings re-walked 962 football and 550 tennis
entities to recover such matches, and the loss recurred daily. Every saved
`last` page now also upserts its events by event id (listing_index.py).
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from bet.sofa import football_rating, tennis_rating
from bet.sofa.cache import SofaCache
from bet.sofa.config import SofaConfig
from bet.sofa.contracts import Fixture
from bet.sofa.db import migrate
from bet.sofa.listing_index import (
    LISTED_EVENT,
    LISTING_EVENT,
    index_page,
    iter_indexed_events,
)
from bet.sofa.samples import get_historical_events
from scripts.sofa import index_listing_events as fill_script
from scripts.sofa.backfill_listings import scan

DAY = 86400
T0 = 1_780_000_000  # all matches before KICKOFF
KICKOFF = datetime.fromtimestamp(T0 + 400 * DAY, UTC)
ENTITY = 10


def _football(eid: int, ts: int, status: str = "finished",
              home: int = ENTITY) -> dict[str, Any]:
    return {
        "id": eid, "startTimestamp": ts,
        "status": {"type": status, "code": 100 if status == "finished" else 0},
        "tournament": {"id": 5, "category": {"sport": {"slug": "football"}},
                       "uniqueTournament": {"id": 17}},
        "homeTeam": {"id": home, "name": "A"},
        "awayTeam": {"id": 7000 + eid, "name": f"B{eid}"},
        "homeScore": {"current": 2, "normaltime": 2, "period1": 1},
        "awayScore": {"current": 1, "normaltime": 1, "period1": 0},
        "winnerCode": 1,
    }


def _page(events: list[dict[str, Any]]) -> dict[str, Any]:
    # Sofascore returns a page ascending (oldest first).
    return {"events": sorted(events, key=lambda e: e["startTimestamp"]),
            "hasNextPage": True}


def _matches(n: int) -> list[dict[str, Any]]:
    """n matches of ENTITY, newest first, ids 1..n, two days apart."""
    return [_football(i + 1, T0 + (n - i) * 2 * DAY) for i in range(n)]


def _raw_insert(db: str, entity: int, page: int, payload: dict[str, Any],
                fetched_at: str) -> None:
    """A page as code before the index wrote it: no index rows."""
    con = sqlite3.connect(db)
    con.execute("INSERT OR REPLACE INTO sofa_entity_events VALUES (?, 'last', ?, ?, ?)",
                (entity, page, fetched_at, json.dumps(payload)))
    con.commit()
    con.close()


def _cache(tmp_path: Path, **kw: Any) -> SofaCache:
    db = str(tmp_path / "sofa.db")
    migrate(db)
    return SofaCache(SofaConfig(db_path=db, **kw))


def _slide(cache: SofaCache, page_size: int = 4, played: int = 1) -> int:
    """Save pages 0-3 of 16 matches, then the entity plays `played` more and
    pages 0-2 are saved again over them (page 3 is not). Returns the id of
    the match that slid out of every stored page."""
    old = _matches(16)
    for p in range(4):
        cache.save_entity_events(ENTITY, "last", p,
                                 _page(old[p * page_size:(p + 1) * page_size]))
    new = [_football(100 + i, T0 + (17 + i) * 2 * DAY) for i in range(played)]
    now = sorted(new, key=lambda e: -e["startTimestamp"]) + old
    for p in range(3):
        cache.save_entity_events(ENTITY, "last", p,
                                 _page(now[p * page_size:(p + 1) * page_size]))
    lost = old[3 * page_size - played]["id"]
    return int(lost)


def _ids_on_pages(db: str) -> set[int]:
    con = sqlite3.connect(db)
    ids = {e["id"] for (j,) in con.execute(
               "SELECT events_json FROM sofa_entity_events WHERE kind = 'last'")
           for e in json.loads(j)["events"]}
    con.close()
    return ids


def test_a_match_that_slid_out_of_every_page_is_still_in_the_football_history(
        tmp_path: Path) -> None:
    cache = _cache(tmp_path)
    lost = _slide(cache)
    db = cache.config.db_path
    assert lost not in _ids_on_pages(db)  # the defect: on no stored page
    history = football_rating.load_history(db)
    assert lost in {r.event_id for r in history}
    assert len({r.event_id for r in history}) == 17


def test_the_sample_reads_the_slid_out_match_from_the_index(tmp_path: Path) -> None:
    # Four pages of four, sample of 14: the walk reads page 3 (the stale one),
    # so the lost match lies inside the span the pages cover.
    cache = _cache(tmp_path, sample_n=14)
    lost = _slide(cache)

    class _NoNetwork:
        def entity_events(self, *a: Any) -> Any:
            raise AssertionError("every page is cached inside its TTL")

    fixture = _fixture()
    got = get_historical_events(_NoNetwork(), cache, ENTITY, "football",  # type: ignore[arg-type]
                                fixture, cache.config, gaps=[])
    ids = [e["id"] for e in got]
    assert lost in ids
    assert len(ids) == 14
    assert ids == sorted(ids, key=lambda i: -next(
        e["startTimestamp"] for e in got if e["id"] == i))


def test_the_index_adds_nothing_to_a_sample_the_pages_already_cover(
        tmp_path: Path) -> None:
    # No slide: the pages are contiguous, so the sample is the page-only one.
    cache = _cache(tmp_path, sample_n=6)
    old = _matches(12)
    for p in range(3):
        cache.save_entity_events(ENTITY, "last", p, _page(old[p * 4:(p + 1) * 4]))

    class _NoNetwork:
        def entity_events(self, *a: Any) -> Any:
            raise AssertionError("cached")

    with_index = get_historical_events(_NoNetwork(), cache, ENTITY, "football",  # type: ignore[arg-type]
                                       _fixture(), cache.config, gaps=[])
    con = sqlite3.connect(cache.config.db_path)
    con.execute(f"DELETE FROM {LISTING_EVENT}")
    con.execute(f"DELETE FROM {LISTED_EVENT}")
    con.commit()
    con.close()
    pages_only = get_historical_events(_NoNetwork(), cache, ENTITY, "football",  # type: ignore[arg-type]
                                       _fixture(), cache.config, gaps=[])
    assert with_index == pages_only
    assert [e["id"] for e in pages_only] == [1, 2, 3, 4, 5, 6]


def test_a_short_sample_is_topped_up_from_the_index_without_a_request(
        tmp_path: Path) -> None:
    cache = _cache(tmp_path, sample_n=10)
    old = _matches(12)
    # The index knows all twelve; only page 0 (four) is still stored.
    con = sqlite3.connect(cache.config.db_path)
    index_page(con, ENTITY, "last", "2026-01-01T00:00:00+00:00", _page(old))
    con.commit()
    con.close()
    cache.save_entity_events(ENTITY, "last", 0, _page(old[:4]))

    class _EmptyAfterPage0:
        def entity_events(self, entity_id: int, kind: str, page: int) -> Any:
            return {"events": [], "hasNextPage": False}

    got = get_historical_events(_EmptyAfterPage0(), cache, ENTITY, "football",  # type: ignore[arg-type]
                                _fixture(), cache.config, gaps=[])
    assert [e["id"] for e in got] == list(range(1, 11))


def _old_football_events(db: str) -> dict[int, dict[str, Any]]:
    """The football reader exactly as it was before the index (reference)."""
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    events: dict[int, dict[str, Any]] = {}
    for (events_json,) in con.execute(
        "SELECT events_json FROM sofa_entity_events WHERE kind = 'last' "
        "AND events_json LIKE '%\"slug\": \"football\"%'"
    ):
        for event in json.loads(events_json).get("events", []):
            if isinstance(event.get("id"), int):
                events[event["id"]] = event
    con.close()
    return events


def _old_fingerprint(db: str) -> str:
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    lst = con.execute("SELECT COUNT(*), MAX(fetched_at) FROM sofa_entity_events "
                      "WHERE kind = 'last'").fetchone()
    sts = con.execute(
        "SELECT COUNT(*), MAX(fetched_at) FROM sofa_event_stats").fetchone()
    con.close()
    friendlies = ",".join(
        str(c) for c in sorted(football_rating.FRIENDLY_COMPETITION_IDS))
    return (f"{football_rating.HISTORY_PARSER_VERSION}|{lst[0]}|{lst[1]}|"
            f"{sts[0]}|{sts[1]}|{friendlies}"
            f"|reserve:{football_rating.reserve_fingerprint()}")


@pytest.mark.parametrize("with_tables", [True, False])
def test_an_empty_index_leaves_every_history_reader_as_it_was(
        tmp_path: Path, with_tables: bool) -> None:
    db = str(tmp_path / "sofa.db")
    migrate(db)
    if not with_tables:  # a file no migrate() has touched since the index
        con = sqlite3.connect(db)
        con.execute(f"DROP TABLE {LISTED_EVENT}")
        con.execute(f"DROP TABLE {LISTING_EVENT}")
        con.commit()
        con.close()
    matches = _matches(10)
    # The same match on two sides' pages with two payloads: the page row
    # read last wins, as before.
    _raw_insert(db, ENTITY, 0, _page(matches[:5]), "2026-09-01T00:00:00+00:00")
    other = dict(matches[0], homeScore={"current": 5, "normaltime": 5})
    _raw_insert(db, 99, 0, _page([other]), "2026-09-02T00:00:00+00:00")
    _raw_insert(db, ENTITY, 1, _page(matches[5:]), "2026-09-01T00:00:00+00:00")

    expected = [r for e in _old_football_events(db).values()
                if (r := football_rating.parse_event(e)) is not None]
    expected.sort(key=lambda r: (r.ts, r.event_id))
    assert football_rating.load_history(db) == expected
    assert football_rating.history_fingerprint(db) == _old_fingerprint(db)
    con = sqlite3.connect(db)
    assert list(iter_indexed_events(con, set())) == []
    con.close()


def test_the_fingerprint_moves_when_only_the_index_changes(tmp_path: Path) -> None:
    db = str(tmp_path / "sofa.db")
    migrate(db)
    _raw_insert(db, ENTITY, 0, _page(_matches(3)), "2026-09-01T00:00:00+00:00")
    before = football_rating.history_fingerprint(db)
    con = sqlite3.connect(db)
    index_page(con, ENTITY, "last", "2026-09-03T00:00:00+00:00",
               _page([_football(500, T0)]))
    con.commit()
    after_add = football_rating.history_fingerprint(db)
    # A re-fetch of the same event (newer payload) moves it too.
    index_page(con, ENTITY, "last", "2026-09-04T00:00:00+00:00",
               _page([_football(500, T0)]))
    con.commit()
    con.close()
    after_refetch = football_rating.history_fingerprint(db)
    assert len({before, after_add, after_refetch}) == 3
    # And the pickled history is rebuilt for it.
    cache_dir = tmp_path / "cache"
    con = sqlite3.connect(db)
    index_page(con, ENTITY, "last", "2026-09-05T00:00:00+00:00",
               _page([_football(501, T0 + DAY)]))
    con.commit()
    con.close()
    assert 501 in {r.event_id for r in football_rating.load_history(db, cache_dir)}


def test_the_newest_payload_wins_in_the_index_and_in_the_reader(tmp_path: Path) -> None:
    db = str(tmp_path / "sofa.db")
    migrate(db)
    con = sqlite3.connect(db)
    upcoming = _football(1, T0, status="notstarted")
    finished = _football(1, T0)
    index_page(con, ENTITY, "last", "2026-09-02T00:00:00+00:00", _page([finished]))
    # An older fetch arriving later (the fill walking an old page) loses.
    index_page(con, ENTITY, "last", "2026-09-01T00:00:00+00:00", _page([upcoming]))
    con.commit()
    status = json.loads(con.execute(
        f"SELECT event_json FROM {LISTED_EVENT}").fetchone()[0])["status"]["type"]
    con.close()
    assert status == "finished"
    # The page still holds the stale notstarted copy; the reader takes the
    # index's newer one.
    _raw_insert(db, ENTITY, 0, _page([upcoming]), "2026-09-01T00:00:00+00:00")
    assert [r.event_id for r in football_rating.load_history(db)] == [1]


def test_next_pages_are_not_indexed(tmp_path: Path) -> None:
    cache = _cache(tmp_path)
    cache.save_entity_events(ENTITY, "next", 0,
                             _page([_football(9, T0, status="notstarted")]))
    con = sqlite3.connect(cache.config.db_path)
    assert con.execute(f"SELECT COUNT(*) FROM {LISTED_EVENT}").fetchone()[0] == 0
    con.close()


def _tennis(eid: int, ts: int) -> dict[str, Any]:
    return {
        "id": eid, "startTimestamp": ts, "groundType": "Hardcourt outdoor",
        "status": {"type": "finished", "code": 100, "description": "Ended"},
        "winnerCode": 1,
        "tournament": {"category": {"name": "ATP", "sport": {"slug": "tennis"}}},
        "homeTeam": {"id": ENTITY, "type": 1},
        "awayTeam": {"id": 7000 + eid, "type": 1},
        "homeScore": {"period1": 6, "period2": 6},
        "awayScore": {"period1": 3, "period2": 4},
    }


def test_the_tennis_history_reads_the_index_too(tmp_path: Path) -> None:
    db = str(tmp_path / "sofa.db")
    migrate(db)
    kept, lost = _tennis(1, T0 + DAY), _tennis(2, T0)
    assert tennis_rating.parse_event(lost) is not None
    _raw_insert(db, ENTITY, 0, _page([kept]), "2026-09-02T00:00:00+00:00")
    assert [r.event_id for r in tennis_rating.load_history(db)] == [1]
    con = sqlite3.connect(db)
    index_page(con, ENTITY, "last", "2026-09-01T00:00:00+00:00", _page([lost]))
    con.commit()
    con.close()
    assert [r.event_id for r in tennis_rating.load_history(db)] == [2, 1]


# --- the one-time fill -------------------------------------------------------

def _pre_index_db(tmp_path: Path, name: str = "sofa.db") -> str:
    """Pages written before the index existed: nothing indexed."""
    db = str(tmp_path / name)
    migrate(db)
    for p in range(6):
        events = [_football(p * 10 + i, T0 + (60 - p * 10 - i) * DAY) for i in range(5)]
        _raw_insert(db, ENTITY, p, _page(events), f"2026-09-0{p + 1}T00:00:00+00:00")
    # The same match on the opponent's listing, a later fetch.
    _raw_insert(db, 77, 0, _page([_football(0, T0 + 60 * DAY)]),
                "2026-09-09T00:00:00+00:00")
    con = sqlite3.connect(db)
    con.execute("INSERT INTO sofa_entity_events VALUES (5, 'next', 0, 'x', '{}')")
    con.commit()
    con.close()
    return db


def _index_dump(db: str) -> tuple[list[Any], list[Any]]:
    con = sqlite3.connect(db)
    events = con.execute(f"SELECT * FROM {LISTED_EVENT} ORDER BY event_id").fetchall()
    members = con.execute(
        f"SELECT * FROM {LISTING_EVENT} ORDER BY entity_id, kind, event_id").fetchall()
    con.close()
    return events, members


def test_the_fill_is_resumable_and_idempotent(tmp_path: Path) -> None:
    whole = _pre_index_db(tmp_path, "whole.db")
    result = fill_script.fill(whole, batch=100, max_minutes=None, pause_ms=0)
    assert result["remaining_pages"] == 0 and result["pages"] == 7
    reference = _index_dump(whole)
    assert len(reference[0]) == 30 and len(reference[1]) == 31

    chunked = _pre_index_db(tmp_path, "chunked.db")
    first = fill_script.fill(chunked, batch=2, max_minutes=1e-9, pause_ms=0)
    assert first["timed_out"] and first["pages"] == 2 and first["remaining_pages"] == 5
    runs = 1
    while fill_script.fill(chunked, batch=2, max_minutes=1e-9,
                           pause_ms=0)["remaining_pages"]:
        runs += 1
        assert runs < 10
    assert _index_dump(chunked) == reference

    again = fill_script.fill(chunked, batch=2, max_minutes=None, pause_ms=0)
    assert again["pages"] == 0 and again["remaining_pages"] == 0
    assert _index_dump(chunked) == reference

    # A page saved again after the fill (old code: no index rows) has a new
    # rowid, so the next run picks it up.
    _raw_insert(chunked, ENTITY, 0, _page([_football(900, T0 + 99 * DAY)]),
                "2026-09-20T00:00:00+00:00")
    late = fill_script.fill(chunked, batch=2, max_minutes=None, pause_ms=0)
    assert late["pages"] == 1
    assert 900 in {row[0] for row in _index_dump(chunked)[0]}


def test_the_fill_makes_the_readers_see_what_the_pages_lost(tmp_path: Path) -> None:
    db = _pre_index_db(tmp_path)
    fill_script.fill(db, batch=3, max_minutes=None, pause_ms=0)
    before = {r.event_id for r in football_rating.load_history(db)}
    # Page 2 is replaced by a page that no longer carries match 20.
    _raw_insert(db, ENTITY, 2, _page([_football(i, T0 + (40 - i + 20) * DAY)
                                      for i in range(21, 25)]),
                "2026-09-30T00:00:00+00:00")
    assert 20 not in _ids_on_pages(db)
    assert {r.event_id for r in football_rating.load_history(db)} == before


def test_the_dry_run_counts_and_writes_nothing(tmp_path: Path) -> None:
    db = _pre_index_db(tmp_path)
    digest = hashlib.md5(Path(db).read_bytes()).hexdigest()
    report = fill_script.dry_run(db, batch=2)
    assert hashlib.md5(Path(db).read_bytes()).hexdigest() == digest
    assert report["pages_to_index"] == 7
    assert report["events"] == 31
    assert report["distinct_events"] == 30
    assert report["already_indexed_events"] == 0


# --- backfill_listings: a gap the index holds is not re-walked ----------------

def _iso(ts: int) -> str:
    return datetime.fromtimestamp(ts, UTC).isoformat()


def test_a_gap_whose_lost_matches_the_index_holds_is_not_a_gap() -> None:
    now = T0 + 400 * DAY

    def page(stamps: list[int], first: int) -> str:
        return json.dumps(_page(
            [_football(first + i, ts) for i, ts in enumerate(stamps)]))

    # Page 1 fetched 10 days before page 0, one match played since: one lost.
    rows = [
        (ENTITY, 0, page([now - DAY, now - 20 * DAY], 100), _iso(now)),
        (ENTITY, 1, page([now - 30 * DAY, now - 60 * DAY], 200), _iso(now - 10 * DAY)),
    ]
    since = now - 730 * DAY
    calls: list[tuple[int, int, int]] = []

    def holds(n: int) -> Any:
        def count(entity_id: int, after: int, before: int) -> int:
            calls.append((entity_id, after, before))
            return n
        return count

    state = scan(rows, "football", now - 400 * DAY)[ENTITY]
    assert state.first_gap(since) == 1  # no index: a gap, as before
    state.indexed = holds(0)
    assert state.first_gap(since) == 1  # the index lacks the lost match
    state.indexed = holds(1)
    assert state.first_gap(since) is None
    assert state.first_gap(since, use_index=False) == 1
    # Asked strictly between page 1's newest and page 0's oldest.
    assert calls[-1] == (ENTITY, now - 30 * DAY, now - 20 * DAY)


def _fixture() -> Fixture:
    return Fixture(
        sofascore_event_id=1, superbet_event_ids=["1"], sport="football",
        kickoff_utc=KICKOFF, home_name="A", away_name="B",
        home_entity_id=ENTITY, away_entity_id=20, competition_name="Liga",
        competition_id=17, season_id=1, category_name="Cat",
        identity="CONFIRMED", round_number=1, round_name=None,
        cup_round_type=None, previous_leg_event_id=None, venue_name=None,
        referee=None, ground_type=None, default_period_count=None,
    )
