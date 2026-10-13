"""scripts/sofa/measure_settled_by_market.py - offline, on a temp DB and files."""

import json
import sqlite3
from pathlib import Path

import pytest

from bet.sofa import settled_by_market as sbm
from scripts.sofa import measure_settled_by_market as m


def test_stats_roi_hit_and_threshold():
    lines = [sbm.Line("g1", 0.8, 2.0, 1), sbm.Line("g2", 0.8, 2.0, 0),
             sbm.Line("g3", 0.5, 2.0, 1)]
    s = sbm.cell_stats(lines, 0.70)
    assert s is not None
    assert s["n"] == 2 and s["games"] == 2
    assert s["hit"] == pytest.approx(0.5)
    assert s["roi"] == pytest.approx(0.0)
    assert s["roi_lo"] <= s["roi"] <= s["roi_hi"]
    assert sbm.cell_stats(lines, 0.95) is None


def test_bootstrap_is_seeded():
    lines = [sbm.Line(f"g{i % 5}", 0.8, 1.5, i % 2) for i in range(20)]
    assert sbm.bootstrap_roi(lines) == sbm.bootstrap_roi(lines)


def _db(path: Path) -> None:
    con = sqlite3.connect(path)
    con.execute("create table sofa_settled_row (run_date text, sofascore_event_id int,"
                " sport text, market text, direction text, p_central real,"
                " offered_odds real, outcome text)")
    rows = [("2026-10-10", 1, "football", "corners_total", "OVER", 0.8, 1.5, "WIN"),
            ("2026-10-10", 2, "football", "corners_total", "OVER", 0.8, 1.5, "LOSS"),
            ("2026-10-10", 3, "football", "corners_total", "OVER", 0.8, 1.5, "VOID"),
            ("cache-calibration", 4, "football", "corners_total", "OVER", 0.8,
             1.5, "WIN"),
            ("2026-10-10", 5, "tennis", "games_total", "UNDER", 0.9, 1.3, "WIN")]
    con.executemany(
        "insert into sofa_settled_row values (?,?,?,?,?,?,?,?)", rows)
    con.commit()
    con.close()


def test_db_lines_filters_and_never_pools_sports(tmp_path):
    db = tmp_path / "s.db"
    _db(db)
    got = m.db_lines(str(db), "2026-10-09", "2026-10-12")
    assert len(got["football"]) == 2 and len(got["tennis"]) == 1
    sec = m.sport_section("football", got["football"], 0.70, 1, True)
    row = sec["market_direction"][0]
    assert row["label"] == ["corners_total", "OVER"] and row["n"] == 2
    assert sec["family_direction"][0]["label"][1] == "OVER"


def test_cs2_lines_read_model_p_and_price(tmp_path):
    day = tmp_path / "cs2" / "2026-10-10"
    day.mkdir(parents=True)
    graded = [{"family": "match_winner", "side": "T1", "odds": 1.5,
               "model_p": 0.8, "outcome": "WIN"},
              {"family": "match_winner", "side": "T2", "odds": 2.5,
               "model_p": None, "outcome": "LOSS"}]
    (day / "settled.json").write_text(json.dumps({"events": {"7": {"graded": graded}}}))
    got = m.cs2_lines(str(tmp_path), ["2026-10-10"])
    assert len(got) == 1 and got[0][2].p == 0.8 and got[0][2].y == 1


def test_render_warns_with_row_count():
    rows = [("f", "T1", sbm.Line("g", 0.8, 1.5, 1))]
    sec = m.sport_section("cs2", rows, 0.7, 1, False)
    text = m.render({"from": "a", "to": "b", "p_min": 0.7, "min_n": 1,
                     "sports": [sec]})
    assert "Multiple comparisons: this report holds 1 table rows" in text
    assert "RAW model p" in text
