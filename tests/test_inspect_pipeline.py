import pytest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import sys

# Ensure scripts dir is in path to import locally
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from agent_output import AgentOutput
from inspect_pipeline import inspect_s0, inspect_s1, inspect_s2

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
            if "SELECT id FROM sports WHERE name = ?" in query:
                return SimpleNamespace(fetchone=lambda: [1])
            if "SELECT stat_key, source FROM team_form WHERE team_name = ? AND sport_id = ?" in query:
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
