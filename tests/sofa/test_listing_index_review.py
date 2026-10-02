"""Review fixes (2026-10-02) of the listed-event index (listing_index.py).

F1 page-only readers lost what backfill_listings no longer re-walks: they read
listed_events_by_id (pages + index, newest payload wins) and are unchanged
while the index is empty. F2 no index top-up without a page. F3 the one-time
fill's pacing, WAL guard and remaining count. F4 the index never forgets, so
SAMPLES adds an indexed event only between pages. F5 a stale pre-match copy no
longer hides the finished one. F6 tennis drops a stale page result like
football; event_sport never raises inside the page save.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

import pytest

from bet.sofa import tennis_rating
from bet.sofa.contracts import GapReason
from bet.sofa.listing_index import (
    LISTED_EVENT,
    LISTING_EVENT,
    event_sport,
    index_page,
    listed_events_by_id,
)
from bet.sofa.samples import get_historical_events
from scripts.sofa import calibrate_from_cache, fit_confidence
from scripts.sofa import fit_no_stats_tournaments as no_stats
from scripts.sofa import index_listing_events as fill_script
from scripts.sofa.backfill_event_stats import _iter_listings
from scripts.sofa.find_women_competitions import main as find_women_main
from scripts.sofa.fit_tennis_tier_baselines import iter_tennis_events
from scripts.sofa.refetch_provisional_stats import kickoffs
from scripts.sofa.regrade_settled import listing_events, match_tiebreak_events
from tests.sofa.test_listing_index import (
    DAY,
    ENTITY,
    T0,
    _cache,
    _fixture,
    _football,
    _page,
    _raw_insert,
    _tennis,
)


def _db(tmp_path: Path) -> str:
    from bet.sofa.db import migrate

    db = str(tmp_path / "sofa.db")
    migrate(db)
    return db


def _index(db: str, entity: int, events: list[dict[str, Any]], at: str) -> None:
    con = sqlite3.connect(db)
    index_page(con, entity, "last", at, _page(events))
    con.commit()
    con.close()


def _countable_tennis(eid: int, ts: int) -> dict[str, Any]:
    event = _tennis(eid, ts)
    event["homeScore"] = dict(event["homeScore"], current=2)
    event["awayScore"] = dict(event["awayScore"], current=0)
    return event


def _women(eid: int, ts: int) -> dict[str, Any]:
    event = _football(eid, ts)
    event["homeTeam"] = {"id": ENTITY, "name": "A", "gender": "F"}
    event["awayTeam"] = {"id": 7000 + eid, "name": "B", "gender": "F"}
    return event


# --- F1: the shared reader ---------------------------------------------------

def test_the_union_reader_is_the_page_reader_while_the_index_is_empty(
        tmp_path: Path) -> None:
    db = _db(tmp_path)
    a, b = _football(1, T0), _football(2, T0 + DAY)
    later_b = dict(b, homeScore={"current": 9})
    _raw_insert(db, ENTITY, 0, _page([a, b]), "2026-09-01T00:00:00+00:00")
    _raw_insert(db, 99, 0, _page([later_b]), "2026-09-05T00:00:00+00:00")
    con = sqlite3.connect(db)
    got = listed_events_by_id(con, lambda e: e)
    # First page copy in rowid order, as every replaced reader kept.
    assert list(got) == [1, 2] and got[2] == b
    # The index adds what the pages lack and replaces an older page copy.
    con.close()
    newer_a = dict(a, homeScore={"current": 4})
    _index(db, ENTITY, [newer_a, _football(3, T0 - DAY)], "2026-09-03T00:00:00+00:00")
    con = sqlite3.connect(db)
    got = listed_events_by_id(con, lambda e: e)
    assert got[1] == newer_a and got[2] == b and 3 in got
    # `only` and a projection that refuses a copy.
    assert set(listed_events_by_id(con, lambda e: e, only={3})) == {3}
    assert set(listed_events_by_id(
        con, lambda e: e if e["id"] != 3 else None)) == {1, 2}
    # The index holds `last` only: a `next`-only read never sees it.
    assert listed_events_by_id(con, lambda e: e, kinds=("next",)) == {}
    con.close()


def test_a_table_without_fetched_at_still_reads(tmp_path: Path) -> None:
    con = sqlite3.connect(str(tmp_path / "bare.db"))
    con.execute("CREATE TABLE sofa_entity_events (kind TEXT, events_json TEXT)")
    con.execute("INSERT INTO sofa_entity_events VALUES ('last', ?)",
                (json.dumps(_page([_football(1, T0)])),))
    assert list(listed_events_by_id(con, lambda e: e)) == [1]
    con.close()


def test_an_index_only_womens_match_is_classed_for_the_fit(tmp_path: Path) -> None:
    db = _db(tmp_path)
    _raw_insert(db, ENTITY, 0, _page([_women(1, T0)]), "2026-09-01T00:00:00+00:00")
    assert fit_confidence.load_event_classes(db) == {1: "women"}
    # The match slid out of every page; the replay still writes its rows.
    _index(db, ENTITY, [_women(2, T0 - DAY)], "2026-09-01T00:00:00+00:00")
    assert fit_confidence.load_event_classes(db) == {1: "women", 2: "women"}


def test_regrade_reads_index_only_matches(tmp_path: Path) -> None:
    db = _db(tmp_path)
    tb = _tennis(5, T0)
    tb["homeScore"] = {"period1": 6, "period2": 3, "period3": 10}
    tb["awayScore"] = {"period1": 3, "period2": 6, "period3": 7}
    con = sqlite3.connect(db)
    assert listing_events(con, {1, 5}) == {}
    assert match_tiebreak_events(con) == set()
    con.close()
    _index(db, ENTITY, [_football(1, T0), tb], "2026-09-01T00:00:00+00:00")
    con = sqlite3.connect(db)
    assert set(listing_events(con, {1, 5})) == {1, 5}
    assert set(listing_events(con, {1})) == {1}
    assert match_tiebreak_events(con) == {5}
    con.close()


def test_kickoffs_and_the_tier_fit_read_the_index(tmp_path: Path) -> None:
    db = _db(tmp_path)
    _raw_insert(db, ENTITY, 0, _page([_countable_tennis(1, T0)]),
                "2026-09-01T00:00:00+00:00")
    _raw_insert(db, 77, 0, _page([_countable_tennis(1, T0)]),
                "2026-09-02T00:00:00+00:00")
    con = sqlite3.connect(db)
    assert kickoffs(con) == {1: (T0, "tennis")}
    con.close()
    # One copy per match now, not one per listing.
    assert [e["id"] for e in iter_tennis_events(db)] == [1]
    _index(db, ENTITY, [_countable_tennis(2, T0 - DAY)], "2026-09-01T00:00:00+00:00")
    con = sqlite3.connect(db)
    assert kickoffs(con) == {1: (T0, "tennis"), 2: (T0 - DAY, "tennis")}
    con.close()
    assert [e["id"] for e in iter_tennis_events(db)] == [1, 2]


def test_find_women_and_no_stats_read_the_index(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "root"
    (root / "data").mkdir(parents=True)
    db = _db(root / "data")
    _index(db, ENTITY, [_women(i, T0 - i * DAY) for i in range(1, 4)],
           "2026-09-01T00:00:00+00:00")
    out = tmp_path / "women.json"
    monkeypatch.setattr(sys, "argv", ["x", "--db-path", db, "--out", str(out)])
    assert find_women_main() == 0
    assert [w["competition_id"] for w in json.loads(out.read_text())["women"]] == [17]

    con = sqlite3.connect(db)
    for i in range(1, 4):
        con.execute("INSERT INTO sofa_event_stats (sofascore_event_id, status_type, "
                    "fetched_at) VALUES (?, 'finished', 'x')", (i,))
    con.commit()
    con.close()
    monkeypatch.setattr(no_stats, "ROOT", root)
    monkeypatch.setattr(no_stats, "OUT_PATH", tmp_path / "no_stats.json")
    monkeypatch.setattr(no_stats, "MIN_EVENTS", 3)
    assert no_stats.main() == 0
    written = json.loads((tmp_path / "no_stats.json").read_text())
    assert [t["id"] for t in written["tournaments"]] == [17]


# --- F2: no index without a page ----------------------------------------------

def test_no_page_read_means_no_index_top_up_and_a_gap(tmp_path: Path) -> None:
    cache = _cache(tmp_path, sample_n=5)
    _index(cache.config.db_path, ENTITY,
           [_football(i, T0 + i * DAY) for i in range(1, 9)],
           "2026-09-01T00:00:00+00:00")

    class _PageZeroGone:
        def entity_events(self, *a: Any) -> Any:
            return None  # TTL expired, the re-fetch failed

    gaps: list[Any] = []
    got = get_historical_events(_PageZeroGone(), cache, ENTITY, "football",  # type: ignore[arg-type]
                                _fixture(), cache.config, gaps=gaps)
    assert got == []
    assert [g.reason for g in gaps] == [GapReason.PROVIDER_ERROR]
    assert "listing page 0 unavailable" in gaps[0].detail


# --- F4: the index never forgets ----------------------------------------------

def test_an_indexed_event_inside_a_pages_span_is_not_added(tmp_path: Path) -> None:
    cache = _cache(tmp_path, sample_n=6)
    t = [T0 + i * DAY for i in range(20)]
    removed = _football(50, t[15])  # once listed between ids 1 and 2
    slid = _football(60, t[11])     # between page 0 and page 1
    _index(cache.config.db_path, ENTITY, [removed, slid], "2026-09-01T00:00:00+00:00")
    cache.save_entity_events(ENTITY, "last", 0, _page(
        [_football(1, t[16]), _football(2, t[14]), _football(3, t[12])]))
    cache.save_entity_events(ENTITY, "last", 1, _page(
        [_football(4, t[10]), _football(5, t[9]), _football(6, t[8])]))

    class _NoNetwork:
        def entity_events(self, *a: Any) -> Any:
            raise AssertionError("cached")

    got = get_historical_events(_NoNetwork(), cache, ENTITY, "football",  # type: ignore[arg-type]
                                _fixture(), cache.config, gaps=[])
    ids = [e["id"] for e in got]
    assert 50 not in ids  # inside page 0's own span: removed by Sofascore
    assert ids == [1, 2, 3, 60, 4, 5]


def test_beyond_the_deepest_page_only_tops_up_a_short_sample(tmp_path: Path) -> None:
    # Index: an older finished match and an older abandoned one (its
    # EVENT_NOT_FINISHED gap shows whether the index was consulted there).
    def run(sample_n: int) -> tuple[list[int], list[Any]]:
        (tmp_path / str(sample_n)).mkdir()
        cache = _cache(tmp_path / str(sample_n), sample_n=sample_n)
        _index(cache.config.db_path, ENTITY,
               [_football(9, T0), _football(8, T0 - DAY, status="canceled")],
               "2026-09-01T00:00:00+00:00")
        cache.save_entity_events(ENTITY, "last", 0, _page(
            [_football(i, T0 + i * DAY) for i in range(1, 5)]))

        class _EndOfListing:
            def entity_events(self, *a: Any) -> Any:
                return {"events": [], "hasNextPage": False}

        gaps: list[Any] = []
        got = get_historical_events(_EndOfListing(), cache, ENTITY, "football",  # type: ignore[arg-type]
                                    _fixture(), cache.config, gaps=gaps)
        return [e["id"] for e in got], gaps

    full, gaps = run(3)
    assert full == [4, 3, 2] and gaps == []
    short, gaps = run(6)
    assert short == [4, 3, 2, 1, 9]
    assert [g.reason for g in gaps] == [GapReason.EVENT_NOT_FINISHED]


# --- F5: a stale pre-match copy does not hide the finished one ---------------

def test_calibration_takes_the_finished_copy_over_a_stale_next_one(
        tmp_path: Path) -> None:
    db = _db(tmp_path)
    upcoming = _football(1, T0, status="notstarted")
    con = sqlite3.connect(db)
    con.execute("INSERT INTO sofa_entity_events VALUES (?, 'next', 0, ?, ?)",
                (ENTITY, "2026-08-30T00:00:00+00:00", json.dumps(_page([upcoming]))))
    con.commit()
    con.close()
    assert calibrate_from_cache.load_cache(Path(db)) == []
    _index(db, ENTITY, [_football(1, T0)], "2026-09-01T00:00:00+00:00")
    assert [p.event_id for p in calibrate_from_cache.load_cache(Path(db))] == [1]
    # The same on a page: a finished `last` copy after the stale `next` one.
    (tmp_path / "b").mkdir()
    db2 = _db(tmp_path / "b")
    con = sqlite3.connect(db2)
    con.execute("INSERT INTO sofa_entity_events VALUES (?, 'next', 0, ?, ?)",
                (ENTITY, "2026-08-30T00:00:00+00:00", json.dumps(_page([upcoming]))))
    con.commit()
    con.close()
    _raw_insert(db2, 77, 0, _page([_football(1, T0)]), "2026-09-01T00:00:00+00:00")
    assert [p.event_id for p in calibrate_from_cache.load_cache(Path(db2))] == [1]


def test_backfill_targets_the_finished_indexed_copy(tmp_path: Path) -> None:
    db = _db(tmp_path)
    con = sqlite3.connect(db)
    con.execute("INSERT INTO sofa_entity_events VALUES (?, 'next', 0, ?, ?)",
                (ENTITY, "2026-08-30T00:00:00+00:00",
                 json.dumps(_page([_football(1, T0, status="notstarted")]))))
    con.commit()
    con.close()
    _index(db, ENTITY, [_football(1, T0)], "2026-09-01T00:00:00+00:00")
    finished = [e["id"] for events in _iter_listings(db) for e in events
                if e["status"]["type"] == "finished"]
    assert finished == [1]


# --- F6 -----------------------------------------------------------------------

def test_tennis_drops_a_page_result_whose_newer_copy_no_longer_parses(
        tmp_path: Path) -> None:
    db = _db(tmp_path)
    _raw_insert(db, ENTITY, 0, _page([_tennis(1, T0)]), "2026-09-01T00:00:00+00:00")
    assert [r.event_id for r in tennis_rating.load_history(db)] == [1]
    cancelled = dict(_tennis(1, T0), status={"type": "canceled", "code": 70})
    _index(db, ENTITY, [cancelled], "2026-09-02T00:00:00+00:00")
    assert tennis_rating.load_history(db) == []


@pytest.mark.parametrize("tournament", ["Liga", 5, ["x"], {"category": "Cat"},
                                        {"category": {"sport": "football"}}])
def test_event_sport_never_raises_and_the_page_is_saved(
        tmp_path: Path, tournament: Any) -> None:
    event = dict(_football(1, T0), tournament=tournament)
    assert event_sport(event) is None
    cache = _cache(tmp_path)
    cache.save_entity_events(ENTITY, "last", 0, _page([event]))
    assert cache.get_entity_events(ENTITY, "last", 0) is not None
    con = sqlite3.connect(cache.config.db_path)
    assert con.execute(f"SELECT sport FROM {LISTED_EVENT}").fetchall() == [(None,)]
    con.close()


# --- F3: the fill --------------------------------------------------------------

def test_a_page_a_new_code_writer_saved_is_not_left_to_fill(tmp_path: Path) -> None:
    cache = _cache(tmp_path)
    db = cache.config.db_path
    _raw_insert(db, ENTITY, 1, _page([_football(1, T0)]), "2026-09-01T00:00:00+00:00")
    assert fill_script.fill(db, batch=10, max_minutes=None,
                            pause_ms=0)["remaining_unindexed"] == 0
    # After the fill: one page by new code (indexed itself), one by old code.
    cache.save_entity_events(ENTITY, "last", 0, _page([_football(2, T0 + DAY)]))
    reader = fill_script.read_only(db)
    cursor = fill_script.read_cursor(reader)
    assert fill_script.remaining_pages(reader, cursor) == 1
    assert fill_script.remaining_unindexed(reader, cursor) == 0
    reader.close()
    _raw_insert(db, 77, 0, _page([_football(3, T0)]), "2026-09-20T00:00:00+00:00")
    reader = fill_script.read_only(db)
    assert fill_script.remaining_unindexed(reader, cursor) == 1
    assert fill_script.remaining_unindexed(reader, cursor, limit=1) is None
    reader.close()


def test_re_indexing_an_indexed_page_writes_nothing(tmp_path: Path) -> None:
    cache = _cache(tmp_path)
    cache.save_entity_events(ENTITY, "last", 0, _page([_football(1, T0)]))
    con = sqlite3.connect(cache.config.db_path)
    stamp = con.execute(f"SELECT fetched_at FROM {LISTED_EVENT}").fetchone()[0]
    before = con.total_changes
    index_page(con, ENTITY, "last", stamp, _page([_football(1, T0)]))
    assert con.total_changes == before
    con.close()


def test_the_wal_guard_stops_the_fill_cleanly_and_it_resumes(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = _db(tmp_path)
    for p in range(6):
        _raw_insert(db, ENTITY, p, _page([_football(p + 1, T0 + p * DAY)]),
                    f"2026-09-0{p + 1}T00:00:00+00:00")
    sizes = iter([(10.0, 50.0, 0), (900.0, 950.0, 1), (900.0, 950.0, 1),
                  (900.0, 950.0, 1)])
    monkeypatch.setattr(fill_script, "wal_mb", lambda conn, path: next(sizes))
    slept: list[float] = []
    result = fill_script.fill(db, batch=1, max_minutes=None, pause_ms=300,
                              checkpoint_every=2, max_wal_mb=256,
                              wal_wait_s=10, sleep=slept.append)
    assert result["stopped"] == "wal_over_limit"
    assert result["pages"] == 4 and result["remaining_unindexed"] == 2
    assert result["wal_live_mb"] == 900.0
    assert slept.count(0.3) == 3 and slept.count(fill_script.WAL_POLL_S) == 2
    monkeypatch.setattr(fill_script, "wal_mb", lambda conn, path: (0.0, 0.0, 0))
    rest = fill_script.fill(db, batch=1, max_minutes=None, pause_ms=0)
    assert rest["pages"] == 2 and rest["stopped"] is None
    assert rest["remaining_unindexed"] == 0
    con = sqlite3.connect(db)
    assert con.execute(f"SELECT COUNT(*) FROM {LISTING_EVENT}").fetchone()[0] == 6
    con.close()


def test_the_real_wal_reading_runs_on_a_wal_file(tmp_path: Path) -> None:
    db = _db(tmp_path)
    con = sqlite3.connect(db)
    live, on_disk, busy = fill_script.wal_mb(con, db)
    con.close()
    assert live >= 0 and on_disk >= 0 and busy in (0, 1)


def test_the_cli_refuses_a_pause_that_starves_writers(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = _db(tmp_path)
    monkeypatch.setattr(sys, "argv", ["x", "--db", db, "--pause-ms", "50"])
    with pytest.raises(SystemExit) as exc:
        fill_script.main()
    assert exc.value.code == 2
    monkeypatch.setattr(sys, "argv", ["x", "--db", db, "--pause-ms", "300"])
    assert fill_script.main() == 0  # nothing to index: done
