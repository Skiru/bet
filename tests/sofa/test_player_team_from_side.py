"""PLAYER_TEAM_FROM_SIDE (epochs.player_team_from_side): the player model
reads a past game's squad from the lineup side the team held in that game,
not from each entry's `teamId` - which is the player's team when the box was
downloaded. A traded player's old-team games against his new team landed in
the new team's sample (Carlson model_n 5 of 85 appearances, McTavish 6 of 88,
2026-10-13; docs/sofa/evidence/sport_player_props_2026-10-13.md). Offline."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from bet.sofa import epochs, player_model
from bet.sofa.player_model import appearances_from_lineups, load_appearances
from scripts.sofa import settle_shadow
from tests.sofa.test_player_model import (
    HOME_ID,
    KO_TS,
    SOG,
    _record,
    entry,
    make_db,
)
from tests.sofa.test_shadow import T1, T2

NEW, OPP, OLD = HOME_ID, 20, 30  # today: NEW (T1) vs OPP (T2); OLD traded him
TRADED = 1


def insert_game(
    conn: sqlite3.Connection,
    eid: int,
    ts: int,
    home: tuple[int, str],
    away: tuple[int, str],
    home_players: list[dict[str, Any]],
    away_players: list[dict[str, Any]],
) -> None:
    """A game whose lineup sides are given as they were played - the
    entries' teamId is whatever the box says."""
    lineups = {"home": {"players": home_players}, "away": {"players": away_players}}
    for team in (home[0], away[0]):
        conn.execute(
            "INSERT INTO sofa_listing_event VALUES (?, 'last', ?, ?, 'x')",
            (team, eid, ts),
        )
    conn.execute(
        "INSERT INTO sofa_event_stats VALUES (?, 'x', NULL, NULL, 'finished', ?)",
        (eid, json.dumps(lineups)),
    )
    event = {
        "id": eid,
        "startTimestamp": ts,
        "homeTeam": {"id": home[0], "name": home[1]},
        "awayTeam": {"id": away[0], "name": away[1]},
        "tournament": {"name": "Extraliga"},
    }
    conn.execute(
        "INSERT INTO sofa_listed_event VALUES (?, 'ice-hockey', ?, 'x', ?)",
        (eid, ts, json.dumps(event)),
    )


def stats(shots: int) -> dict[str, Any]:
    return {"secondsPlayed": 1200, "shots": shots, "plusMinus": 0}


def traded_history(conn: sqlite3.Connection) -> None:
    """Jan Novak (id 1) played games 100-102 for OLD against NEW (home side,
    OLD's) and 200-205 for NEW. Every box was downloaded after the trade, so
    every entry of his carries NEW's teamId."""
    for i in range(3):
        insert_game(
            conn,
            100 + i,
            KO_TS - (30 + i) * 86400,
            (OLD, "Old Club"),
            (NEW, T1),
            [entry(NEW, TRADED, "Jan Novak", stats(9)),
             entry(OLD, 5, "Ota Mlady", stats(1))],
            [entry(NEW, 2, "Petr Svoboda", stats(3))],
        )
    for i in range(6):
        insert_game(
            conn,
            200 + i,
            KO_TS - (i + 1) * 2 * 86400,
            (NEW, T1),
            (OPP, T2),
            [entry(NEW, TRADED, "Jan Novak", stats(2)),
             entry(NEW, 2, "Petr Svoboda", stats(3))],
            [entry(OPP, 3, "Karel Dvorak", stats(1))],
        )
    conn.commit()


def test_the_lineup_side_is_the_squad_and_teamid_is_not_read() -> None:
    lineups = {
        "home": {"players": [entry(NEW, TRADED, "Jan Novak", stats(9)),
                             entry(OLD, 5, "Ota Mlady", stats(1))]},
        "away": {"players": [entry(NEW, 2, "Petr Svoboda", stats(3))]},
    }
    # Off (no side): by teamId - the traded player is NEW's in OLD's game.
    off_new = appearances_from_lineups("hockey", lineups, 1, 0, NEW)
    off_old = appearances_from_lineups("hockey", lineups, 1, 0, OLD)
    assert {a.player_id for a in off_new} == {TRADED, 2}
    assert {a.player_id for a in off_old} == {5}
    # On: the side the team held.
    on_old = appearances_from_lineups("hockey", lineups, 1, 0, OLD, "home")
    on_new = appearances_from_lineups("hockey", lineups, 1, 0, NEW, "away")
    assert {a.player_id for a in on_old} == {TRADED, 5}
    assert all(a.team_id == OLD for a in on_old)
    assert {a.player_id for a in on_new} == {2}
    assert player_model.event_side({"homeTeam": {"id": OLD}}, OLD) == "home"
    assert player_model.event_side(json.dumps({"awayTeam": {"id": NEW}}), NEW) == "away"
    assert player_model.event_side("{not json", NEW) is None
    assert player_model.event_side(None, NEW) is None


def test_off_reproduces_the_bug_and_on_gives_old_team_games_to_the_old_team(
    tmp_path: Path,
) -> None:
    conn = make_db(tmp_path / "db.sqlite")
    traded_history(conn)
    before = KO_TS - 60
    off = load_appearances(conn, "hockey", [OLD, NEW], before, None)
    on = load_appearances(conn, "hockey", [OLD, NEW], before, None,
                          team_from_side=True)
    old_games = {100, 101, 102}

    def teams(apps: list[player_model.Appearance]) -> set[int]:
        return {a.team_id for a in apps
                if a.player_id == TRADED and a.event_id in old_games}

    assert teams(off) == {NEW}  # the bug: OLD's games counted as NEW's
    assert teams(on) == {OLD}
    # Today's two teams (NEW, OPP): off, his sample holds OLD's games against
    # NEW; on, only his games for NEW.
    today_off = load_appearances(conn, "hockey", [NEW, OPP], before, None)
    today_on = load_appearances(conn, "hockey", [NEW, OPP], before, None,
                                team_from_side=True)
    assert {a.event_id for a in today_off if a.player_id == TRADED} == (
        old_games | set(range(200, 206)))
    assert {a.event_id for a in today_on if a.player_id == TRADED} == set(
        range(200, 206))
    # Nobody else moved: every non-traded appearance is the same.
    def rest(apps: list[player_model.Appearance]) -> list[tuple[int, int, int]]:
        return sorted((a.event_id, a.player_id, a.team_id) for a in apps
                      if a.player_id != TRADED)

    assert rest(today_off) == rest(today_on)


