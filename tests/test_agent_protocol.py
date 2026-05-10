"""Tests for agent communication protocol."""
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from agent_protocol import (
    write_step_output,
    read_agent_review,
    STEP_AGENT_CONFIG,
    REVIEWS_DIR,
)


# ---------------------------------------------------------------------------
# File I/O
# ---------------------------------------------------------------------------


def test_write_step_output_creates_file():
    """Verify JSON file is created in correct location."""
    tmp = tempfile.mkdtemp()
    reviews_dir = Path(tmp) / "reviews"

    with patch("agent_protocol.REVIEWS_DIR", reviews_dir):
        result = write_step_output(
            date="2099-01-01",
            step_id="s3_deep_stats",
            metrics={"candidates_analyzed": 5, "avg_safety_score": 0.72},
            artifacts=["betting/data/2099-01-01_s3_deep_stats.json"],
        )

    out_path = Path(result)
    assert out_path.exists()

    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert data["step_id"] == "s3_deep_stats"
    assert data["date"] == "2099-01-01"
    assert data["metrics"]["candidates_analyzed"] == 5
    assert "written_at" in data

    import shutil
    shutil.rmtree(tmp)


def test_read_agent_review_returns_none_when_missing():
    """Verify graceful None return when no review file exists."""
    tmp = tempfile.mkdtemp()
    reviews_dir = Path(tmp) / "reviews"

    with patch("agent_protocol.REVIEWS_DIR", reviews_dir):
        result = read_agent_review("2099-01-01", "s3_deep_stats")

    assert result is None

    import shutil
    shutil.rmtree(tmp)


def test_read_agent_review_reads_existing():
    """Verify review file is read correctly when it exists."""
    tmp = tempfile.mkdtemp()
    reviews_dir = Path(tmp) / "reviews"
    date_dir = reviews_dir / "2099-01-01"
    date_dir.mkdir(parents=True)

    review = {
        "agent": "bet-statistician",
        "step_id": "s3_deep_stats",
        "status": "approved",
        "flags": [],
        "enrichments": {"top_pick": "Liverpool corners"},
    }
    (date_dir / "s3_deep_stats_review.json").write_text(
        json.dumps(review), encoding="utf-8"
    )

    with patch("agent_protocol.REVIEWS_DIR", reviews_dir):
        result = read_agent_review("2099-01-01", "s3_deep_stats")

    assert result is not None
    assert result["status"] == "approved"
    assert result["agent"] == "bet-statistician"

    import shutil
    shutil.rmtree(tmp)


# ---------------------------------------------------------------------------
# Config coverage
# ---------------------------------------------------------------------------


def test_step_agent_config_has_required_keys():
    """Verify STEP_AGENT_CONFIG entries have expected structure."""
    for step_id, config in STEP_AGENT_CONFIG.items():
        assert "agent" in config, f"Step {step_id} missing 'agent' key"
