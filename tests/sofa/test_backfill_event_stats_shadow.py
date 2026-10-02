"""backfill_event_stats --sport hockey/basketball/volleyball [--with-lineups].

The measured sports have results only in the cache. The backfill asks
/statistics and, with --with-lineups, /lineups for their finished games, and
reads "already asked" per column: SHADOW_SETTLE writes lineups-only rows,
which the football rule ("the row exists") would read as a statistics 404.
--board-days reads the shadow boards (runs/sofa/shadow/<sport>/<date>/).
Selected on temp DBs; the fetches against fakes.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from bet.sofa.db import get_connection, migrate
from scripts.sofa.backfill_event_stats import (
    MAX_BARREN_MISSES,
    Backfill,
    RouteState,
    ShadowTarget,
    _iter_listings,
    _route_states,
    _sport_events,
    route_barren,
    select_shadow_targets,
    shadow_board_entities,
    shadow_board_sides,
)

NOW = 1_800_000_000
DAY = 86400
ROOT = Path(__file__).resolve().parents[2]


def _event(eid: int, home: int, away: int, ts: int,
           slug: str = "ice-hockey", comp: int = 17,
           status: str = "finished") -> dict[str, Any]:
    return {"id": eid, "startTimestamp": ts, "status": {"type": status},
            "tournament": {"uniqueTournament": {"id": comp},
                           "category": {"sport": {"slug": slug}}},
            "homeTeam": {"id": home}, "awayTeam": {"id": away}}


def _db(tmp_path: Path, listings: dict[int, list[dict[str, Any]]]) -> str:
    db = str(tmp_path / "sofa.db")
    migrate(db)
    with get_connection(db) as conn:
        for eid, events in listings.items():
            conn.execute(
                "INSERT INTO sofa_entity_events VALUES (?, 'last', 0, ?, ?)",
                (eid, "2026-10-01T00:00:00+00:00",
                 json.dumps({"events": events, "hasNextPage": True})))
    return db


def _row(db: str, eid: int, stats: str | None, lineups: str | None) -> None:
    with get_connection(db) as conn:
        conn.execute(
            "INSERT INTO sofa_event_stats (sofascore_event_id, fetched_at,"
            " statistics_json, incidents_json, status_type, lineups_json)"
            " VALUES (?, '2026-10-01', ?, NULL, 'finished', ?)",
            (eid, stats, lineups))


def _ids(targets: list[ShadowTarget]) -> list[tuple[int, bool, bool]]:
    return [(int(t.event["id"]), t.stats, t.lineups) for t in targets]


def test_a_lineups_only_row_still_wants_its_statistics(tmp_path: Path) -> None:
    db = _db(tmp_path, {1: [_event(101, 1, 2, NOW - 10 * DAY),
                            _event(102, 1, 3, NOW - 11 * DAY),
                            _event(103, 1, 4, NOW - 12 * DAY)]})
    _row(db, 101, None, json.dumps({"home": {"players": []}}))  # SHADOW_SETTLE
    _row(db, 102, "{}", None)  # asked, 404
    _row(db, 103, json.dumps({"statistics": [1]}), "{}")  # both asked
    states = _route_states(db)
    assert states[101] == RouteState(None, True)
    assert states[102] == RouteState(False, None)
    assert states[103] == RouteState(True, False)
    events = _sport_events(_iter_listings(db), "ice-hockey")
    got = select_shadow_targets(events, states, NOW - 30 * DAY, NOW, False)
    assert _ids(got) == [(101, True, False)]
    got = select_shadow_targets(events, states, NOW - 30 * DAY, NOW, True)
    assert _ids(got) == [(101, True, False), (102, False, True)]


def test_only_the_sport_finished_in_window_and_old_enough(tmp_path: Path) -> None:
    db = _db(tmp_path, {1: [
        _event(201, 1, 2, NOW - 5 * DAY),
        _event(202, 1, 2, NOW - 5 * DAY, slug="basketball"),
        _event(203, 1, 2, NOW - 5 * DAY, status="notstarted"),
        _event(204, 1, 2, NOW - 40 * DAY),  # before --days
        _event(205, 1, 2, NOW - DAY),  # younger than the provisional window
        _event(206, 1, 2, NOW - 6 * DAY),
    ], 2: [_event(206, 1, 2, NOW - 6 * DAY)]})  # listed twice, asked once
    events = _sport_events(_iter_listings(db), "ice-hockey")
    got = select_shadow_targets(
        events, _route_states(db), NOW - 30 * DAY, NOW - 3 * DAY, False)
    assert _ids(got) == [(201, True, False), (206, True, False)]


def test_friendlies_are_not_asked() -> None:
    friendly = _event(301, 1, 2, NOW - 5 * DAY)
    friendly["tournament"]["uniqueTournament"]["name"] = "Club Friendly Games"
    league = _event(302, 1, 2, NOW - 5 * DAY)
    league["tournament"]["uniqueTournament"]["name"] = "Extraliga"
    got = select_shadow_targets([friendly, league], {}, 0, NOW, True)
    assert _ids(got) == [(302, True, True)]


def test_barren_is_kept_per_route(tmp_path: Path) -> None:
    n = MAX_BARREN_MISSES
    events = [_event(1000 + i, 1, 2, NOW - (i + 5) * DAY) for i in range(n + 1)]
    db = _db(tmp_path, {1: events})
    # The league publishes statistics but never a box score.
    for i in range(n):
        _row(db, 1000 + i, json.dumps({"statistics": [1]}), "{}")
    states = _route_states(db)
    listed = _sport_events(_iter_listings(db), "ice-hockey")
    assert route_barren(listed, states, "stats") == set()
    assert route_barren(listed, states, "lineups") == {17}
    got = select_shadow_targets(
        listed, states, 0, NOW, True,
        route_barren(listed, states, "stats"),
        route_barren(listed, states, "lineups"))
    assert _ids(got) == [(1000 + n, True, False)]


def test_board_days_reads_the_shadow_boards(tmp_path: Path) -> None:
    db = _db(tmp_path, {})
    runs = tmp_path / "runs"
    with get_connection(db) as conn:
        conn.execute(
            "INSERT INTO sofa_event_detail VALUES (?, ?, ?, ?)",
            (555, "2026-10-01", "finished", json.dumps(
                {"event": {"homeTeam": {"id": 11}, "awayTeam": {"id": 12}}})))
        for key, sid, status in (("hc sparta praha", 21, "verified"),
                                 ("rytiri kladno", 22, "candidate")):
            conn.execute(
                "INSERT INTO sofa_entity (sport, query_key, sofascore_id,"
                " sofascore_name, entity_type, status) VALUES (?, ?, ?, ?,"
                " 'team', ?)", ("ice-hockey", key, sid, key, status))
    for day, team1, team2, eid in (("2026-09-20", "Old Club", "Older Club", 999),
                                   ("2026-09-30", "HC Sparta Praha",
                                    "Rytiri Kladno", 555)):
        d = runs / "shadow" / "hockey" / day
        d.mkdir(parents=True)
        (d / "snapshots.jsonl").write_text(json.dumps(
            {"team1": team1, "team2": team2, "lines": []}) + "\nnot json\n")
        (d / "settled.json").write_text(json.dumps(
            {"date": day, "events": {"x": {"sofascore_event_id": eid},
                                     "y": {"state": "NOT_ON_SOFASCORE"}}}))
    names, events = shadow_board_sides(str(runs), "hockey", 1)
    assert events == {555}
    assert "hc sparta praha" in names and "old club" not in names
    # The settled game's sides, and the one verified name; a candidate is not.
    assert shadow_board_entities(str(runs), "hockey", 1, db) == {11, 12, 21}
    assert shadow_board_entities(str(runs), "basketball", 7, db) == set()
    assert shadow_board_entities(str(runs), "hockey", 0, db) == set()


class _Client:
    def __init__(self, stats: dict[int, Any], lineups: dict[int, Any],
                 fail_lineups: set[int] | None = None,
                 circuit: set[int] | None = None) -> None:
        self.stats, self.lineups = stats, lineups
        self.fail_lineups = fail_lineups or set()
        self.circuit = circuit or set()
        self.asked: list[tuple[str, int]] = []

    def event_statistics(self, event_id: int) -> Any:
        from bet.sofa.errors import CircuitOpenError

        self.asked.append(("stats", event_id))
        if event_id in self.circuit:
            raise CircuitOpenError("open")
        return self.stats.get(event_id)

    def event_lineups(self, event_id: int) -> Any:
        from bet.sofa.errors import ProviderError

        self.asked.append(("lineups", event_id))
        if event_id in self.fail_lineups:
            raise ProviderError("HTTP 503")
        return self.lineups.get(event_id)

    def event_incidents(self, event_id: int) -> Any:
        raise AssertionError("the measured sports ask no incidents")


class _Cache:
    def __init__(self) -> None:
        self.stats: dict[int, Any] = {}
        self.lineups: dict[int, Any] = {}

    def save_event_stats(self, event_id: int, stats: Any, incidents: Any,
                         status: str) -> None:
        assert incidents is None and status == "finished"
        self.stats[event_id] = stats

    def save_event_lineups(self, event_id: int, lineups: Any, status: str) -> None:
        assert status == "finished"
        self.lineups[event_id] = lineups


def _t(eid: int, stats: bool = True, lineups: bool = True,
       comp: int = 17) -> ShadowTarget:
    return ShadowTarget(_event(eid, 1, 2, NOW, comp=comp), stats, lineups)


def test_a_statistics_404_is_saved_as_empty_not_null_and_routes_apart() -> None:
    client = _Client({1: {"statistics": [1]}}, {2: {"home": {}}}, fail_lineups={1})
    cache = _Cache()
    runner = Backfill(client, cache, sport="hockey")
    runner.fetch_shadow(_t(1))
    runner.fetch_shadow(_t(2))
    runner.fetch_shadow(_t(3, stats=False))
    assert cache.stats == {1: {"statistics": [1]}, 2: {}}
    # The /lineups error lost nothing of /statistics, and wrote no lineups.
    assert cache.lineups == {2: {"home": {}}, 3: None}
    assert ("stats", 3) not in client.asked
    assert runner.counts == {"done": 3, "stats": 1, "no_stats": 1, "errors": 1,
                             "skipped_barren": 0, "lineups": 1, "no_lineups": 1}


def test_an_open_circuit_stops_the_shadow_backfill() -> None:
    client, cache = _Client({}, {}, circuit={1}), _Cache()
    runner = Backfill(client, cache, sport="basketball")
    runner.fetch_shadow(_t(1))
    runner.fetch_shadow(_t(2))
    assert runner.stop.is_set()
    assert client.asked == [("stats", 1)]
    assert cache.stats == {} and cache.lineups == {}


def test_a_route_barren_at_run_time_is_given_up_for_that_route_only() -> None:
    n = MAX_BARREN_MISSES
    client = _Client({i: {"statistics": [1]} for i in range(n + 2)}, {})
    runner = Backfill(client, _Cache(), sport="volleyball")
    for i in range(n):
        runner.fetch_shadow(_t(i))
    runner.fetch_shadow(_t(n))
    runner.fetch_shadow(_t(n + 1, stats=False))
    assert ("lineups", n) not in client.asked
    assert ("stats", n) in client.asked
    assert runner.counts["skipped_barren"] == 1


def test_with_lineups_is_refused_for_football() -> None:
    proc = subprocess.run(
        [sys.executable, "scripts/sofa/backfill_event_stats.py",
         "--sport", "football", "--with-lineups", "--dry-run"],
        cwd=ROOT, capture_output=True, text=True,
        env={"PYTHONPATH": "src:.", "PATH": "/usr/bin:/bin"})
    assert proc.returncode == 2
    assert "--with-lineups is for" in proc.stderr


def test_football_backfill_counts_are_unchanged() -> None:
    runner = Backfill(_Client({}, {}), _Cache())
    assert runner.counts == {"done": 0, "stats": 0, "no_stats": 0, "errors": 0,
                             "skipped_barren": 0}
