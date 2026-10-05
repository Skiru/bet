"""CS2 and CS2_SETTLE end to end against fake Superbet and Sofascore clients,
and their place in run_pipeline: registered, never in the daily sequence,
never writing into the day's own directory."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from bet.sofa.errors import CircuitOpenError
from scripts.sofa import audit_cs2, run_cs2, run_pipeline, settle_cs2

DATE = "2026-09-26"
KICKOFF = datetime(2026, 9, 26, 15, 0, tzinfo=UTC)


def odd(market: str, name: str, price: float, spec: dict[str, str]) -> dict[str, Any]:
    return {
        "marketName": market,
        "name": name,
        "info": name,
        "price": price,
        "specifiers": spec,
        "status": "active",
    }


class FakeSuperbet:
    def __init__(self, fail_board: bool = False, fail_event: str | None = None) -> None:
        self.fail_board, self.fail_event = fail_board, fail_event

    def events_by_date(
        self, start: datetime, end: datetime, offer_state: str
    ) -> list[dict]:
        if self.fail_board:
            raise RuntimeError("board down")
        assert offer_state == "prematch"
        return [
            {
                "sportId": 55,
                "eventId": 1,
                "matchName": "GamerLegion·magic",
                "utcDate": "2026-09-26T15:00:00Z",
                "tournamentId": 7,
            },
            {
                "sportId": 55,
                "eventId": 2,
                "matchName": "Steel Panthers·Phantom Sharks",
                "utcDate": "2026-09-26T09:00:00Z",
                "tournamentId": 8,
            },  # started
            {
                "sportId": 55,
                "eventId": 3,
                "matchName": "A·B",
                "utcDate": "2026-09-27T01:00:00Z",
                "tournamentId": 7,
            },  # next day
            {
                "sportId": 5,
                "eventId": 4,
                "matchName": "Legia·Lech",
                "utcDate": "2026-09-26T16:00:00Z",
                "tournamentId": 9,
            },  # football
            {
                "sportId": 55,
                "eventId": 5,
                "matchName": "C·D",
                "utcDate": "2026-09-26T18:00:00Z",
                "tournamentId": 7,
            },
        ]

    def event_odds(self, event_id: str) -> dict[str, Any]:
        if event_id == self.fail_event:
            raise RuntimeError("event down")
        if event_id != "1":
            return {"odds": None}
        return {
            "odds": [
                odd("Liczba map", "poniżej 2.5", 1.8, {"total": "2.5"}),
                odd("Liczba map", "powyżej 2.5", 1.95, {"total": "2.5"}),
                odd(
                    "3.mapa - liczba zabójstw zawodnika (z dogrywką)",
                    "REZ - powyżej 25.5",
                    1.85,
                    {"player": "REZ", "total": "25.5"},
                ),
                odd(
                    "3.mapa - liczba zabójstw zawodnika (z dogrywką)",
                    "REZ - poniżej 25.5",
                    1.85,
                    {"player": "REZ", "total": "25.5"},
                ),
            ]
        }

    def _get_json(self, path: str) -> dict[str, Any]:
        return {
            "data": {"tournaments": [{"id": "7", "localNames": {"pl-PL": "CCT - EU"}}]}
        }


def test_snapshot_records_only_unstarted_cs2_series_of_the_day(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(run_cs2, "now", lambda: datetime(2026, 9, 26, 12, tzinfo=UTC))
    result = run_cs2.snapshot(DATE, FakeSuperbet(), str(tmp_path))  # type: ignore[arg-type]
    assert result["verdict"] == "OK"
    assert result["metrics"] == {
        "events_on_board": 3,
        "started": 1,
        "events_with_lines": 1,
        "lines": 4,
        "fetch_failed": 0,
    }
    path = tmp_path / "cs2" / DATE / "snapshots.jsonl"
    (rec,) = [json.loads(x) for x in path.read_text().splitlines()]
    assert rec["team1"] == "GamerLegion" and rec["tournament"] == "CCT - EU"
    assert {ln["family"] for ln in rec["lines"]} == {"maps_total", "player_kills"}
    # A second snapshot appends; it never rewrites the first.
    run_cs2.snapshot(DATE, FakeSuperbet(), str(tmp_path))  # type: ignore[arg-type]
    assert len(path.read_text().splitlines()) == 2


def test_snapshot_verdicts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(run_cs2, "now", lambda: datetime(2026, 9, 26, 12, tzinfo=UTC))
    partial = run_cs2.snapshot(DATE, FakeSuperbet(fail_event="5"), str(tmp_path))  # type: ignore[arg-type]
    assert partial["verdict"] == "PARTIAL" and partial["metrics"]["fetch_failed"] == 1
    failed = run_cs2.snapshot(DATE, FakeSuperbet(fail_board=True), str(tmp_path))  # type: ignore[arg-type]
    assert failed["verdict"] == "FAILED"


# --- settle ---------------------------------------------------------------------


def game(gid: int, start: int, home: int, away: int) -> dict[str, Any]:
    return {
        "id": gid,
        "startTimestamp": start,
        "status": {"type": "finished"},
        "homeScore": {"display": home},
        "awayScore": {"display": away},
        "hasCompleteStatistics": True,
    }


class FakeSofascore:
    """magic - GamerLegion 2-1 of 2026-09-26, as Sofascore serves it."""

    def __init__(
        self,
        status: str = "finished",
        games: list[dict] | None = None,
        breaker: bool = False,
        listed: bool = True,
        event_answers: bool = True,
    ) -> None:
        self.status, self.breaker, self.listed = status, breaker, listed
        # False: /event/{id} answers nothing (a pinned id that no longer
        # resolves - settle_cs2.settle_one then searches, C2).
        self.event_answers = event_answers
        self.games = (
            games
            if games is not None
            else [game(11, 1000, 13, 6), game(12, 2000, 8, 13), game(13, 3000, 19, 17)]
        )
        self.calls: list[str] = []

    def _event(self) -> dict[str, Any]:
        return {
            "id": 900,
            "startTimestamp": int(KICKOFF.timestamp()),
            "homeTeam": {"name": "magic"},
            "awayTeam": {"name": "GamerLegion"},
            "homeScore": {"current": 2},
            "awayScore": {"current": 1},
            "status": {"type": self.status, "description": "Ended"},
            "tournament": {
                "name": "CCT Europe",
                "category": {"name": "Counter Strike"},
            },
        }

    def search(self, q: str) -> dict[str, Any]:
        if self.breaker:
            raise CircuitOpenError("open")
        self.calls.append(f"search {q}")
        return {
            "results": [
                {"type": "team", "entity": {"id": 5, "sport": {"slug": "esports"}}},
                {"type": "team", "entity": {"id": 6, "sport": {"slug": "football"}}},
            ]
        }

    def entity_events(self, team_id: int, kind: str, page: int) -> dict[str, Any]:
        self.calls.append(f"listing {team_id} {kind}")
        return {"events": [self._event()] if self.listed and kind == "last" else []}

    def event(self, event_id: int) -> dict[str, Any]:
        self.calls.append(f"event {event_id}")
        return {"event": self._event()} if self.event_answers else {}

    def esports_games(self, event_id: int) -> dict[str, Any]:
        return {"games": self.games}

    def esports_game_lineups(self, game_id: int) -> dict[str, Any]:
        self.calls.append(f"lineups {game_id}")
        rez = {
            "player": {"name": "REZ"},
            "kills": 28 if game_id == 13 else 12,
            "deaths": 27,
            "assists": 6,
            "headshots": 12,
        }
        return {"homeTeamPlayers": [], "awayTeamPlayers": [rez]}


def write_snapshot(tmp_path: Path) -> None:
    lines = [
        {
            "superbet_event_id": "1",
            "family": "maps_total",
            "map_nr": 0,
            "subject": "",
            "line": 2.5,
            "side": s,
            "odds": o,
        }
        for s, o in (("UNDER", 1.8), ("OVER", 1.95))
    ] + [
        {
            "superbet_event_id": "1",
            "family": "player_kills",
            "map_nr": 3,
            "subject": "REZ",
            "line": 25.5,
            "side": s,
            "odds": 1.85,
        }
        for s in ("OVER", "UNDER")
    ]
    rec = {
        "fetched_at_utc": "2026-09-26T12:00:00Z",
        "superbet_event_id": "1",
        "match_name": "GamerLegion·magic",
        "team1": "GamerLegion",
        "team2": "magic",
        "kickoff_utc": "2026-09-26T15:00:00Z",
        "tournament": "CCT - EU",
        "lines": lines,
    }
    day = tmp_path / "cs2" / DATE
    day.mkdir(parents=True)
    (day / "snapshots.jsonl").write_text(json.dumps(rec) + "\n")


def run_settle(
    tmp_path: Path, sofa: FakeSofascore, hours_after: float
) -> dict[str, Any]:
    at = KICKOFF + timedelta(hours=hours_after)
    return settle_cs2.settle(DATE, sofa, str(tmp_path), at)  # type: ignore[arg-type]


def settled(tmp_path: Path) -> dict[str, Any]:
    events: dict[str, Any] = json.loads(
        (tmp_path / "cs2" / DATE / "settled.json").read_text()
    )["events"]
    return events


def test_settle_grades_the_series_end_to_end(tmp_path: Path) -> None:
    write_snapshot(tmp_path)
    sofa = FakeSofascore()
    result = run_settle(tmp_path, sofa, 6)
    assert result["verdict"] == "OK"
    rec = settled(tmp_path)["1"]
    assert rec["state"] == "SETTLED" and rec["home_is_team1"] is False
    assert rec["maps"] == [[6, 13], [13, 8], [17, 19]]  # GamerLegion first
    got = {(r["family"], r["side"]): (r["actual"], r["outcome"]) for r in rec["graded"]}
    assert got == {
        ("maps_total", "OVER"): (3.0, "WIN"),
        ("maps_total", "UNDER"): (3.0, "LOSS"),
        ("player_kills", "OVER"): (28.0, "WIN"),
        ("player_kills", "UNDER"): (28.0, "LOSS"),
    }
    # The football candidate is never listed.
    assert not any(c.startswith("listing 6") for c in sofa.calls)


def test_a_settled_series_is_never_asked_again(tmp_path: Path) -> None:
    write_snapshot(tmp_path)
    run_settle(tmp_path, FakeSofascore(), 6)
    again = FakeSofascore()
    assert run_settle(tmp_path, again, 30)["metrics"]["kept"] == 1
    assert again.calls == []


def test_too_early_is_not_attempted(tmp_path: Path) -> None:
    write_snapshot(tmp_path)
    sofa = FakeSofascore()
    assert run_settle(tmp_path, sofa, 1)["metrics"]["too_early"] == 1
    assert sofa.calls == []


def test_a_series_not_played_within_48h_is_void_by_superbets_rule(
    tmp_path: Path,
) -> None:
    write_snapshot(tmp_path)
    run_settle(tmp_path, FakeSofascore(status="inprogress"), 6)
    assert settled(tmp_path)["1"]["state"] == "PENDING"
    run_settle(tmp_path, FakeSofascore(status="notstarted"), 50)
    assert settled(tmp_path)["1"]["state"] == "VOID"


def test_our_own_lookup_failure_is_retried_not_voided(tmp_path: Path) -> None:
    """Review finding 3: a transient failure past 48 h once became a permanent
    VOID - Superbet's rule is about the series, not about our request."""
    write_snapshot(tmp_path)
    run_settle(tmp_path, FakeSofascore(listed=False), 50)
    assert settled(tmp_path)["1"]["state"] == "NOT_ON_SOFASCORE"
    run_settle(tmp_path, FakeSofascore(), 60)
    assert settled(tmp_path)["1"]["state"] == "SETTLED"


