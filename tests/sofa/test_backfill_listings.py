"""scripts/sofa/backfill_listings.py - deepen cached listings, resumably.

FK Aktobe's cached history began five months before 2026-09-30 because
SAMPLES asks only for the pages it needs; the league-strength term then had 8
cross-league matches for the Kazakh women's league where 10 were needed. These
tests pin the three things a backfill of that history must get right: every
opponent is an entity to deepen, an entity that already reaches the window is
never asked again, and a page walk stops where the history does.
"""

import json

from bet.sofa.errors import CircuitOpenError
from scripts.sofa.backfill_listings import Deepen, EntityState, plan, scan

DAY = 86400
NOW = 1_800_000_000


def _event(eid, ts, home, away, sport="football"):
    return {"id": eid, "startTimestamp": ts,
            "tournament": {"category": {"sport": {"slug": sport}}},
            "homeTeam": {"id": home}, "awayTeam": {"id": away}}


def _page(events, has_next=True):
    return json.dumps({"events": events, "hasNextPage": has_next})


def test_every_opponent_is_an_entity_and_other_sports_are_ignored():
    rows = [
        (1, 0, _page([_event(10, NOW - DAY, 1, 2), _event(11, NOW - 2 * DAY, 3, 1)])),
        (7, 0, _page([_event(12, NOW - DAY, 7, 8, sport="tennis")])),
    ]
    states = scan(rows, "football", NOW - 400 * DAY)
    assert set(states) == {1, 2, 3}
    assert states[1].deepest_page == 0 and states[2].deepest_page == -1


def test_an_entity_that_reaches_the_window_is_not_asked_again():
    since = NOW - 730 * DAY
    rows = [
        (1, 0, _page([_event(10, NOW - DAY, 1, 2)])),
        (1, 1, _page([_event(11, since - DAY, 1, 2)])),  # already past the window
        (2, 0, _page([_event(10, NOW - DAY, 1, 2)], has_next=False)),  # no more
        (3, 0, _page([_event(13, NOW - DAY, 3, 4)])),  # short
    ]
    states = scan(rows, "football", NOW - 400 * DAY)
    todo = plan(states, board={4}, since_ts=since, recent_since=NOW - 400 * DAY)
    ids = [s.entity_id for s in todo]
    assert 1 not in ids and 2 not in ids
    assert ids[0] == 4  # the board comes first
    assert set(ids) == {3, 4}


class _Client:
    def __init__(self, pages):
        self.pages, self.asked = pages, []

    def entity_events(self, entity_id, kind, page):
        self.asked.append(page)
        value = self.pages.get(page)
        if isinstance(value, Exception):
            raise value
        return value


class _Cache:
    def __init__(self):
        self.saved, self.misses = [], []

    def get_listing_miss(self, entity_id, kind, page):
        return False

    def save_listing_miss(self, entity_id, kind, page):
        self.misses.append(page)

    def save_entity_events(self, entity_id, kind, page, payload):
        self.saved.append(page)


def test_the_walk_starts_after_the_deepest_page_and_stops_at_the_window():
    since = NOW - 730 * DAY
    client = _Client({
        2: {"events": [_event(1, NOW - 300 * DAY, 1, 2)], "hasNextPage": True},
        3: {"events": [_event(2, since - DAY, 1, 2)], "hasNextPage": True},
        4: {"events": [_event(3, since - 90 * DAY, 1, 2)], "hasNextPage": True},
    })
    cache = _Cache()
    Deepen(client, cache, since, None).run_one(EntityState(1, deepest_page=1))
    assert client.asked == [2, 3] and cache.saved == [2, 3]


def test_a_404_is_recorded_and_a_refusal_stops_everyone():
    cache = _Cache()
    Deepen(_Client({0: None}), cache, NOW - 730 * DAY, None).run_one(EntityState(1))
    assert cache.misses == [0]
    runner = Deepen(_Client({0: CircuitOpenError("403")}), _Cache(),
                    NOW - 730 * DAY, None)
    runner.run_one(EntityState(1))
    assert runner.stop.is_set()
    runner.run_one(EntityState(2))  # nobody asks once the breaker opened
    assert runner.counts["pages"] == 0


def test_a_locked_database_is_counted_not_fatal(monkeypatch):
    import sqlite3

    import scripts.sofa.backfill_listings as bl

    monkeypatch.setattr(bl, "DB_RETRY_SLEEP_S", 0.0)

    class Locked(_Cache):
        def save_entity_events(self, *a):
            raise sqlite3.OperationalError("database is locked")

    client = _Client({0: {"events": [_event(1, NOW, 1, 2)], "hasNextPage": True}})
    runner = Deepen(client, Locked(), NOW - 730 * DAY, None)
    runner.run_one(EntityState(1))
    assert runner.counts["db_locked"] == 1 and not runner.stop.is_set()


def test_opponents_come_only_from_pages_cached_before_the_seed():
    rows = [
        (1, 0, _page([_event(10, NOW - DAY, 1, 2)]), "2026-09-30T10:00:00"),
        # a page the backfill fetched later names a new opponent, 99
        (2, 0, _page([_event(11, NOW - DAY, 2, 99)]), "2026-09-30T18:00:00"),
    ]
    states = scan(rows, "football", NOW - 400 * DAY, "2026-09-30T17:29:00")
    assert set(states) == {1, 2}
    assert states[2].deepest_page == 0  # its own page still counts


def test_the_seed_time_is_recorded_once_and_reused(tmp_path):
    from scripts.sofa.backfill_listings import seed_cut

    path = tmp_path / "seed.json"
    assert seed_cut(path, "football", "T1") == "T1"
    assert seed_cut(path, "football", "T2") == "T1"
    assert seed_cut(path, "tennis", "T3") == "T3"
