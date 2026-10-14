"""sofa_event_extra and backfill_event_extra (2026-10-14): the shotmap /
point-by-point payloads are cached per (event, kind), an empty answer is a
fact, a live match is never stored, and the backfill asks each finished,
eligible, never-asked event once, newest first."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from bet.sofa.cache import SofaCache
from bet.sofa.config import SofaConfig
from bet.sofa.db import migrate
from bet.sofa.errors import CircuitOpenError
from scripts.sofa import backfill_event_extra as bx


@pytest.fixture
def cache(tmp_path: Path) -> SofaCache:
    db_path = str(tmp_path / "sofa.db")
    migrate(db_path)
    return SofaCache(SofaConfig(db_path=db_path, events_ttl_min=360))


def test_extra_round_trip_empty_and_kinds(cache: SofaCache) -> None:
    assert cache.get_event_extra(1, "shotmap") is None  # never asked
    cache.save_event_extra(1, "shotmap", {"shotmap": [{"id": 9}]}, "finished")
    cache.save_event_extra(1, "point_by_point", None, "finished")
    assert cache.get_event_extra(1, "shotmap") == {"shotmap": [{"id": 9}]}
    assert cache.get_event_extra(1, "point_by_point") == {}  # asked, empty
    with pytest.raises(ValueError):
        cache.save_event_extra(2, "shotmap", {}, "inprogress")
    with pytest.raises(ValueError):
        cache.get_event_extra(1, "graph")


def _ev(eid: int, ts: int, comp: int = 7, status: str = "finished") -> dict[str, Any]:
    return {"id": eid, "startTimestamp": ts, "status": status, "competition": comp}


def test_select_targets_skips_asked_and_friendlies_newest_first() -> None:
    friendly = next(iter(bx.FRIENDLY_COMPETITION_IDS))
    # 4's index copy is the pre-match one: its cached row says it finished
    events = [_ev(1, 100), _ev(2, 300), _ev(3, 200), _ev(4, 250, status="notstarted"),
              _ev(5, 260, comp=friendly)]
    assert [e["id"] for e in bx.select_targets(events, done={3})] == [2, 4, 1]


def test_candidate_events_reads_the_index_in_sql(tmp_path: Path) -> None:
    db = str(tmp_path / "sofa.db")
    migrate(db)
    import json
    import sqlite3
    conn = sqlite3.connect(db)
    ev = {"tournament": {"uniqueTournament": {"id": 17}},
          "status": {"type": "finished"}}
    conn.execute("INSERT INTO sofa_listed_event VALUES (1, 'football', 150, 'x', ?)",
                 (json.dumps(ev),))
    conn.execute("INSERT INTO sofa_listed_event VALUES (2, 'tennis', 150, 'x', ?)",
                 (json.dumps(ev),))
    conn.execute("INSERT INTO sofa_listing_event VALUES (50, 'last', 9, 160, 'x')")
    conn.execute("INSERT INTO sofa_listing_event VALUES (51, 'last', 8, 999, 'x')")
    conn.commit()
    conn.close()
    got = bx.candidate_events(db, {1, 2, 3, 8, 9}, 100, 200, "football", True)
    assert sorted((e["id"], e["competition"]) for e in got) == [(1, 17), (9, None)]
    got = bx.candidate_events(db, {1, 2, 9}, 100, 200, "tennis", False)
    assert [e["id"] for e in got] == [2]


def test_has_content() -> None:
    assert bx.has_content("shotmap", {"shotmap": [{}]})
    assert not bx.has_content("shotmap", {"shotmap": []})
    assert not bx.has_content("point_by_point", None)
    assert bx.has_content("point_by_point", {"pointByPoint": [{"set": 1}]})


class _Client:
    def __init__(self, answers: dict[int, Any]) -> None:
        self.answers = answers

    def get(self, eid: int) -> Any:
        a = self.answers[eid]
        if isinstance(a, Exception):
            raise a
        return a


def test_backfill_stores_hits_and_empties_and_stops_on_refusal(
    cache: SofaCache, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(bx, "breaker_tripped", lambda client: False)
    client = _Client({1: {"shotmap": [{"x": 1}]}, 2: {}, 3: CircuitOpenError("open")})
    run = bx.Backfill(client.get, cache, "shotmap", None, client)
    for eid in (1, 2, 3):
        run.fetch(_ev(eid, 100))
    assert cache.get_event_extra(1, "shotmap") == {"shotmap": [{"x": 1}]}
    assert cache.get_event_extra(2, "shotmap") == {}
    assert cache.get_event_extra(3, "shotmap") is None  # refused: never stored
    assert run.stop.is_set() and run.counts["hit"] == 1 and run.counts["empty"] == 1
