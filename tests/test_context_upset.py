"""Tests for context checks and upset risk modules."""
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from context_checks import run_context_checks
from upset_risk import run_upset_risk


# ---------------------------------------------------------------------------
# Context checks
# ---------------------------------------------------------------------------


def test_context_checks_no_data():
    """Empty state with no data files — should not crash."""
    tmp = tempfile.mkdtemp()
    with patch("context_checks.DATA_DIR", Path(tmp)):
        success, summary = run_context_checks("2099-01-01", {})
    assert success is True
    assert isinstance(summary, str)
    import shutil
    shutil.rmtree(tmp)


# ---------------------------------------------------------------------------
# Upset risk
# ---------------------------------------------------------------------------


def test_upset_risk_no_candidates():
    """Empty candidates (no S3 data) — should not crash."""
    tmp = tempfile.mkdtemp()
    with patch("upset_risk.DATA_DIR", Path(tmp)):
        success, summary = run_upset_risk("2099-01-01", {})
    assert success is True
    assert isinstance(summary, str)
    import shutil
    shutil.rmtree(tmp)


def test_upset_risk_with_candidates():
    """S3 data with candidates — should score them without crashing."""
    tmp = tempfile.mkdtemp()
    data_dir = Path(tmp)
    s3_data = {
        "analyses": [
            {
                "sport": "football",
                "event": "Team A vs Team B",
                "markets": [{"name": "Corners", "safety_score": 0.75}],
            },
            {
                "sport": "tennis",
                "event": "Player X vs Player Y",
                "markets": [{"name": "Total Games", "safety_score": 0.60}],
            },
        ]
    }
    (data_dir / "2099-01-01_s3_deep_stats.json").write_text(
        json.dumps(s3_data), encoding="utf-8"
    )
    with patch("upset_risk.DATA_DIR", data_dir):
        success, summary = run_upset_risk("2099-01-01", {})
    assert success is True
    assert isinstance(summary, str)
    import shutil
    shutil.rmtree(tmp)
