"""The cache replay holds only what it reads (2026-10-04).

load_cache kept every finished listed event of every sport whole - 1.41M
events, 25 GB - before it dropped all but football and tennis, and the
refit's replay thrashed a 48 GB machine for hours. It now keeps only the
replayed sports, without the display-only subtrees, and the replay of a
match must not change for it.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from bet.sofa.db import migrate
from scripts.sofa import calibrate_from_cache as cfc


def _team(tid: int, name: str) -> dict[str, Any]:
    return {"id": tid, "name": name, "gender": "M", "national": False,
            "country": {"alpha2": "PT", "name": "Portugal"},
            "teamColors": {"primary": "#fff"}, "subTeams": [],
            "fieldTranslations": {"nameTranslation": {"ar": "x"}}}


def _event(eid: int, sport: str = "football") -> dict[str, Any]:
    return {
        "id": eid, "status": {"type": "finished", "code": 100},
        "startTimestamp": 1_780_000_000 + eid,
        "homeTeam": _team(eid * 10 + 1, "A"), "awayTeam": _team(eid * 10 + 2, "B"),
        "homeScore": {"current": 2, "period1": 1, "period2": 1, "normaltime": 2},
        "awayScore": {"current": 1, "period1": 0, "period2": 1, "normaltime": 1},
        "roundInfo": {"round": 7},
        "tournament": {
            "name": "Liga Portugal 2", "id": 5,
            "fieldTranslations": {"nameTranslation": {"ar": "y"}},
            "uniqueTournament": {"id": 239, "name": "Liga Portugal 2",
                                 "fieldTranslations": {}},
            "category": {"name": "Portugal", "alpha2": "PT",
                         "country": {"alpha2": "PT"},
                         "sport": {"slug": sport}},
        },
    }


def _db(tmp_path: Path, name: str, events: list[dict[str, Any]]) -> Path:
    db = tmp_path / name
    migrate(str(db))
    with sqlite3.connect(db) as conn:
        conn.execute("INSERT INTO sofa_entity_events VALUES (1, 'last', 0, 'x', ?)",
                     (json.dumps({"events": events}),))
    return db


def test_slim_event_drops_display_subtrees_only() -> None:
    slim = cfc.slim_event(_event(1))
    assert "fieldTranslations" not in slim["tournament"]
    assert "fieldTranslations" not in slim["tournament"]["uniqueTournament"]
    assert set(slim["homeTeam"]) == {"id", "name", "gender", "national"}
    # A category's country is not a team's: kept.
    assert slim["tournament"]["category"]["country"] == {"alpha2": "PT"}
    full = _event(1)
    for key in ("homeScore", "awayScore", "status", "roundInfo", "startTimestamp"):
        assert slim[key] == full[key]


def test_replay_is_the_same_on_slim_events(tmp_path: Path) -> None:
    def bare(eid: int) -> dict[str, Any]:
        return cfc.slim_event(_event(eid))

    whole = cfc.load_cache(_db(tmp_path, "whole.db", [_event(1), _event(2)]))
    slim = cfc.load_cache(_db(tmp_path, "slim.db", [bare(1), bare(2)]))
    assert whole and whole == slim


def test_other_sports_are_never_held(tmp_path: Path, monkeypatch: Any) -> None:
    held: list[int] = []
    real = cfc.listed_events_by_id

    def spy(conn: Any, project: Any, **kw: Any) -> Any:
        out = real(conn, project, **kw)
        held.extend(out)
        return out

    monkeypatch.setattr(cfc, "listed_events_by_id", spy)
    db = _db(tmp_path, "mixed.db", [_event(1), _event(2, "ice-hockey")])
    assert [p.event_id for p in cfc.load_cache(db)] == [1]
    assert held == [1]


def test_a_same_named_match_of_another_sport_no_longer_drops_football(
    tmp_path: Path,
) -> None:
    # one_listing_per_match also keys on team names: a volleyball Vietnam -
    # Myanmar the same day collapsed a football one out of the replay
    # (39 football matches on the 2026-10-04 cache).
    football = _event(5)
    other = _event(3, "volleyball")
    other["startTimestamp"] = football["startTimestamp"]
    dropped: set[int] = set()
    played = cfc.load_cache(_db(tmp_path, "names.db", [football, other]), dropped)
    assert [p.event_id for p in played] == [5]
    assert dropped == set()
