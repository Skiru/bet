"""backfill_football_lineups: scope from the day artifacts, target selection,
and the order of writes for an event the cache has never seen."""

import json
from pathlib import Path
from typing import Any

from bet.sofa.samples import FRIENDLY_COMPETITION_IDS
from scripts.sofa import backfill_football_lineups as bl

NOW = 1_800_000_000
DAY = 86400


def ev(eid: int, days_ago: float, comp: int, home: int = 1, away: int = 2,
       **extra: Any) -> dict[str, Any]:
    return {"id": eid, "startTimestamp": NOW - int(days_ago * DAY),
            "status": {"type": "finished"},
            "tournament": {"uniqueTournament": {"id": comp},
                           "category": {"sport": {"slug": "football"}}},
            "homeTeam": {"id": home}, "awayTeam": {"id": away}, **extra}


def test_scope_is_the_fixtures_whose_offer_carried_a_player_rung(
    tmp_path: Path,
) -> None:
    day = tmp_path / "2026-10-01"
    day.mkdir()
    (day / "04_offer.json").write_text(json.dumps([
        {"sofascore_event_id": 1, "rungs": [{"market": "player_shots_for"}]},
        {"sofascore_event_id": 2, "rungs": [{"market": "corners_total"}]},
    ]))
    friendly = next(iter(FRIENDLY_COMPETITION_IDS))
    (day / "02_fixtures.json").write_text(json.dumps([
        {"sofascore_event_id": 1, "sport": "football", "competition_id": 54,
         "home_entity_id": 10, "away_entity_id": 11},
        {"sofascore_event_id": 2, "sport": "football", "competition_id": 17,
         "home_entity_id": 20, "away_entity_id": 21},
    ]))
    comps, teams = bl.player_market_scope(str(tmp_path))
    assert comps == {54} and teams == {10, 11}
    assert friendly not in comps


def test_targets_are_in_scope_unasked_and_newest_first() -> None:
    friendly = next(iter(FRIENDLY_COMPETITION_IDS))
    events = [
        ev(1, 10, 54),                      # in a player-market league
        ev(2, 5, 999, home=10),             # a player-market team elsewhere
        ev(3, 3, 999),                      # neither
        ev(4, 2, friendly, home=10),        # friendly: out, as in SAMPLES
        ev(5, 1, 54, hasEventPlayerStatistics=False),  # Sofascore says none
        ev(6, 4, 54),                       # lineups already asked
        ev(7, 400, 54),                     # outside the window
        ev(8, 6, 54),                       # no stats row at all
    ]
    states = {1: (True, False), 2: (True, False), 6: (True, True)}
    got = bl.select_targets(events, states, {54}, {10}, NOW - 365 * DAY, NOW,
                            barren=set())
    assert [t.event["id"] for t in got] == [2, 8, 1]
    assert {t.event["id"]: t.needs_stats for t in got} == {2: False, 8: True, 1: False}


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def event_statistics(self, eid: int) -> dict[str, Any]:
        self.calls.append(f"stats {eid}")
        return {"statistics": [1]}

    def event_incidents(self, eid: int) -> dict[str, Any]:
        self.calls.append(f"incidents {eid}")
        return {"incidents": []}

    def event_lineups(self, eid: int) -> dict[str, Any] | None:
        self.calls.append(f"lineups {eid}")
        return {"home": {"players": []}} if eid != 9 else None


class FakeCache:
    def __init__(self) -> None:
        self.writes: list[tuple[str, int, Any]] = []

    def save_event_stats(self, eid: int, stats: Any, incidents: Any, st: str) -> None:
        self.writes.append(("stats", eid, stats))

    def save_event_lineups(self, eid: int, lineups: Any, st: str) -> None:
        self.writes.append(("lineups", eid, lineups))


def test_an_unseen_event_gets_its_team_statistics_before_its_lineups() -> None:
    client, cache = FakeClient(), FakeCache()
    runner = bl.Backfill(client, cache, deadline=None)
    runner.fetch(bl.Target(ev(8, 1, 54), needs_stats=True))
    runner.fetch(bl.Target(ev(1, 1, 54), needs_stats=False))
    runner.fetch(bl.Target(ev(9, 1, 54), needs_stats=False))
    assert client.calls == ["stats 8", "incidents 8", "lineups 8",
                            "lineups 1", "lineups 9"]
    assert [w[:2] for w in cache.writes] == [
        ("stats", 8), ("lineups", 8), ("lineups", 1), ("lineups", 9)]
    assert cache.writes[-1][2] is None  # an empty answer is recorded as asked
    assert runner.counts["lineups"] == 2 and runner.counts["no_lineups"] == 1
