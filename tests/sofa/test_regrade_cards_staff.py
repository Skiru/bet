"""--cards-staff selects the card-points rows of events with a staff card,
live and cache-calibration, and nothing else (2026-10-02)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from bet.sofa.db import migrate
from scripts.sofa.regrade_settled import cards_staff_candidates, staff_card_events


def _row(
    conn: sqlite3.Connection, eid: int, market: str, run_date: str, line: float = 4.5
) -> None:
    conn.execute(
        "INSERT INTO sofa_settled_row (run_date, sofascore_event_id, sport, market,"
        " subject, line, direction, sample_size, sample_mean, sample_sd, p_central,"
        " p_bar, actual_value, outcome, settled_at) VALUES"
        " (?, ?, 'football', ?, '', ?, 'OVER', 10, 4, 1, 0.5, 0.5, 5, 'WIN', 'x')",
        (run_date, eid, market, line),
    )


def test_staff_card_events_and_their_rows(tmp_path: Path) -> None:
    db = str(tmp_path / "s.db")
    migrate(db)
    conn = sqlite3.connect(db)
    staff = {"incidents": [{"incidentType": "card", "manager": {"id": 1},
                            "playerName": "Coach", "incidentClass": "yellow"}]}
    player = {"incidents": [{"incidentType": "card", "player": {"id": 2},
                             "manager": None, "incidentClass": "yellow"}]}
    for eid, inc in ((1, staff), (2, player)):
        conn.execute(
            "INSERT INTO sofa_event_stats (sofascore_event_id, fetched_at,"
            " statistics_json, incidents_json, status_type) VALUES (?, 'x', NULL, ?,"
            " 'finished')",
            (eid, json.dumps(inc)),
        )
    _row(conn, 1, "cards_points_total", "2026-09-30")
    _row(conn, 1, "cards_points_total", "cache-calibration", line=3.5)
    _row(conn, 1, "corners_total", "2026-09-30")
    _row(conn, 2, "cards_points_total", "2026-09-30")
    conn.commit()
    assert staff_card_events(conn) == {1}
    rows = cards_staff_candidates(conn)
    assert sorted((r["run_date"], r["market"]) for r in rows) == [
        ("2026-09-30", "cards_points_total"),
        ("cache-calibration", "cards_points_total"),
    ]
