"""Re-grading settled rows after their match data was re-fetched.

2026-09-28: event 17059933 was settled on an early Sofascore snapshot -
yellowCards 0-0, no card incidents - and the truth was 3-3. Settled rows are
never overwritten, so after the cache was repaired 88 card rows kept the wrong
outcome. scripts/sofa/regrade_settled.py grades them again with the code that
graded them and changes only actual_value / outcome / settled_at.
"""

import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

import pytest

from bet.sofa.db import migrate

EARLY = "2026-09-21T04:00:00+00:00"
GRADED = "2026-09-21T05:00:00+00:00"
LATE = "2026-09-28T08:00:00+00:00"
EID = 17059933


def _stats(yellow: tuple[int, int]) -> str:
    items = [
        {
            "key": "yellowCards",
            "name": "Yellow cards",
            "homeValue": yellow[0],
            "awayValue": yellow[1],
        },
        {"key": "redCards", "name": "Red cards", "homeValue": 0, "awayValue": 0},
    ]
    return json.dumps(
        {
            "statistics": [
                {
                    "period": "ALL",
                    "groups": [{"groupName": "x", "statisticsItems": items}],
                }
            ]
        }
    )


def _cards(home: int, away: int) -> str:
    incidents = [
        {
            "incidentType": "card",
            "incidentClass": "yellow",
            "isHome": True,
            "player": {"id": i},
        }
        for i in range(home)
    ] + [
        {
            "incidentType": "card",
            "incidentClass": "yellow",
            "isHome": False,
            "player": {"id": 100 + i},
        }
        for i in range(away)
    ]
    return json.dumps({"incidents": incidents})


EVENT = {
    "id": EID,
    "startTimestamp": 1_790_000_000,
    "status": {"type": "finished"},
    "homeTeam": {"id": 11, "name": "ASA Targu Mures"},
    "awayTeam": {"id": 22, "name": "CS Dinamo Bucuresti"},
    "homeScore": {"current": 1, "normaltime": 1},
    "awayScore": {"current": 1, "normaltime": 1},
    "tournament": {
        "category": {"sport": {"slug": "football"}},
        "uniqueTournament": {"id": 152},
    },
}


def _row(
    run_date: str,
    market: str,
    subject: str,
    line: float,
    direction: str,
    actual: float,
    outcome: str,
    settled_at: str = GRADED,
) -> tuple[Any, ...]:
    return (
        run_date,
        EID,
        "football",
        152,
        market,
        subject,
        line,
        direction,
        10,
        4.0,
        1.0,
        0.5,
        0.5,
        None,
        actual,
        outcome,
        settled_at,
    )


def _db(tmp_path: Path, stats_fetched_at: str) -> Path:
    db = tmp_path / "sofa.db"
    migrate(str(db))
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO sofa_event_stats (sofascore_event_id, fetched_at,"
        " statistics_json, incidents_json, status_type)"
        " VALUES (?, ?, ?, ?, 'finished')",
        (EID, stats_fetched_at, _stats((3, 3)), _cards(3, 3)),
    )
    # The pre-match copy of the same match, as a `next` listing holds it:
    # listed first, no score. It must not be the one that grades.
    upcoming = {
        **EVENT,
        "status": {"type": "notstarted"},
        "homeScore": {},
        "awayScore": {},
    }
    conn.execute(
        "INSERT INTO sofa_entity_events VALUES (11, 'next', 0, ?, ?)",
        (EARLY, json.dumps({"events": [upcoming]})),
    )
    conn.execute(
        "INSERT INTO sofa_entity_events VALUES (11, 'last', 0, ?, ?)",
        (LATE, json.dumps({"events": [EVENT]})),
    )
    conn.executemany(
        "INSERT INTO sofa_settled_row (run_date, sofascore_event_id, sport,"
        " competition_id, market, subject, line, direction, sample_size,"
        " sample_mean, sample_sd, p_central, p_bar, market_p, actual_value,"
        " outcome, settled_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            # live, graded on the 0-0 snapshot
            _row("2026-09-22", "cards_points_total", "", 4.5, "UNDER", 0.0, "WIN"),
            _row(
                "2026-09-22",
                "cards_points_for",
                "asa targu mures",
                1.5,
                "OVER",
                0.0,
                "LOSS",
            ),
            # cache-calibration, subject is the team id
            _row(
                "cache-calibration", "cards_points_for", "22", 2.5, "UNDER", 0.0, "WIN"
            ),
            # already right: must not be touched
            _row("2026-09-22", "cards_points_total", "", 7.5, "UNDER", 6.0, "WIN"),
            # a score market got no new data: left as graded, even though the
            # cached listing (1-1) disagrees with what was settled (3)
            _row("2026-09-22", "goals_total", "", 2.5, "OVER", 3.0, "WIN"),
        ],
    )
    conn.commit()
    conn.close()
    day = tmp_path / "runs/2026-09-22"
    day.mkdir(parents=True)
    (day / "02_fixtures.json").write_text(
        json.dumps(
            [
                {
                    "sofascore_event_id": EID,
                    "home_name": "ASA Târgu Mureş",
                    "away_name": "CS Dinamo București",
                }
            ]
        )
    )
    return db


