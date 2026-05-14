import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
import sys

# Ensure scripts dir is in path to import locally
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from agent_output import AgentOutput
from inspect_pipeline import inspect_s0, inspect_s1

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