def test_a_game_whose_payload_does_not_name_the_team_is_left_out(
    tmp_path: Path,
) -> None:
    conn = make_db(tmp_path / "db.sqlite")
    traded_history(conn)
    conn.execute("UPDATE sofa_listed_event SET event_json = '{}' WHERE event_id = 200")
    conn.commit()
    on = load_appearances(conn, "hockey", [NEW], KO_TS - 60, None,
                          team_from_side=True)
    assert 200 not in {a.event_id for a in on}
    off = load_appearances(conn, "hockey", [NEW], KO_TS - 60, None)
    assert 200 in {a.event_id for a in off}


def test_the_switch_reads_the_day_and_the_clock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    on = epochs.player_team_from_side
    at = epochs.PLAYER_TEAM_FROM_SIDE_FROM_UTC
    assert at == datetime(2026, 10, 14, 0, 0, tzinfo=UTC)
    # A day before the switch is never rebuilt under it, whatever the clock;
    # the day itself needs the clock past the moment.
    assert not on("2026-10-13", datetime(2026, 10, 14, 6, tzinfo=UTC))
    assert not on("2026-10-14", datetime(2026, 10, 13, 23, 59, tzinfo=UTC))
    assert on("2026-10-14", at)
    assert on("2026-10-15", datetime(2026, 10, 15, tzinfo=UTC))
    monkeypatch.setattr(epochs, "PLAYER_TEAM_FROM_SIDE_FROM_UTC", None)
    assert not on("2026-10-15", datetime(2026, 10, 15, tzinfo=UTC))


def _forecast(db: Path) -> list[dict[str, Any]]:
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        return player_model.forecast_records(
            conn, "hockey", "ice-hockey", [_record(T2)], "x", set(), KO_TS
        )
    finally:
        conn.close()


def test_the_pregame_forecast_follows_the_switch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "db.sqlite"
    traded_history(make_db(db))
    # The fixture's day (2026-09-28) is before the switch: the old rule, and
    # rows byte-identical to the rule before it (no marker).
    off = _forecast(db)
    assert {r["model_n"] for r in off} == {9}
    assert all("player_team_rule" not in r for r in off)
    monkeypatch.setattr(epochs, "PLAYER_TEAM_FROM_SIDE_FROM_UTC",
                        datetime(2026, 9, 28, 0, 0, tzinfo=UTC))
    on = _forecast(db)
    assert {r["model_n"] for r in on} == {6}
    assert {r["player_team_rule"] for r in on} == {epochs.PLAYER_TEAM_RULE}
    # A snapshot clock before the moment keeps the old rule on that day.
    monkeypatch.setattr(epochs, "PLAYER_TEAM_FROM_SIDE_FROM_UTC",
                        datetime(2026, 9, 28, 17, 0, tzinfo=UTC))
    assert {r["model_n"] for r in _forecast(db)} == {9}
    # The marker is one of the keys a pregame number carries to settled.json.
    assert "player_team_rule" in player_model.MODEL_KEYS


def test_settle_time_number_follows_the_games_day(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "db.sqlite"
    traded_history(make_db(db))
    from bet.sofa.shadow import SPORTS

    rows = [{
        "superbet_event_id": "1", "market_id": SOG,
        "family": "player_shots_on_goal", "subject": "Novak, Jan",
        "line": 2.5, "side": "OVER", "odds": 1.9,
    }]
    event = {"id": 999, "homeTeam": {"id": NEW}, "awayTeam": {"id": OPP}}
    kickoff = datetime.fromtimestamp(KO_TS, UTC)
    box = {"jan novak": TRADED}

    def settle() -> dict[str, Any]:
        [(_, fields)] = settle_shadow._settle_time_model(
            rows, SPORTS["hockey"], event, {"startTimestamp": KO_TS}, kickoff,
            str(db), box)
        return fields

    off = settle()
    assert off["model_n"] == 9 and "player_team_rule" not in off
    monkeypatch.setattr(epochs, "PLAYER_TEAM_FROM_SIDE_FROM_UTC",
                        datetime(2026, 9, 28, 0, 0, tzinfo=UTC))
    on = settle()
    assert on["model_n"] == 6 and on["player_team_rule"] == epochs.PLAYER_TEAM_RULE


def test_the_fit_replay_follows_the_flag(tmp_path: Path) -> None:
    from scripts.sofa import fit_player_model as fpm

    conn = make_db(tmp_path / "db.sqlite")
    traded_history(conn)
    cutoff = KO_TS - 60
    for flag in (False, True):
        mem = fpm.History.from_db(conn, "hockey", team_from_side=flag)
        sql = load_appearances(conn, "hockey", [OLD, NEW, OPP], cutoff, None,
                               team_from_side=flag)
        got = mem.appearances_before([OLD, NEW, OPP], cutoff, None)
        assert sorted((a.event_id, a.player_id, a.team_id) for a in got) == sorted(
            (a.event_id, a.player_id, a.team_id) for a in sql)
