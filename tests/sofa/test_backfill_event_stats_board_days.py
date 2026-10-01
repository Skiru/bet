"""backfill_event_stats --board-days: only the matches of sides we price.

The statistics backfill asked for every finished event any cached listing
names; --board-days N keeps only events one of whose sides is on the last N
boards (backfill_listings.board_entities), so the bridge time goes to the
teams/players whose samples the next sheet reads. Selected on a temp DB.
"""

from __future__ import annotations

import json
from pathlib import Path

from bet.sofa.db import get_connection, migrate
from scripts.sofa.backfill_event_stats import (
    _already_asked,
    _iter_listings,
    barren_competitions,
    select_targets,
)
from scripts.sofa.backfill_listings import board_entities

NOW = 1_800_000_000
DAY = 86400


def _event(eid: int, home: int, away: int, ts: int, sport: str = "football") -> dict:
    return {"id": eid, "startTimestamp": ts, "status": {"type": "finished"},
            "tournament": {"uniqueTournament": {"id": 17},
                           "category": {"sport": {"slug": sport}}},
            "homeTeam": {"id": home}, "awayTeam": {"id": away}}


def _board(runs: Path, day: str, pairs: list[tuple[int, int]]) -> None:
    d = runs / day
    d.mkdir(parents=True)
    fixtures = [{"sport": "football", "home_entity_id": h, "away_entity_id": a,
                 "competition_id": 17} for h, a in pairs]
    # another sport's sides on the same board are not football entities
    fixtures.append({"sport": "tennis", "home_entity_id": 50,
                     "away_entity_id": 51})
    (d / "02_fixtures.json").write_text(json.dumps(fixtures))


def _db(tmp_path: Path) -> str:
    db = str(tmp_path / "sofa.db")
    migrate(db)
    listings = {
        1: [_event(101, 1, 2, NOW - DAY), _event(102, 3, 1, NOW - 5 * DAY)],
        5: [_event(501, 5, 6, NOW - 2 * DAY)],  # only on an old board
        7: [_event(701, 7, 8, NOW - 3 * DAY)],  # never on a board
        9: [_event(901, 9, 1, NOW - 4 * DAY)],  # asked already
    }
    with get_connection(db) as conn:
        for eid, events in listings.items():
            conn.execute(
                "INSERT INTO sofa_entity_events VALUES (?, 'last', 0, ?, ?)",
                (eid, "2026-10-01T00:00:00+00:00",
                 json.dumps({"events": events, "hasNextPage": True})))
        conn.execute(
            "INSERT INTO sofa_event_stats (sofascore_event_id, fetched_at,"
            " statistics_json, incidents_json, status_type)"
            " VALUES (901, '2026-10-01', '{}', NULL, 'finished')")
    return db


def _select(db: str, entities: set[int] | None) -> list[int]:
    asked = _already_asked(db)
    barren = barren_competitions(_iter_listings(db), asked)
    return [e["id"] for e in select_targets(
        _iter_listings(db), {17}, set(asked), NOW - 30 * DAY, barren,
        sport="football", entities=entities)]


def test_board_days_keeps_only_matches_of_sides_on_the_last_boards(tmp_path):
    runs = tmp_path / "runs"
    _board(runs, "2026-09-20", [(5, 6)])
    _board(runs, "2026-09-30", [(1, 2)])
    _board(runs, "2026-10-01", [(3, 4)])
    db = _db(tmp_path)

    entities = board_entities(str(runs), "football", 2)
    assert entities == {1, 2, 3, 4}  # the 09-20 board is outside two boards
    # 101 and 102 have a board side; 501 only on the old board; 701 none;
    # 901 involves side 1 but its statistics were already asked.
    assert _select(db, entities) == [101, 102]
    # without --board-days the existing selection is unchanged
    assert _select(db, None) == [101, 501, 701, 102]


def test_board_days_zero_selects_nothing(tmp_path):
    runs = tmp_path / "runs"
    _board(runs, "2026-10-01", [(1, 2)])
    assert board_entities(str(runs), "football", 0) == set()
    assert _select(_db(tmp_path), set()) == []