def test_after_a_week_we_give_up_and_say_it_was_us(tmp_path: Path) -> None:
    write_snapshot(tmp_path)
    run_settle(tmp_path, FakeSofascore(listed=False), 24 * 8)
    rec = settled(tmp_path)["1"]
    assert rec["state"] == "GAVE_UP" and rec["gave_up_on"] == "NOT_ON_SOFASCORE"
    again = FakeSofascore()
    run_settle(tmp_path, again, 24 * 9)
    assert again.calls == []  # terminal


def test_late_player_statistics_are_waited_for(tmp_path: Path) -> None:
    """Review finding 4: SETTLED before the per-player rows landed lost the
    player lines for good."""
    write_snapshot(tmp_path)
    no_stats = [dict(g, hasCompleteStatistics=False) for g in FakeSofascore().games]
    run_settle(tmp_path, FakeSofascore(games=no_stats), 5)
    # Since 2026-10-01 the series lines are graded at once; only the player
    # sides wait (pending_sides), and the series is asked again.
    first = settled(tmp_path)["1"]
    assert first["state"] == "SETTLED" and first["pending_sides"] == 2
    assert {r["family"] for r in first["graded"]} == {"maps_total"}
    run_settle(tmp_path, FakeSofascore(), 30)
    rec = settled(tmp_path)["1"]
    assert rec["state"] == "SETTLED"
    assert {r["family"] for r in rec["graded"]} == {"maps_total", "player_kills"}


