"""--match-tiebreak: re-grade tennis games rows graded with 10 points as games.

Before afdb886f a match tiebreak's points were summed as games, so 6-4 6-7(3)
10-5 settled games_won_for at 22 and games_total at 38. On 2026-09-29 the
settled history held 144 such rows (21-22.09), 50 of them with the wrong
outcome. The fetch time of the data says nothing about these rows, so they
are picked by the match, not by fetched_at.
"""

import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

import pytest

from bet.sofa.db import migrate

EID, PLAIN = 16498311, 16498312
DAY = "2026-09-21"


def _event(eid: int, home: dict[str, int], away: dict[str, int]) -> dict[str, Any]:
    return {
        "id": eid,
        "status": {"type": "finished", "description": "Ended"},
        "winnerCode": 1,
        "homeTeam": {"id": 1, "name": "Luca Stefan Prunescu Nita", "type": 1},
        "awayTeam": {"id": 2, "name": "Ioan Alexandru Teglas", "type": 1},
        "tournament": {"category": {"sport": {"slug": "tennis"}, "name": "ITF Men"}},
        "homeScore": home,
        "awayScore": away,
    }


def _row(eid: int, market: str, subject: str, line: float, actual: float, outcome: str):
    return (
        DAY,
        eid,
        "tennis",
        1,
        market,
        subject,
        line,
        "OVER",
        10,
        12.0,
        3.0,
        0.6,
        0.6,
        None,
        actual,
        outcome,
        "2026-09-22T05:00:00+00:00",
    )


def _db(tmp_path: Path) -> Path:
    db = tmp_path / "sofa.db"
    migrate(str(db))
    conn = sqlite3.connect(db)
    events = [
        _event(
            EID,
            {"period1": 6, "period2": 6, "period3": 10},
            {"period1": 4, "period2": 7, "period3": 5},
        ),
        _event(PLAIN, {"period1": 6, "period2": 6}, {"period1": 4, "period2": 3}),
    ]
    conn.execute(
        "INSERT INTO sofa_entity_events VALUES (1, 'last', 0, ?, ?)",
        ("2026-09-22T04:00:00+00:00", json.dumps({"events": events})),
    )
    conn.executemany(
        "INSERT INTO sofa_settled_row (run_date, sofascore_event_id, sport,"
        " competition_id, market, subject, line, direction, sample_size,"
        " sample_mean, sample_sd, p_central, p_bar, market_p, actual_value,"
        " outcome, settled_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            _row(EID, "games_won_for", "luca stefan prunescu nita", 12.5, 22.0, "WIN"),
            _row(EID, "games_total", "", 30.5, 38.0, "WIN"),
            # no match tiebreak: never a candidate, even if it were wrong
            _row(PLAIN, "games_total", "", 20.5, 99.0, "WIN"),
        ],
    )
    conn.commit()
    conn.close()
    day = tmp_path / "runs" / DAY
    day.mkdir(parents=True)
    (day / "02_fixtures.json").write_text(
        json.dumps(
            [
                {
                    "sofascore_event_id": e,
                    "home_name": "Luca Stefan Prunescu Nita",
                    "away_name": "Ioan Alexandru Teglas",
                }
                for e in (EID, PLAIN)
            ]
        )
    )
    return db


def test_match_tiebreak_rows_are_regraded_by_the_match(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts.sofa.regrade_settled import main

    db = _db(tmp_path)
    monkeypatch.setenv("SOFA_DB_PATH", str(db))
    monkeypatch.setenv("SOFA_RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setattr(sys, "argv", ["regrade", "--match-tiebreak", "--apply"])
    assert main() == 0
    conn = sqlite3.connect(db)
    got = {
        (r[0], r[1]): (r[2], r[3])
        for r in conn.execute(
            "SELECT sofascore_event_id, market, actual_value, outcome"
            " FROM sofa_settled_row"
        )
    }
    conn.close()
    assert got[(EID, "games_won_for")] == (13.0, "WIN")
    assert got[(EID, "games_total")] == (24.0, "LOSS")
    assert got[(PLAIN, "games_total")] == (99.0, "WIN")
