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


def test_the_seed_advances_to_a_completed_runs_start_and_never_back(tmp_path):
    """2026-10-22: every seed sat at 2026-09-30, so entities first cached
    since were never queued (football 0 -> 2,598 with the seed at now)."""
    from scripts.sofa.backfill_listings import (
        advance_seed,
        recorded_seed,
        seed_cut,
    )

    path = tmp_path / "seed.json"
    path.write_text(json.dumps({"football": "2026-09-30T17:29:57+00:00",
                                "tennis": "2026-09-30T19:42:00+00:00"}))
    assert advance_seed(path, "football", "2026-10-22T08:00:00+00:00", "r1")
    assert recorded_seed(path, "football") == "2026-10-22T08:00:00+00:00"
    assert seed_cut(path, "football", "X") == "2026-10-22T08:00:00+00:00"
    # the old plain-string entries stay readable and untouched
    assert recorded_seed(path, "tennis") == "2026-09-30T19:42:00+00:00"
    assert not advance_seed(path, "football", "2026-10-01T00:00:00+00:00", "r0")
    assert recorded_seed(path, "football") == "2026-10-22T08:00:00+00:00"


def test_only_a_run_that_walked_its_whole_queue_completes_a_hop():
    from scripts.sofa.backfill_listings import hop_completed

    assert hop_completed(10, None, False, False)
    assert not hop_completed(10, None, False, True)   # --max-minutes
    assert not hop_completed(10, None, True, False)   # breaker
    assert not hop_completed(10, 10, False, False)    # --limit cut it
    assert hop_completed(3, 10, False, False)


def _main(monkeypatch, tmp_path, rows, argv, index=None):
    import types

    import scripts.sofa.backfill_listings as bl

    config = types.SimpleNamespace(run_id="t", db_path="unused",
                                   runs_dir=str(tmp_path), max_concurrency=1)
    monkeypatch.setattr(bl.SofaConfig, "from_env", staticmethod(lambda: config))
    monkeypatch.setattr(bl, "_rows", lambda db: rows)

    class NoIndex:
        available = False

        def __init__(self, db):
            pass

    monkeypatch.setattr(bl, "IndexCounter", index or NoIndex)
    seed = tmp_path / "seed.json"
    monkeypatch.setattr("sys.argv", ["backfill_listings.py", "--seed-file",
                                     str(seed), *argv])
    return bl.main(), seed


def test_an_empty_hop_moves_the_seed_to_now_and_a_dry_run_writes_nothing(
        monkeypatch, tmp_path, capsys):
    import time

    now = int(time.time())
    old = "2026-09-30T17:29:57+00:00"
    # entity 1 is done (no next page); its page fetched after the old seed
    # names a new opponent, 2, that the frozen seed never queued.
    rows = [(1, 0, _page([_event(11, now - DAY, 1, 2)], has_next=False),
             "2026-10-20T00:00:00+00:00")]
    rc, seed = _main(monkeypatch, tmp_path, rows, ["--dry-run"])
    assert rc == 0 and not seed.exists()
    capsys.readouterr()
    seed.write_text(json.dumps({"football": old}))
    rc, _ = _main(monkeypatch, tmp_path, rows, ["--dry-run"])
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert out["seed_advanced"] and out["entities_to_deepen"] == 1
    assert json.loads(seed.read_text()) == {"football": old}  # dry: untouched
    # an override is used as given, never advanced past
    _main(monkeypatch, tmp_path, rows, ["--dry-run", "--seed-before", old])
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert not out["seed_advanced"] and out["entities_to_deepen"] == 0
    # a real run with the hop walked records the new seed before deepening
    monkeypatch.setattr("scripts.sofa.backfill_listings.plan",
                        lambda *a: [])
    rc, _ = _main(monkeypatch, tmp_path, rows, [])
    assert rc == 0 and json.loads(seed.read_text())["football"]["seed_before"] > old


def test_the_empty_hop_check_counts_what_the_index_holds(
        monkeypatch, tmp_path, capsys):
    """2026-10-22 night: plan() was asked before the index counter was
    attached, so a hop whose gaps the index covers looked unwalked - the
    seed stayed at 09-30 and the counted plan (with the index) was empty:
    hockey listings 'DONE' at 0 where the moved seed queued 77."""
    import time

    import scripts.sofa.backfill_listings as bl

    now = int(time.time())
    old = "2026-09-30T17:29:57+00:00"
    rows = [(1, 0, _page([_event(11, now - DAY, 1, 2)], has_next=False),
             "2026-10-20T00:00:00+00:00")]

    class Index:
        available = True

        def __init__(self, db):
            pass

        def __call__(self, entity_id, after_ts, before_ts):
            return 10**6

    def counted_plan(states, *a):
        # a gap only the index covers: open without it, closed with it
        return [s for s in states.values() if s.indexed is None]

    monkeypatch.setattr(bl, "plan", counted_plan)
    (tmp_path / "seed.json").write_text(json.dumps({"football": old}))
    rc, seed = _main(monkeypatch, tmp_path, rows, [], index=Index)
    out = json.loads(capsys.readouterr().out.strip().splitlines()[0])
    assert rc == 0 and out["seed_advanced"]
    assert json.loads(seed.read_text())["football"]["seed_before"] > old
