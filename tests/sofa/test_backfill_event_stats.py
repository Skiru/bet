"""select_targets: which cached listing events the statistics backfill asks for."""

from __future__ import annotations

from typing import Any

from scripts.sofa.backfill_event_stats import select_targets


def _event(
    event_id: int,
    ts: int,
    comp: int = 17,
    status: str = "finished",
    sport: str = "football",
    **extra: Any,
) -> dict[str, Any]:
    return {
        "id": event_id,
        "startTimestamp": ts,
        "status": {"type": status},
        "tournament": {
            "uniqueTournament": {"id": comp},
            "category": {"sport": {"slug": sport}},
        },
        **extra,
    }


def test_only_finished_football_in_board_competitions_since_cutoff() -> None:
    listings = [[
        _event(1, 2000),
        _event(2, 2000, status="notstarted"),
        _event(3, 2000, sport="tennis"),
        _event(4, 2000, comp=999),
        _event(5, 500),
    ]]
    got = select_targets(listings, {17}, set(), since_ts=1000)
    assert [e["id"] for e in got] == [1]


def test_already_asked_events_are_never_asked_again() -> None:
    # An asked-and-404 row is in sofa_event_stats too; asking again would
    # spend bridge time on an answer we already hold.
    got = select_targets([[_event(1, 2000), _event(2, 2000)]], {17}, {1}, 0)
    assert [e["id"] for e in got] == [2]


def test_newest_first_and_deduplicated_across_listings() -> None:
    # The same match sits in both teams' listings.
    listings = [[_event(1, 1000), _event(2, 3000)], [_event(2, 3000), _event(3, 2000)]]
    got = select_targets(listings, {17}, set(), 0)
    assert [e["id"] for e in got] == [2, 3, 1]


def test_tournament_known_to_publish_nothing_is_skipped(monkeypatch: Any) -> None:
    import scripts.sofa.backfill_event_stats as mod

    monkeypatch.setattr(mod, "statistics_are_hopeless", lambda e: e["id"] == 1)
    got = select_targets([[_event(1, 2000), _event(2, 2000)]], {17}, set(), 0)
    assert [e["id"] for e in got] == [2]


class _Client:
    def __init__(self, stats: dict[int, Any], fail: set[int] | None = None,
                 circuit: set[int] | None = None) -> None:
        self.stats, self.fail, self.circuit = stats, fail or set(), circuit or set()
        self.asked: list[int] = []

    def event_statistics(self, event_id: int) -> Any:
        from bet.sofa.errors import CircuitOpenError, ProviderError

        self.asked.append(event_id)
        if event_id in self.circuit:
            raise CircuitOpenError("open")
        if event_id in self.fail:
            raise ProviderError("HTTP 503")
        return self.stats.get(event_id)

    def event_incidents(self, event_id: int) -> Any:
        return {"incidents": []}


class _Cache:
    def __init__(self) -> None:
        self.saved: dict[int, Any] = {}

    def save_event_stats(self, event_id: int, stats: Any, incidents: Any,
                         status: str) -> None:
        self.saved[event_id] = (stats, incidents, status)


def test_a_404_is_saved_as_asked_and_an_error_is_not_saved() -> None:
    from scripts.sofa.backfill_event_stats import Backfill

    client, cache = _Client({1: {"statistics": []}}, fail={3}), _Cache()
    runner = Backfill(client, cache)
    for eid in (1, 2, 3):
        runner.fetch_one(_event(eid, 2000))
    assert cache.saved[1][0] == {"statistics": []}
    assert cache.saved[2][0] is None  # asked, 404
    assert 3 not in cache.saved  # an error is not an answer
    assert runner.counts["errors"] == 1 and runner.counts["no_stats"] == 1


def test_an_open_circuit_stops_every_later_request() -> None:
    from scripts.sofa.backfill_event_stats import Backfill

    client, cache = _Client({}, circuit={2}), _Cache()
    runner = Backfill(client, cache)
    for eid in (1, 2, 3, 4):
        runner.fetch_one(_event(eid, 2000))
    assert runner.stop.is_set()
    assert client.asked == [1, 2]


def test_a_barren_competition_is_given_up_but_one_success_keeps_it() -> None:
    from scripts.sofa.backfill_event_stats import MAX_BARREN_MISSES, Backfill

    client, cache = _Client({500: {"statistics": []}}), _Cache()
    runner = Backfill(client, cache)
    for eid in range(MAX_BARREN_MISSES + 5):
        runner.fetch_one(_event(eid, 2000, comp=99))
    assert len(client.asked) == MAX_BARREN_MISSES
    assert runner.counts["skipped_barren"] == 5
    runner.fetch_one(_event(500, 2000, comp=17))
    for eid in range(600, 600 + MAX_BARREN_MISSES + 5):
        runner.fetch_one(_event(eid, 2000, comp=17))
    assert runner.counts["skipped_barren"] == 5  # comp 17 had a success
