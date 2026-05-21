import json
import sqlite3
import pytest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import sys

# Ensure scripts dir is in path to import locally
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from agent_output import AgentOutput
from inspect_pipeline import inspect_s0, inspect_s1, inspect_s2, inspect_s3, inspect_s7, inspect_s8


def _install_sqlite_db(monkeypatch, tmp_path):
    db_path = tmp_path / "inspect_pipeline.db"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE sports (id INTEGER PRIMARY KEY, name TEXT);
            CREATE TABLE teams (id INTEGER PRIMARY KEY, name TEXT);
            CREATE TABLE team_form (team_id INTEGER, sport_id INTEGER, stat_key TEXT, source TEXT);
            CREATE TABLE scraper_runs (
                sport TEXT,
                status TEXT,
                records_scraped INTEGER,
                records_inserted INTEGER,
                records_updated INTEGER,
                started_at TEXT,
                finished_at TEXT
            );
            CREATE TABLE analysis_results (betting_date TEXT);
            CREATE TABLE gate_results (betting_date TEXT, status TEXT);
            CREATE TABLE coupons (
                id INTEGER PRIMARY KEY,
                coupon_id TEXT,
                coupon_type TEXT,
                total_odds REAL,
                stake_pln REAL,
                status TEXT,
                created_at TEXT,
                placed_at TEXT
            );
            CREATE TABLE bets (id INTEGER PRIMARY KEY, coupon_id INTEGER);
            """
        )

    monkeypatch.setattr("inspect_pipeline._get_db", lambda: sqlite3.connect(db_path))
    return db_path


def _patch_json_loader(monkeypatch, mapping):
    def fake_load_json(relative_path, date):
        return mapping.get(relative_path)

    monkeypatch.setattr("inspect_pipeline._load_json", fake_load_json)

def test_no_kickoff_utc_in_source():
    """Regression test: kickoff_utc should not be used."""
    script_path = ROOT / "scripts" / "inspect_pipeline.py"
    content = script_path.read_text()
    assert "kickoff_utc" not in content, "kickoff_utc found in inspect_pipeline.py (should be kickoff)"

def test_metric_key_consistency():
    """Regression test: total_discovery_events used instead of total_scan_events."""
    script_path = ROOT / "scripts" / "inspect_pipeline.py"
    content = script_path.read_text()
    assert "total_discovery_events" in content
    assert "total_scan_events" not in content

def test_inspect_s0_valid_dict():
    mock_db = MagicMock()
    mock_db.__enter__.return_value = mock_db
    mock_db.execute.return_value.fetchall.return_value = []
    mock_db.execute.return_value.fetchone.return_value = [0]
    
    with patch("inspect_pipeline._get_db", return_value=mock_db):
        out = AgentOutput("s0")
        out.summary = MagicMock()
        result = inspect_s0("2026-05-14", out)
        
        assert isinstance(result, dict)
        assert "_verdict" in result
        assert result["_verdict"] in ("OK", "PARTIAL", "FAILED")


def test_inspect_s0_includes_previous_day_readiness():
    mock_db = MagicMock()
    mock_db.__enter__.return_value = mock_db
    mock_db.execute.return_value.fetchall.return_value = []
    mock_db.execute.return_value.fetchone.return_value = [0]

    readiness = {
        "previous_betting_day": "2026-05-20",
        "ready": False,
        "blocking_reasons": ["previous_day_unsettled", "learning_summary_stale"],
        "coupon_counts": {"total": 1, "pending": 1, "settled": 0},
        "bet_counts": {"total": 1, "pending": 1, "settled": 0},
        "decision_review": {"snapshots": 0, "outcomes": 0, "missing_outcomes": 0},
        "learning_summary": {"exists": True, "analyzed_at": "2026-05-20T08:00:00", "analyzed_for_session_date": False},
    }

    with patch("inspect_pipeline._get_db", return_value=mock_db), patch(
        "inspect_pipeline.assess_s0_readiness", return_value=readiness
    ):
        out = AgentOutput("s0")
        out.summary = MagicMock()
        result = inspect_s0("2026-05-21", out)

    assert result["session_readiness"]["ready"] is False
    assert result["session_readiness"]["blocking_reasons"] == [
        "previous_day_unsettled",
        "learning_summary_stale",
    ]
    assert result["_verdict"] == "FAILED"

def test_inspect_s1_graceful_missing_data():
    with patch("inspect_pipeline._get_db", return_value=None):
        with patch("inspect_pipeline._file_exists", return_value=False):
            out = AgentOutput("s1")
            out.summary = MagicMock()
            out.warning = MagicMock()
            
            result = inspect_s1("2026-05-14", out)
            assert isinstance(result, dict)
            assert result["_verdict"] in ("PARTIAL", "FAILED")


def test_inspect_s2_basketball_rich_summary_fields():
    shortlist = {
        "candidates": [
            {"sport": "basketball", "home_team": "Lakers", "away_team": "Celtics"},
            {"sport": "basketball", "home_team": "Knicks", "away_team": "Bulls"},
        ]
    }

    class FakeConn:
        def execute(self, query, params=None):
            if "FROM team_form tf JOIN sports s ON tf.sport_id = s.id" in query:
                return SimpleNamespace(fetchall=lambda: [("basketball", 3)])
            if "SELECT stat_key, COUNT(*) FROM team_form" in query:
                return SimpleNamespace(fetchall=lambda: [("rebounds", 3), ("assists", 3)])
            if "FROM scraper_runs" in query and "SUM(records_scraped)" in query:
                return SimpleNamespace(fetchall=lambda: [(0, 0, 0)])
            if "FROM scraper_runs" in query:
                return SimpleNamespace(fetchall=lambda: [])
            if "SELECT id FROM sports WHERE name = ?" in query:
                return SimpleNamespace(fetchone=lambda: [1])
            if "FROM team_form tf JOIN teams t ON t.id = tf.team_id" in query:
                team_name = params[0]
                rows = {
                    "Lakers": [
                        ("rebounds", "api-basketball"),
                        ("assists", "api-basketball"),
                        ("steals", "api-basketball"),
                        ("blocks", "api-basketball"),
                        ("turnovers", "api-basketball"),
                        ("fouls", "api-basketball"),
                        ("fg_pct", "api-basketball"),
                        ("three_pct", "api-basketball"),
                        ("ft_pct", "api-basketball"),
                        ("points_in_paint", "api-basketball"),
                        ("fast_break_points", "api-basketball"),
                    ],
                    "Celtics": [("points", "league-profile-baseline")],
                    "Knicks": [],
                    "Bulls": [],
                }
                return SimpleNamespace(fetchall=lambda: rows[team_name])
            raise AssertionError(f"Unexpected query: {query}")

    class FakeDB:
        def __enter__(self):
            return FakeConn()

        def __exit__(self, exc_type, exc, tb):
            return False

    with patch("inspect_pipeline._load_json", return_value=shortlist), patch("inspect_pipeline._get_db", return_value=FakeDB()):
        out = AgentOutput("s2")
        out.summary = MagicMock()

        result = inspect_s2("2026-05-14", out)

    assert result["shortlist_teams_count"] == 4
    assert result["basketball_rich_eligible"] == 1
    assert result["basketball_completed"] == 1
    assert result["basketball_still_missing_rich"] == 3
    assert len(result["basketball_team_completeness"]) == 4
    assert result["basketball_team_completeness"][0]["team"] == "Bulls"


def test_inspect_s2_separates_scraper_success_from_s3_readiness(monkeypatch, tmp_path):
    db_path = _install_sqlite_db(monkeypatch, tmp_path)
    shortlist = {
        "candidates": [
            {"sport": "football", "home_team": "Arsenal", "away_team": "Chelsea"},
            {"sport": "football", "home_team": "Liverpool", "away_team": "Tottenham"},
        ]
    }
    _patch_json_loader(monkeypatch, {"betting/data/{date}_s2_shortlist.json": shortlist})

    with sqlite3.connect(db_path) as conn:
        conn.execute("INSERT INTO sports (id, name) VALUES (?, ?)", (1, "football"))
        teams = [(1, "Arsenal"), (2, "Chelsea"), (3, "Liverpool"), (4, "Tottenham")]
        conn.executemany("INSERT INTO teams (id, name) VALUES (?, ?)", teams)
        conn.execute(
            "INSERT INTO scraper_runs (sport, status, records_scraped, records_inserted, records_updated, started_at, finished_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("football", "success", 12, 5, 2, "2026-05-21T06:10:00", "2026-05-21T06:15:00"),
        )
        for stat_key in ("corners", "yellow_cards", "red_cards", "shots", "shots_on_target", "fouls", "possession"):
            conn.execute(
                "INSERT INTO team_form (team_id, sport_id, stat_key, source) VALUES (?, ?, ?, ?)",
                (1, 1, stat_key, "flashscore"),
            )
        conn.execute(
            "INSERT INTO team_form (team_id, sport_id, stat_key, source) VALUES (?, ?, ?, ?)",
            (2, 1, "points", "league-profile-baseline"),
        )
        conn.execute(
            "INSERT INTO team_form (team_id, sport_id, stat_key, source) VALUES (?, ?, ?, ?)",
            (3, 1, "corners", "flashscore"),
        )

    out = AgentOutput("s2")
    out.summary = MagicMock()

    result = inspect_s2("2026-05-21", out)

    assert result["scraper_success"]["success_runs"] == 1
    assert result["scraper_success"]["warehouse_improved"] is True
    assert result["shortlist_bucket_counts"] == {
        "rich": 1,
        "baseline_only": 1,
        "partial": 1,
        "no_data": 1,
    }
    assert result["s3_readiness"]["ready"] is False
    assert result["team_form_readiness"]["teams_with_any_data"] == 3
    assert [detail["team"] for detail in result["no_data_shortlist_teams"]] == ["Tottenham"]


def test_inspect_s3_reports_db_json_parity(monkeypatch):
    stats = {
        "analyses": [
            {"has_data": True, "best_safety_score": 6.8, "markets_evaluated": 4, "sport": "football", "data_quality": {"label": "FULL"}},
            {"has_data": True, "best_safety_score": 5.4, "markets_evaluated": 3, "sport": "basketball", "data_quality": {"label": "PARTIAL"}},
        ],
        "total_candidates": 2,
        "candidates_with_data": 2,
        "candidates_without_data": 0,
    }
    _patch_json_loader(monkeypatch, {"betting/data/{date}_s3_deep_stats.json": stats})

    parity_meta = {
        "source": "json_with_db_overlay",
        "counts": {"canonical": 2, "json": 2, "db": 1},
        "parity": {
            "status": "db_subset_of_json",
            "shared_candidates": 1,
            "json_only_candidates": 1,
            "db_only_candidates": 0,
            "overlay_candidates": 1,
            "json_index": {"input_count": 2, "unique_count": 2, "duplicate_count": 0},
            "db_index": {"input_count": 1, "unique_count": 1, "duplicate_count": 0},
        },
    }

    monkeypatch.setattr("inspect_pipeline.load_s3_candidates_with_parity", lambda date: ([{"fixture_id": 1}, {"fixture_id": 2}], parity_meta))

    class FakeConn:
        def execute(self, query, params=None):
            if "FROM analysis_results" in query:
                return SimpleNamespace(fetchone=lambda: [1])
            raise AssertionError(f"Unexpected query: {query}")

    class FakeDB:
        def __enter__(self):
            return FakeConn()

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr("inspect_pipeline._get_db", lambda: FakeDB())

    out = AgentOutput("s3")
    out.summary = MagicMock()

    result = inspect_s3("2026-05-21", out)

    assert result["db_json_parity"]["status"] == "db_subset_of_json"
    assert result["db_json_parity"]["json_only_candidates"] == 1
    assert result["canonical_candidate_count"] == 2


def test_inspect_s7_reports_db_json_bucket_parity(monkeypatch, tmp_path):
    db_path = _install_sqlite_db(monkeypatch, tmp_path)
    gate = {
        "gate_results": {
            "approved": [{"fixture_id": 1}],
            "extended_pool": [],
            "rejected": [{"fixture_id": 2}],
        }
    }
    _patch_json_loader(monkeypatch, {"betting/data/{date}_s7_gate_results.json": gate})

    with sqlite3.connect(db_path) as conn:
        conn.execute("INSERT INTO gate_results (betting_date, status) VALUES (?, ?)", ("2026-05-21", "APPROVED"))
        conn.execute("INSERT INTO gate_results (betting_date, status) VALUES (?, ?)", ("2026-05-21", "EXTENDED"))

    out = AgentOutput("s7")
    out.summary = MagicMock()

    result = inspect_s7("2026-05-21", out)

    assert result["db_json_parity"]["status"] == "mismatch"
    assert sorted(result["db_json_parity"]["mismatched_keys"]) == ["extended_pool", "rejected"]


def test_inspect_s8_reports_coupon_db_json_parity(monkeypatch, tmp_path):
    db_path = _install_sqlite_db(monkeypatch, tmp_path)
    coupon_dir = tmp_path / "betting" / "coupons"
    coupon_dir.mkdir(parents=True)
    (coupon_dir / "2026-05-21-core.md").write_text("# Coupon\n", encoding="utf-8")
    monkeypatch.setattr("inspect_pipeline.COUPON_DIR", coupon_dir)

    coupons_json = {
        "core_coupons": [],
        "combos": [],
        "singles": [
            {
                "id": "CP-2026-05-21-SINGLE1",
                "legs": [{"home_team": "Arsenal", "away_team": "Chelsea"}],
            }
        ],
    }
    _patch_json_loader(monkeypatch, {
        "betting/coupons/{date}.json": coupons_json,
        "config/betting_config.json": {"bankroll": 1000},
    })

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO coupons (id, coupon_id, coupon_type, total_odds, stake_pln, status, created_at, placed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (1, "CP-2026-05-21-SINGLE1", "SINGLE", 1.91, 20.0, "pending", "2026-05-21T08:00:00", "2026-05-21T08:00:00"),
        )
        conn.execute("INSERT INTO bets (id, coupon_id) VALUES (?, ?)", (1, 1))

    out = AgentOutput("s8")
    out.summary = MagicMock()

    result = inspect_s8("2026-05-21", out)

    assert result["db_coupons"] == 1
    assert result["total_legs"] == 1
    assert result["db_json_parity"]["status"] == "exact"
    assert result["json_coupon_counts"]["persisted_coupons"] == 1