def test_statistics_that_never_land_settle_the_rest_after_the_grace(
    tmp_path: Path,
) -> None:
    write_snapshot(tmp_path)
    no_stats = [dict(g, hasCompleteStatistics=False) for g in FakeSofascore().games]
    run_settle(tmp_path, FakeSofascore(games=no_stats), 80)
    rec = settled(tmp_path)["1"]
    assert rec["state"] == "SETTLED" and rec["ungradeable"] == 2
    assert {r["family"] for r in rec["graded"]} == {"maps_total"}


def test_an_unplayed_third_map_in_the_list_does_not_break_the_series(
    tmp_path: Path,
) -> None:
    """Review finding 6."""
    write_snapshot(tmp_path)
    games = [
        *FakeSofascore().games,
        {
            "id": 14,
            "startTimestamp": 4000,
            "status": {"type": "notstarted"},
            "homeScore": {},
            "awayScore": {},
        },
    ]
    run_settle(tmp_path, FakeSofascore(games=games), 6)
    assert settled(tmp_path)["1"]["state"] == "SETTLED"


def test_maps_that_do_not_add_up_are_not_graded(tmp_path: Path) -> None:
    write_snapshot(tmp_path)
    run_settle(tmp_path, FakeSofascore(games=[game(11, 1000, 13, 6)]), 6)
    rec = settled(tmp_path)["1"]
    assert rec["state"] == "DATA_MISMATCH" and "graded" not in rec


