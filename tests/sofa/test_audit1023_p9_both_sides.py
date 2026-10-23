"""Audit 2026-10-23 B9 / P9: a hockey / basketball game belongs to both teams'
lists (bet.sofa.sport_history.list_both_sides / listing_kinds / listed_rows,
epochs.PLAYER_BOTH_SIDES_LISTED_FROM_UTC).

A `last` page indexes its games under the page's owner only, so Vancouver @
Florida 16546356 (2026-10-15) sat in Florida's list (3687) and never in
Vancouver's (3692): the player model, which reads a team's own list, lost the
game for Vancouver's players.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bet.sofa import epochs
from bet.sofa import sport_history as sh
from bet.sofa.cache import SofaCache
from bet.sofa.config import SofaConfig
from bet.sofa.db import migrate
from bet.sofa.player_model import listed_games

FLORIDA, VANCOUVER = 3687, 3692
EVENT = 16546356
START = 1792105200  # 2026-10-15 23:00Z


def _game(eid: int = EVENT, ts: int = START, status: str = "finished",
          sport: str = "ice-hockey") -> dict[str, Any]:
    return {
        "id": eid, "startTimestamp": ts,
        "status": {"type": status, "description": "Ended"},
        "tournament": {"id": 234, "category": {"sport": {"slug": sport}},
                       "uniqueTournament": {"id": 234}},
        "homeTeam": {"id": FLORIDA, "name": "Florida Panthers"},
        "awayTeam": {"id": VANCOUVER, "name": "Vancouver Canucks"},
        "homeScore": {"current": 3, "period1": 1, "period2": 1, "period3": 1},
        "awayScore": {"current": 2, "period1": 0, "period2": 1, "period3": 1},
    }


def _db(tmp_path: Path, *games: dict[str, Any]) -> sqlite3.Connection:
    db = str(tmp_path / "sofa.db")
    migrate(db)
    # Florida's own `last` page: the index learns the game under 3687 only.
    SofaCache(SofaConfig(db_path=db)).save_entity_events(
        FLORIDA, "last", 0, {"events": list(games) or [_game()]})
    return sqlite3.connect(db)


ON = datetime(2026, 10, 24, 0, 0, 0, tzinfo=UTC)


def test_the_switch_by_day_and_build_clock() -> None:
    assert epochs.PLAYER_BOTH_SIDES_LISTED_FROM_UTC == ON
    assert sh.listing_kinds("2026-10-23", datetime(2026, 10, 23, 23, tzinfo=UTC)) \
        == ("last",)
    assert sh.listing_kinds("2026-10-24", ON) == ("last", sh.OPPONENT_KIND)
    # a 10-24 day built before the switch's clock reads the old lists
    assert sh.listing_kinds("2026-10-24", datetime(2026, 10, 23, 22, tzinfo=UTC)) \
        == ("last",)


def test_vancouver_at_florida_is_in_both_lists(tmp_path: Path) -> None:
    con = _db(tmp_path)
    before = START + 86400
    # Before the fix: Florida's list holds the game, Vancouver's does not.
    assert [r[0] for r in sh.listed_rows(con, FLORIDA, before, 10)] == [EVENT]
    assert sh.listed_rows(con, VANCOUVER, before, 10) == []
    missing = sh.missing_sides(con)
    assert [(m.event_id, m.team_id, m.start_ts) for m in missing] == [
        (EVENT, VANCOUVER, START)]
    assert sh.list_both_sides(con) == 1
    con.commit()
    on = sh.listing_kinds("2026-10-24", ON)
    assert [r[0] for r in sh.listed_rows(con, VANCOUVER, before, 10, on)] == [EVENT]
    assert [r[0] for r in sh.listed_rows(con, FLORIDA, before, 10, on)] == [EVENT]
    # Off: nobody reading `last` sees a new row.
    off = sh.listing_kinds("2026-10-23", ON)
    assert sh.listed_rows(con, VANCOUVER, before, 10, off) == []
    assert listed_games(con, VANCOUVER, before, None) == []
    # Idempotent: nothing is missing any more.
    assert sh.missing_sides(con) == []
    assert sh.list_both_sides(con) == 0


def test_a_later_own_page_does_not_double_the_game(tmp_path: Path) -> None:
    con = _db(tmp_path)
    sh.list_both_sides(con)
    con.commit()
    # Vancouver's own page arrives later: a `last` row beside the side row.
    con.execute("INSERT INTO sofa_listing_event VALUES (?, 'last', ?, ?, ?)",
                (VANCOUVER, EVENT, START, "2026-10-21T00:00:00+00:00"))
    rows = sh.listed_rows(con, VANCOUVER, START + 1, 10,
                          ("last", sh.OPPONENT_KIND))
    assert [r[0] for r in rows] == [EVENT]


def test_only_finished_games_of_the_player_sports(tmp_path: Path) -> None:
    con = _db(tmp_path, _game(1, START, "notstarted"),
              _game(2, START + 10, sport="volleyball"),
              _game(3, START + 20, sport="basketball"))
    assert [(m.event_id, m.team_id) for m in sh.missing_sides(con)] == [
        (3, VANCOUVER)]


def test_old_rows_are_the_old_query(tmp_path: Path) -> None:
    con = _db(tmp_path, *[_game(10 + i, START - i * 86400) for i in range(5)])
    old = [(e, t) for e, t in listed_games(con, FLORIDA, START + 1, None, 3)]
    new = [(e, t) for e, t, _ in sh.listed_rows(con, FLORIDA, START + 1, 12)][:3]
    assert old == new
