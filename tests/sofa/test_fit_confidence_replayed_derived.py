"""fit_confidence scores a REPLAYED derived row (run_date cache-calibration:
handicap_games / most_games from the tennis rating, the --derived football
joints) by its stored outcome into its own market's curves - and still scores
a live derived row nowhere, and a derived row in no pool or class."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

from bet.sofa.db import migrate
from scripts.sofa import fit_confidence

N = 700


def _insert(conn: sqlite3.Connection, run_date: str, market: str, wins: int,
            n: int, p: float, start: int) -> None:
    for i in range(n):
        conn.execute(
            "INSERT INTO sofa_settled_row (run_date, sofascore_event_id, sport, "
            "competition_id, market, subject, line, direction, sample_size, "
            "sample_mean, sample_sd, p_central, p_bar, market_p, actual_value, "
            "outcome, settled_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (run_date, start + i, "tennis", 1, market, str(i), 1.5, "OVER", 10,
             8.0, 2.0, p, p, None, 3.0 if i < wins else -9.0,
             "WIN" if i < wins else "LOSS", "2026-10-07T00:00:00"))


def test_a_replayed_derived_row_has_its_own_curve_and_no_pool(
        tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "s.db"
    migrate(str(db))
    conn = sqlite3.connect(db)
    _insert(conn, "cache-calibration", "handicap_games", 560, N, 0.80, 1)
    _insert(conn, "2026-10-05", "handicap_games", 0, N, 0.80, 10_000)  # live
    conn.commit()
    conn.close()
    out = tmp_path / "cal.json"
    monkeypatch.setattr(sys, "argv", ["fit_confidence", "--db-path", str(db),
                                      "--out", str(out)])
    fit_confidence.main()
    doc = json.loads(out.read_text(encoding="utf-8"))
    cell = doc["by_market_direction"]["handicap_games|OVER"]["0.800-0.825"]
    assert cell["n"] == N and cell["realised"] == 0.8   # the live rows: not in
    assert not doc.get("pooled") and not doc.get("pooled_by_sport")
