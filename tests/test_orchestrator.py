"""Tests for pipeline orchestrator core logic."""
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# Add scripts to path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from pipeline_orchestrator import (
    load_state,
    save_state,
    run_command,
    check_outputs,
    load_config,
    PIPELINE_STEPS,
    STEP_TIMEOUTS,
)


# ---------------------------------------------------------------------------
# State management
# ---------------------------------------------------------------------------


def test_load_state_fresh():
    """New state has all expected keys."""
    with patch("pipeline_orchestrator.ROOT_DIR", Path(tempfile.mkdtemp())):
        state = load_state("2099-01-01")

    assert state["date"] == "2099-01-01"
    assert "steps" in state
    assert "errors" in state
    assert "step_data" in state
    assert "version" in state
    assert "current_step" in state
    assert "pass_number" in state
    assert isinstance(state["steps"], dict)
    assert isinstance(state["errors"], list)


def test_save_and_load_roundtrip():
    """Save state to temp dir, load it back, verify identical."""
    tmp = tempfile.mkdtemp()
    tmp_path = Path(tmp)
    state_dir = tmp_path / "betting" / "data" / "pipeline_state"

    state = {
        "date": "2099-01-01",
        "session": "full",
        "version": "v1",
        "started_at": "2099-01-01T06:00:00",
        "completed_at": None,
        "current_step": None,
        "steps": {"s1_scan": {"status": "completed"}},
        "errors": [],
        "step_data": {"s1_scan": {"total": 42}},
        "pass_number": 1,
    }

    with patch("pipeline_orchestrator.STATE_DIR", state_dir), \
         patch("pipeline_orchestrator.ROOT_DIR", tmp_path):
        save_state("2099-01-01", state)
        loaded = load_state("2099-01-01")

    assert loaded["date"] == "2099-01-01"
    assert loaded["steps"]["s1_scan"]["status"] == "completed"
    # Clean up
    import shutil
    shutil.rmtree(tmp)


# ---------------------------------------------------------------------------
# Command runner
# ---------------------------------------------------------------------------


def test_run_command_success():
    """Run `echo hello` command, verify success."""
    success, output = run_command("echo hello", "2099-01-01")
    assert success is True
    assert "hello" in output


def test_run_command_failure():
    """Run `false` command, verify failure."""
    success, output = run_command("false", "2099-01-01")
    assert success is False


def test_run_command_timeout():
    """Run with very short timeout, verify timeout error."""
    with patch.dict(STEP_TIMEOUTS, {"test_step": 1}):
        success, output = run_command(
            "python3 -c \"import time; time.sleep(10)\"",
            "2099-01-01",
            step_id="test_step",
        )
    assert success is False
    assert "timed out" in output.lower() or "timeout" in output.lower()


# ---------------------------------------------------------------------------
# Output checking
# ---------------------------------------------------------------------------


def test_check_outputs_existing():
    """Create temp files, verify check passes."""
    tmp = tempfile.mkdtemp()
    step = {"outputs": []}

    # Create a valid JSON file
    data_dir = Path(tmp) / "betting" / "data"
    data_dir.mkdir(parents=True)
    test_file = data_dir / "test_output.json"
    test_file.write_text(json.dumps({"key": "value"}))

    step = {"outputs": ["betting/data/test_output.json"]}
    with patch("pipeline_orchestrator.ROOT_DIR", Path(tmp)):
        missing = check_outputs(step)

    assert missing == []
    import shutil
    shutil.rmtree(tmp)


def test_check_outputs_missing():
    """Verify check reports missing files."""
    tmp = tempfile.mkdtemp()
    step = {"outputs": ["betting/data/nonexistent.json"]}

    with patch("pipeline_orchestrator.ROOT_DIR", Path(tmp)):
        missing = check_outputs(step)

    assert len(missing) == 1
    assert "nonexistent.json" in missing[0]
    import shutil
    shutil.rmtree(tmp)


# ---------------------------------------------------------------------------
# Pipeline definition completeness
# ---------------------------------------------------------------------------


def test_pipeline_steps_complete():
    """Verify all expected step IDs exist in PIPELINE_STEPS."""
    step_ids = {s["id"] for s in PIPELINE_STEPS}
    expected = {
        "s0_settle", "s1_scan", "s1_ingest", "s1a_discover",
        "s1b_parallel", "s1c_aggregate", "s1d_matrix", "s1e_shortlist",
        "s2_tipster", "s3_deep_stats", "s4_odds_eval", "s5_context",
        "s6_upset_risk", "s7_gate", "s8_coupons", "s9_validate", "s10_summary",
    }
    for exp in expected:
        assert exp in step_ids, f"Missing step: {exp}"


def test_step_timeouts_match_steps():
    """Verify every step has a timeout defined."""
    step_ids = {s["id"] for s in PIPELINE_STEPS}
    for step_id in step_ids:
        assert step_id in STEP_TIMEOUTS, f"Missing timeout for step: {step_id}"