def test_an_open_breaker_fails_the_stage_and_keeps_nothing_false(
    tmp_path: Path,
) -> None:
    write_snapshot(tmp_path)
    result = run_settle(tmp_path, FakeSofascore(breaker=True), 6)
    assert result["verdict"] == "FAILED"
    assert "1" not in settled(tmp_path)


def test_no_snapshots_is_a_failure_not_an_empty_success(tmp_path: Path) -> None:
    assert run_settle(tmp_path, FakeSofascore(), 6)["verdict"] == "FAILED"


def test_audit_renders_coverage_and_the_price_table(tmp_path: Path) -> None:
    write_snapshot(tmp_path)
    run_settle(tmp_path, FakeSofascore(), 6)
    text = "\n".join(
        audit_cs2.render(audit_cs2.load(str(tmp_path), DATE, DATE), DATE, DATE)
    )
    assert "series: 1  SETTLED 1" in text
    assert "| CCT - EU | SETTLED 1 |" in text
    # One side per line (the favourite), or the gap is 0 by construction.
    assert "| maps_total | 1 | 1 |" in text and "| ALL | 1 | 2 |" in text


# --- the place in the pipeline --------------------------------------------------------


def test_cs2_stages_are_registered_and_never_in_the_daily_sequence() -> None:
    assert run_pipeline.STAGE_MODULES["CS2"] == "scripts.sofa.run_cs2"
    assert run_pipeline.STAGE_MODULES["CS2_SETTLE"] == "scripts.sofa.settle_cs2"
    daily = {stage for stage, _ in run_pipeline.DEFAULT_SEQUENCE}
    assert not daily & {"CS2", "CS2_SETTLE"}
    assert callable(run_cs2.main) and callable(settle_cs2.main)


def test_cs2_writes_beside_the_day_never_into_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(run_cs2, "now", lambda: datetime(2026, 9, 26, 12, tzinfo=UTC))
    run_cs2.snapshot(DATE, FakeSuperbet(), str(tmp_path))  # type: ignore[arg-type]
    run_settle(tmp_path, FakeSofascore(), 6)
    written = {
        p.relative_to(tmp_path).parts[0] for p in tmp_path.rglob("*") if p.is_file()
    }
    assert written == {"cs2"}


def test_audit_history_backtests_the_real_window(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The first --history run scored 0 maps: its cut sat decades ahead and
    the 365-day window behind it held nothing."""
    import sqlite3
    import time

    from bet.sofa.cs2_store import save_series
    from bet.sofa.db import migrate

    dbp = str(tmp_path / "t.db")
    migrate(dbp)
    conn = sqlite3.connect(dbp)
    now = int(time.time())
    for i in range(40):
        ev = {
            "id": i + 1,
            "startTimestamp": now - (40 - i) * 3600,
            "homeTeam": {"id": 1, "name": "a"},
            "awayTeam": {"id": 2, "name": "b"},
            "homeScore": {"current": 1},
            "awayScore": {"current": 0},
            "status": {"type": "finished", "description": "Ended"},
        }
        games = [
            {
                "id": 1000 + i,
                "startTimestamp": 1,
                "status": {"type": "finished"},
                "homeScore": {"display": 13},
                "awayScore": {"display": 8},
            }
        ]
        save_series(conn, ev, games, {}, "t", True)
    conn.close()
    monkeypatch.setenv("SOFA_DB_PATH", dbp)
    monkeypatch.setenv("SOFA_RUNS_DIR", str(tmp_path))
    monkeypatch.setattr("sys.argv", ["audit_cs2", "--history"])
    import io
    from contextlib import redirect_stdout

    out = io.StringIO()
    with redirect_stdout(out):
        audit_cs2.main()
    text = out.getvalue()
    assert "series 40" in text
    assert "coin): 0 maps predicted" not in text and "maps predicted" in text
