"""scripts/sofa/probe_lineup_availability.py (F3.1), offline with a fake client."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from bet.sofa.errors import CircuitOpenError, ProviderError
from scripts.sofa import probe_lineup_availability as probe_mod
from scripts.sofa.probe_lineup_availability import (
    MAX_EVENTS_CAP,
    ProbeTarget,
    availability_table,
    day_targets,
    probe,
    read_rows,
    select,
    summarise_payload,
)

AT = datetime(2026, 10, 6, 15, 0, tzinfo=UTC)


def _target(eid: int, hours: float, sport: str = "football") -> ProbeTarget:
    return ProbeTarget(eid, sport, AT + timedelta(hours=hours), 17, "Premier League",
                       "England")


LINEUPS = {
    "confirmed": True,
    "home": {
        "formation": "4-3-3",
        "players": [{"player": {"id": i}, "substitute": i > 11} for i in range(1, 21)],
        "missingPlayers": [{"type": "missing", "reason": 1},
                           {"type": "doubtful", "reason": 3}],
    },
    "away": {"players": [{"player": {"id": 100 + i}, "substitute": i > 11}
                         for i in range(1, 19)]},
}


class FakeClient:
    def __init__(self, answers: dict[int, Any]) -> None:
        self.answers = answers
        self.asked: list[int] = []

    def event_lineups(self, id: int) -> Any | None:
        self.asked.append(id)
        got = self.answers.get(id)
        if isinstance(got, Exception):
            raise got
        return got


def test_summarise_payload() -> None:
    assert summarise_payload(None) == {"status": "NOT_FOUND"}
    assert summarise_payload({}) == {"status": "NOT_FOUND"}
    got = summarise_payload(LINEUPS)
    assert got["status"] == "OK" and got["confirmed"] is True
    assert (got["home_players"], got["home_starters"]) == (20, 11)
    assert (got["home_missing"], got["home_doubtful"]) == (1, 1)
    assert got["home_missing_listed"] and not got["away_missing_listed"]
    assert got["away_starters"] == 11 and got["home_formation"] == "4-3-3"


def test_select_window_gap_sport_and_cap() -> None:
    targets = [_target(1, 0.5), _target(2, 2.5), _target(3, 5.0),
               _target(4, 1.0, "tennis"), _target(5, -0.2)]
    got = select(targets, AT, sports=["football"], min_hours=0.0, max_hours=3.0,
                 max_events=20)
    assert [t.sofascore_event_id for t in got] == [1, 2]
    # Asked 10 minutes ago: skipped; 40 minutes ago: asked again (a new horizon).
    previous = [
        {"sofascore_event_id": 1,
         "probed_at_utc": (AT - timedelta(minutes=10)).isoformat()},
        {"sofascore_event_id": 2,
         "probed_at_utc": (AT - timedelta(minutes=40)).isoformat()},
    ]
    got = select(targets, AT, sports=["football"], min_hours=0.0, max_hours=3.0,
                 max_events=20, previous=previous)
    assert [t.sofascore_event_id for t in got] == [2]
    many = [_target(i, 1.0) for i in range(100)]
    assert len(select(many, AT, sports=["football"], min_hours=0, max_hours=3,
                      max_events=1000)) == MAX_EVENTS_CAP


def test_probe_writes_one_row_per_ask_and_stops_on_the_breaker(tmp_path: Path) -> None:
    out = tmp_path / "d" / "lineup_probe.jsonl"
    client = FakeClient({1: LINEUPS, 2: None, 3: ProviderError("HTTP 500"),
                         4: CircuitOpenError("open"), 5: LINEUPS})
    targets = [_target(i, float(i)) for i in range(1, 6)]
    asked, failed, broke = probe(client, targets, out, "2026-10-06", clock=lambda: AT)
    assert (asked, failed, broke) == (3, 1, True)
    assert client.asked == [1, 2, 3, 4]  # nothing after the breaker opened
    rows = read_rows(out)
    assert [r["status"] for r in rows] == ["OK", "NOT_FOUND", "ERROR"]
    assert rows[0]["hours_before"] == 1.0
    assert rows[0]["probed_at_utc"] == "2026-10-06T15:00:00Z"


def test_availability_table_counts_by_horizon() -> None:
    rows = [
        {"sport": "football", "competition_name": "PL", "hours_before": 2.5,
         "status": "NOT_FOUND"},
        {"sport": "football", "competition_name": "PL", "hours_before": 0.8,
         "status": "OK", "confirmed": True, "home_missing_listed": True},
        {"sport": "football", "competition_name": "PL", "hours_before": 0.7,
         "status": "ERROR"},
    ]
    table = availability_table(rows)
    assert "| football | PL | 30-60 min | 1 | 1 | 1 | 1 |" in table
    assert "| football | PL | 2-3 h | 1 | 0 | 0 | 0 |" in table
    assert len(table) == 4


def test_day_targets_read_both_fixture_files(tmp_path: Path) -> None:
    (tmp_path / "02_fixtures.json").write_text(json.dumps([
        {"sofascore_event_id": 11, "sport": "football",
         "kickoff_utc": "2026-10-06T18:00:00Z", "competition_id": 17,
         "competition_name": "PL", "category_name": "England"},
        {"sofascore_event_id": None, "sport": "football",
         "kickoff_utc": "2026-10-06T18:00:00Z"},
    ]))
    (tmp_path / "sport_fixtures.json").write_text(json.dumps({"fixtures": [
        {"sofascore_event_id": 22, "sport": "hockey",
         "kickoff_utc": "2026-10-06T17:00:00Z", "tournament": "USA - NHL",
         "competition_id": None},
        {"sofascore_event_id": None, "sport": "hockey",
         "kickoff_utc": "2026-10-06T17:00:00Z"},
    ]}))
    got = day_targets(tmp_path)
    assert [(t.sofascore_event_id, t.sport) for t in got] == [(22, "hockey"),
                                                             (11, "football")]


def test_main_dry_run_and_summary_make_no_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    day = tmp_path / "2026-10-06"
    day.mkdir()
    (day / "02_fixtures.json").write_text(json.dumps([
        {"sofascore_event_id": 11, "sport": "football",
         "kickoff_utc": "2026-10-06T16:00:00Z", "competition_name": "PL"},
    ]))
    monkeypatch.setenv("SOFA_NOW", "2026-10-06T15:00:00Z")
    monkeypatch.setattr(probe_mod, "probe", lambda *a, **k: pytest.fail("asked"))
    assert probe_mod.main(["--date", "2026-10-06", "--runs-dir", str(tmp_path),
                           "--dry-run"]) == 0
    assert '"to_ask": 1' in capsys.readouterr().out
    assert probe_mod.main(["--date", "2026-10-06", "--runs-dir", str(tmp_path),
                           "--summary"]) == 0
    assert probe_mod.main(["--date", "2026-10-07", "--runs-dir", str(tmp_path)]) == 2