def _run(tmp_path: Path, db: Path, monkeypatch: pytest.MonkeyPatch, *argv: str) -> None:
    from scripts.sofa.regrade_settled import main

    monkeypatch.setenv("SOFA_DB_PATH", str(db))
    monkeypatch.setenv("SOFA_RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setattr(sys, "argv", ["regrade", *argv])
    assert main() == 0


def _outcomes(db: Path) -> dict[tuple[str, str, float], tuple[float, str]]:
    conn = sqlite3.connect(db)
    out = {
        (r[0], r[1], r[2]): (r[3], r[4])
        for r in conn.execute(
            "SELECT run_date, market, line, actual_value, outcome FROM sofa_settled_row"
        )
    }
    conn.close()
    return out


def test_a_dry_run_changes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    db = _db(tmp_path, LATE)
    before = _outcomes(db)
    _run(tmp_path, db, monkeypatch)
    assert _outcomes(db) == before
    summary = json.loads(capsys.readouterr().out.split("SOFA_SUMMARY: ")[1])
    assert summary["metrics"]["tally"] == {"outcome_flipped": 3, "unchanged": 1}


def test_apply_corrects_the_fact_logs_it_and_is_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    db = _db(tmp_path, LATE)
    _run(tmp_path, db, monkeypatch, "--apply")
    after = _outcomes(db)
    assert after[("2026-09-22", "cards_points_total", 4.5)] == (6.0, "LOSS")
    assert after[("2026-09-22", "cards_points_for", 1.5)] == (3.0, "WIN")
    assert after[("cache-calibration", "cards_points_for", 2.5)] == (3.0, "LOSS")
    assert after[("2026-09-22", "cards_points_total", 7.5)] == (6.0, "WIN")
    assert after[("2026-09-22", "goals_total", 2.5)] == (3.0, "WIN")
    log = json.loads(next((tmp_path / "runs").glob("regrade_*.json")).read_text())
    assert len(log) == 3 and {c["old_actual"] for c in log} == {0.0}
    capsys.readouterr()
    _run(tmp_path, db, monkeypatch, "--apply")  # the stamped rows are not picked again
    summary = json.loads(capsys.readouterr().out.split("SOFA_SUMMARY: ")[1])
    assert summary["metrics"]["tally"] == {"unchanged": 1}


def test_a_row_graded_after_the_data_was_fetched_is_not_a_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    db = _db(tmp_path, EARLY)  # stats older than the grading: nothing new to read
    before = _outcomes(db)
    _run(tmp_path, db, monkeypatch, "--apply")
    assert _outcomes(db) == before
    summary = json.loads(capsys.readouterr().out.split("SOFA_SUMMARY: ")[1])
    assert summary["metrics"]["tally"] == {}
