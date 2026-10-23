"""Coverage audit 2026-10-23, wiring of P9 (epochs.PLAYER_BOTH_SIDES_LISTED)
into the player model and of P3 (epochs.PLAYER_HISTORY_ANY_TEAM) into
SHADOW_SETTLE's settle-time number:

- player_model.listed_games / load_appearances read `kinds`
  (sport_history.listing_kinds); ("last",) is the old reader exactly;
- SHADOW (forecast_records) reads the kinds by the game's day and the
  snapshot clock, keys its cache on them and marks rows
  `player_lists_rule: "both_sides"`;
- settle_shadow._settle_time_model passes `kinds` and `any_team` by the
  game's day, marks `player_lists_rule` / `player_history_rule`; off: the
  old call (no new argument).

A game seen on the opponent's page only (`last_side`, Vancouver @ Florida
16546356) counts for the team's players only under P9."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from bet.sofa import epochs, player_model
from bet.sofa import sport_history as sh
from bet.sofa.player_model import listed_games, load_appearances
from scripts.sofa import settle_shadow
from tests.sofa.test_player_model import KO_TS, SOG, make_db
from tests.sofa.test_player_team_from_side import (
    NEW,
    OPP,
    TRADED,
    _forecast,
    traded_history,
)

DAY_ON = datetime(2026, 9, 28, 0, 0, tzinfo=UTC)  # the fixtures' game day
SIDE_ONLY = (200, 201, 202)  # NEW's games seen on OPP's page only


def _db(tmp_path: Path) -> Path:
    db = tmp_path / "db.sqlite"
    conn = make_db(db)
    traded_history(conn)
    # 200-202 lose NEW's own `last` row; the repair lists them as last_side.
    for eid in SIDE_ONLY:
        conn.execute("UPDATE sofa_listing_event SET kind = ? WHERE entity_id = ? "
                     "AND event_id = ?", (sh.OPPONENT_KIND, NEW, eid))
    conn.commit()
    conn.close()
    return db


def test_listed_games_and_appearances_read_the_kinds(tmp_path: Path) -> None:
    conn = sqlite3.connect(_db(tmp_path))
    before = KO_TS - 60
    both = ("last", sh.OPPONENT_KIND)
    old = {e for e, _ in listed_games(conn, NEW, before, None)}
    assert not old & set(SIDE_ONLY)
    assert {e for e, _ in listed_games(conn, NEW, before, None, kinds=("last",))} == old
    assert set(SIDE_ONLY) <= {e for e, _ in listed_games(conn, NEW, before, None,
                                                         kinds=both)}
    off = load_appearances(conn, "hockey", [NEW, OPP], before, None)
    on = load_appearances(conn, "hockey", [NEW, OPP], before, None, kinds=both)
    novak = {a.event_id for a in off if a.player_id == TRADED}
    assert not novak & set(SIDE_ONLY)
    assert set(SIDE_ONLY) <= {a.event_id for a in on if a.player_id == TRADED}
    # the peers are read through the same lists (any_team)
    memo: dict[Any, Any] = {}
    peers = load_appearances(conn, "hockey", [NEW], before, None,
                             team_from_side=True, any_team=True, memo=memo,
                             kinds=both)
    assert set(SIDE_ONLY) <= {a.event_id for a in peers if a.player_id == TRADED}


def test_shadow_reads_both_lists_by_the_day_and_the_snapshot_clock(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = _db(tmp_path)
    monkeypatch.setattr(epochs, "PLAYER_BOTH_SIDES_LISTED_FROM_UTC", None)
    off = _forecast(db)
    monkeypatch.setattr(epochs, "PLAYER_BOTH_SIDES_LISTED_FROM_UTC", DAY_ON)
    on = _forecast(db)
    assert all("player_lists_rule" not in r for r in off)
    assert {r["player_lists_rule"] for r in on} == {player_model.PLAYER_LISTS_RULE}
    assert {r["model_n"] for r in on} != {r["model_n"] for r in off}
    # the markers a pregame number carries to settled.json
    assert {"player_lists_rule", "player_history_rule", "name_rule"} <= set(
        player_model.MODEL_KEYS)
    # a snapshot clock before the moment keeps the old lists on that day
    monkeypatch.setattr(epochs, "PLAYER_BOTH_SIDES_LISTED_FROM_UTC",
                        datetime(2026, 9, 28, 17, 0, tzinfo=UTC))
    late = _forecast(db)
    assert [r["model_n"] for r in late] == [r["model_n"] for r in off]
    assert all("player_lists_rule" not in r for r in late)


def _settle(db: Path) -> dict[str, Any]:
    from bet.sofa.shadow import SPORTS

    rows = [{"superbet_event_id": "1", "market_id": SOG,
             "family": "player_shots_on_goal", "subject": "Novak, Jan",
             "line": 2.5, "side": "OVER", "odds": 1.9}]
    event = {"id": 999, "homeTeam": {"id": NEW}, "awayTeam": {"id": OPP}}
    [(_, fields)] = settle_shadow._settle_time_model(
        rows, SPORTS["hockey"], event, {"startTimestamp": KO_TS},
        datetime.fromtimestamp(KO_TS, UTC), str(db), {"jan novak": TRADED})
    return fields


def test_settle_reads_both_lists_by_the_games_day(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = _db(tmp_path)
    monkeypatch.setattr(epochs, "PLAYER_BOTH_SIDES_LISTED_FROM_UTC", None)
    off = _settle(db)
    monkeypatch.setattr(epochs, "PLAYER_BOTH_SIDES_LISTED_FROM_UTC", DAY_ON)
    on = _settle(db)
    assert "player_lists_rule" not in off
    assert on["player_lists_rule"] == player_model.PLAYER_LISTS_RULE
    assert on["model_n"] > off["model_n"]


def test_settle_passes_any_team_only_under_p3_and_the_side_rule(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = _db(tmp_path)
    seen: list[dict[str, Any]] = []
    real = player_model.load_appearances

    def spy(*a: Any, **kw: Any) -> Any:
        seen.append({k: v for k, v in kw.items() if k != "memo"})
        return real(*a, **kw)

    monkeypatch.setattr(player_model, "load_appearances", spy)
    monkeypatch.setattr(epochs, "PLAYER_BOTH_SIDES_LISTED_FROM_UTC", None)
    monkeypatch.setattr(epochs, "PLAYER_HISTORY_ANY_TEAM_FROM_UTC", DAY_ON)
    # the side rule off on the fixtures' day: no any_team (it needs it)
    first = _settle(db)
    monkeypatch.setattr(epochs, "PLAYER_TEAM_FROM_SIDE_FROM_UTC", DAY_ON)
    second = _settle(db)
    monkeypatch.setattr(epochs, "PLAYER_HISTORY_ANY_TEAM_FROM_UTC", None)
    third = _settle(db)
    assert seen == [{"team_from_side": False}, {"team_from_side": True,
                                                "any_team": True},
                    {"team_from_side": True}]
    assert "player_history_rule" not in first and "player_history_rule" not in third
    assert second["player_history_rule"] == player_model.PLAYER_HISTORY_RULE
