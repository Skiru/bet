"""The measured sports' history is brought up to date (bet.sofa.sport_history).

2026-10-12: SPORT_IDENTITY asks the teams' listings before the game, so a game
entered the cache `notstarted` (or not at all) and its result never did - of
the settled Superbet games of 10-07..10-11 only 0-30% were in the history the
score model and the line evidence read. refresh_sport_history.py asks
`/event/{id}` for every game that should have ended and indexes the answer.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from bet.sofa import sport_history as sh
from bet.sofa.cache import SofaCache
from bet.sofa.config import SofaConfig
from bet.sofa.db import migrate
from bet.sofa.score_model import load_history
from bet.sofa.shadow import SPORTS

T0 = 1_790_000_000
HOME, AWAY = 501, 502


def _game(eid: int, ts: int, status: str = "finished", home: int = HOME,
          away: int = AWAY) -> dict[str, Any]:
    done = status == "finished"
    return {
        "id": eid, "startTimestamp": ts,
        "status": {"type": status, "code": 100 if done else 0,
                   "description": "Ended" if done else "Not started"},
        "tournament": {"id": 9, "category": {"sport": {"slug": "basketball"}},
                       "uniqueTournament": {"id": 99}},
        "homeTeam": {"id": home, "name": "H"}, "awayTeam": {"id": away, "name": "A"},
        "homeScore": ({"current": 80, "period1": 20, "period2": 20, "period3": 20,
                       "period4": 20} if done else {}),
        "awayScore": ({"current": 70, "period1": 10, "period2": 20, "period3": 20,
                       "period4": 20} if done else {}),
    }


def _db(tmp_path: Path) -> str:
    db = str(tmp_path / "sofa.db")
    migrate(db)
    return db


def test_a_game_cached_before_its_start_is_asked_and_enters_the_history(
        tmp_path: Path) -> None:
    db = _db(tmp_path)
    cache = SofaCache(SofaConfig(db_path=db))
    # SPORT_IDENTITY's view: the game on the home team's `next` page.
    cache.save_entity_events(HOME, "next", 0,
                             {"events": [_game(1, T0, "notstarted")]})
    assert [g.event_id for g in load_history(db, SPORTS["basketball"])] == []
    con = sqlite3.connect(db)
    found = sh.candidates(con, ["basketball"], T0 - 86400, T0 + 86400)
    assert found.ids == {"basketball": {1}}
    asked: list[int] = []

    def fetch(eid: int) -> Any:
        asked.append(eid)
        return {"event": _game(eid, T0)}

    res = sh.refresh(con, found.ids["basketball"], fetch,
                     lambda: "2026-10-12T21:00:00+00:00")
    con.close()
    assert asked == [1] and res.finished == 1 and res.missing == 0
    hist = load_history(db, SPORTS["basketball"])
    assert [g.event_id for g in hist] == [1]
    # both teams list it as a `last` member (a sample reader finds it too)
    con = sqlite3.connect(db)
    members = sorted(r[0] for r in con.execute(
        "SELECT entity_id FROM sofa_listing_event WHERE event_id = 1"))
    assert members == [HOME, AWAY]
    # resumable: a finished game is not a candidate again
    again = sh.candidates(con, ["basketball"], T0 - 86400, T0 + 86400)
    assert again.ids == {"basketball": set()}
    assert again.already_finished == {"basketball": 1}


def test_games_outside_the_window_or_of_another_sport_are_not_asked(
        tmp_path: Path) -> None:
    db = _db(tmp_path)
    cache = SofaCache(SofaConfig(db_path=db))
    hockey = _game(3, T0, "notstarted")
    hockey["tournament"]["category"]["sport"]["slug"] = "ice-hockey"
    cache.save_entity_events(HOME, "next", 0, {"events": [
        _game(1, T0 - 30 * 86400, "notstarted"),   # too old
        _game(2, T0 + 5 * 86400, "notstarted"),    # not over yet
        hockey,
    ]})
    con = sqlite3.connect(db)
    found = sh.candidates(con, ["basketball"], T0 - 86400, T0 + 86400)
    assert found.ids == {"basketball": set()}


def test_a_pinned_id_absent_from_every_listing_is_asked(tmp_path: Path) -> None:
    db = _db(tmp_path)
    con = sqlite3.connect(db)
    found = sh.candidates(con, ["basketball"], T0 - 86400, T0 + 86400,
                          {"basketball": [42]})
    assert found.ids == {"basketball": {42}}


def test_pinned_ids_read_sport_fixtures(tmp_path: Path) -> None:
    day = tmp_path / "2026-10-10"
    day.mkdir()
    (day / "sport_fixtures.json").write_text(json.dumps({"fixtures": [
        {"sport": "basketball", "sofascore_event_id": 7, "status": "IDENTIFIED"},
        {"sport": "hockey", "sofascore_event_id": 8},
        {"sport": "basketball", "sofascore_event_id": None},
    ]}), encoding="utf-8")
    assert sh.pinned_ids(tmp_path, "basketball", ["2026-10-10", "2026-10-09"]) == {7}


def test_a_game_not_finished_is_stored_but_stays_out_of_the_history(
        tmp_path: Path) -> None:
    db = _db(tmp_path)
    con = sqlite3.connect(db)
    res = sh.refresh(con, [5], lambda eid: {"event": _game(eid, T0, "postponed")},
                     lambda: "2026-10-12T21:00:00+00:00")
    con.close()
    assert res.not_finished == 1
    assert load_history(db, SPORTS["basketball"]) == []


def test_an_unanswered_game_is_counted_and_a_refusal_stops_the_run(
        tmp_path: Path) -> None:
    db = _db(tmp_path)
    con = sqlite3.connect(db)

    def fetch(eid: int) -> Any:
        if eid == 2:
            raise RuntimeError("Circuit breaker is open")
        return None  # 404

    res = sh.refresh(con, [1, 2, 3], fetch, lambda: "x")
    assert res.asked == 1 and res.missing == 1
    assert res.stopped is not None and "breaker" in res.stopped


def test_a_payload_for_another_id_is_not_stored(tmp_path: Path) -> None:
    db = _db(tmp_path)
    con = sqlite3.connect(db)
    res = sh.refresh(con, [1], lambda eid: {"event": _game(99, T0)}, lambda: "x")
    con.close()
    assert res.missing == 1
    assert load_history(db, SPORTS["basketball"]) == []


def test_the_newer_fetch_replaces_the_pre_game_copy(tmp_path: Path) -> None:
    db = _db(tmp_path)
    cache = SofaCache(SofaConfig(db_path=db))
    # an older index copy of the same game, not finished
    cache.save_entity_events(HOME, "last", 0, {"events": [_game(1, T0, "notstarted")]})
    con = sqlite3.connect(db)
    sh.refresh(con, [1], lambda eid: {"event": _game(eid, T0)},
               lambda: "2099-01-01T00:00:00+00:00")
    con.close()
    assert [g.event_id for g in load_history(db, SPORTS["basketball"])] == [1]


def test_day_status_warns_when_yesterdays_games_are_not_in_the_history(
        tmp_path: Path) -> None:
    from scripts.sofa import day_status as ds

    db = _db(tmp_path)
    runs = tmp_path / "runs"
    day = runs / "2026-10-11"
    day.mkdir(parents=True)
    (day / "sport_fixtures.json").write_text(json.dumps({"fixtures": [
        {"sport": "basketball", "sofascore_event_id": 1},
        {"sport": "hockey", "sofascore_event_id": 2}]}), encoding="utf-8")
    check = ds.history_check(runs, "2026-10-12", db)
    assert check.status == ds.WARN and "0/2" in check.detail
    con = sqlite3.connect(db)
    sh.refresh(con, [1, 2], lambda eid: {"event": _game(eid, T0)}, lambda: "x")
    con.close()
    check = ds.history_check(runs, "2026-10-12", db)
    assert check.status == ds.OK and "2/2" in check.detail
    assert ds.history_check(runs, "2026-10-12", None).status == ds.NOT_CHECKED


def test_the_morning_evidence_refresh_brings_the_history_up_first() -> None:
    import importlib.util
    import sys

    path = Path(__file__).resolve().parents[2] / "scripts/sofa/refresh_line_evidence.py"
    spec = importlib.util.spec_from_file_location("rle_for_history", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["rle_for_history"] = mod
    spec.loader.exec_module(mod)
    cmd = mod.history_command()
    assert cmd[1] == "scripts/sofa/refresh_sport_history.py"
    assert "--dry-run" not in cmd
