"""Player-prop rows (the cache replay adds ~1.2M of them since 2026-10-03)
get their own market and direction curves and enter no pool: a pooled number
must say what it pooled across, and a player leg never reads a pool."""

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

from bet.sofa.db import get_connection, migrate
from scripts.sofa.fit_constants import fit_reliability

REPO = Path(__file__).resolve().parents[2]


def _seed_settled(db: str, market: str, n: int, wins: int, eid0: int) -> None:
    with get_connection(db) as conn:
        for i in range(n):
            conn.execute(
                "INSERT INTO sofa_settled_row (run_date, sofascore_event_id, sport,"
                " competition_id, market, subject, line, direction, sample_size,"
                " sample_mean, sample_sd, p_central, p_bar, actual_value, outcome,"
                " settled_at) VALUES ('cache-calibration', ?, 'football', 1, ?, '',"
                " 0.5, 'OVER', 10, 1.0, 1.0, 0.85, 0.85, 1.0, ?, 'x')",
                (eid0 + i, market, "WIN" if i < wins else "LOSS"))
        conn.commit()


def test_reliability_pool_holds_team_rows_only(tmp_path: Path) -> None:
    db = str(tmp_path / "sofa.db")
    migrate(db)
    _seed_settled(db, "goals_total", 400, 340, 0)
    with get_connection(db) as conn:
        team_only = fit_reliability(conn)
    _seed_settled(db, "player_fouls_for", 400, 200, 10_000)
    with get_connection(db) as conn:
        both = fit_reliability(conn)
    assert both["_pooled"] == team_only["_pooled"]
    assert "player_fouls_for" in both  # its own entry stays


def test_confidence_pools_hold_team_rows_only(tmp_path: Path) -> None:
    db = tmp_path / "sofa.db"
    con = sqlite3.connect(db)
    con.execute("""create table sofa_settled_row (market text, line real,
        direction text, sample_size int, sample_mean real, sample_sd real,
        actual_value real, p_central real, sport text, sofascore_event_id int)""")
    con.execute("create table sofa_entity_events (kind text, events_json text)")
    rows = [("goals_total", 4.5, "UNDER", 10, 2.0, 1.2, 2.0 if i % 5 else 6.0,
             0.9, "football", i) for i in range(1200)]
    rows += [("player_fouls_for", 0.5, "OVER", 10, 1.2, 1.0, 0.0 if i % 2 else 2.0,
              0.9, "football", 5000 + i) for i in range(1200)]
    con.executemany("insert into sofa_settled_row values (?,?,?,?,?,?,?,?,?,?)", rows)
    con.commit()
    con.close()
    out = tmp_path / "cal.json"
    proc = subprocess.run(
        [sys.executable, "scripts/sofa/fit_confidence.py", "--db-path", str(db),
         "--out", str(out)],
        cwd=REPO, capture_output=True, text=True,
        env={"PYTHONPATH": "src:.", "PATH": "/usr/bin:/bin"},
    )
    assert proc.returncode == 0, proc.stderr
    doc = json.loads(out.read_text())
    assert sum(b["n"] for b in doc["pooled"].values()) == 1200
    assert sum(b["n"] for b in doc["pooled_by_sport"]["football"].values()) == 1200
    assert "player_fouls_for" in doc["by_market"]
