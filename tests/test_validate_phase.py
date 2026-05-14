import pytest
from pathlib import Path
from unittest.mock import patch
import sys

# Ensure scripts dir is in path to import locally
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from validate_phase import Check, validate_data_phase

def test_no_stale_script_references():
    """Regression test: discover_fixtures.py should not be used."""
    script_path = ROOT / "scripts" / "validate_phase.py"
    content = script_path.read_text()
    assert "discover_fixtures.py" not in content, "Found stale reference to discover_fixtures.py"

def test_recovery_messages_use_discover_events():
    """Regression test: recovery messages should use discover_events.py."""
    with patch("validate_phase._load_pipeline_state", return_value={}):
        checks = validate_data_phase("2026-05-14")
        discover_refs = [c for c in checks if "discover_events.py" in c.recovery]
        assert len(discover_refs) > 0, "No recovery messages with discover_events.py found"
        stale_refs = [c for c in checks if "discover_fixtures.py" in c.recovery]
        assert len(stale_refs) == 0, "Found recovery message with discover_fixtures.py"

def test_check_structure():
    """Test the Check class structure."""
    check = Check(
        check_id="T1",
        name="Test Check",
        status="FAIL",
        value="Tested value",
        gate=True,
        recovery="Do something"
    )
    assert check.check_id == "T1"
    assert check.status == "FAIL"
    
    d = check.to_dict()
    assert d["check"] == "T1"
    assert d["gate"] is True
    
    s = str(check)
    assert "❌ T1: Test Check" in s
    assert "[GATE]" in s
    assert "↳ Recovery: Do something" in s
