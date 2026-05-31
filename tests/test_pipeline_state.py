"""Tests for PipelineState."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from bet.pipeline.state import PipelineState, STEP_ORDER, DATA_DIR, _determine_phase


@pytest.fixture
def tmp_data_dir(tmp_path):
    """Override DATA_DIR to temp directory for tests."""
    with patch("bet.pipeline.state.DATA_DIR", tmp_path):
        yield tmp_path


class TestPipelineState:
    def test_fresh_start(self, tmp_data_dir):
        state = PipelineState.load("2026-05-30")
        assert state.is_fresh
        assert state.phase == "DATA"
        assert state.position == "S0"
        assert state.completed_steps == []

    def test_advance_basic(self, tmp_data_dir):
        state = PipelineState.load("2026-05-30")
        state.advance("S0", {"settled": True, "pnl": 12.5})

        assert "S0" in state.completed_steps
        assert state.position == "S1"
        assert state.phase == "DATA"
        assert state.data_summary["S0"]["settled"] is True

    def test_advance_to_analysis_phase(self, tmp_data_dir):
        state = PipelineState.load("2026-05-30")
        # Advance through DATA phase
        for step in ["S0", "S1", "S1e", "S2", "S2.3", "S2.5", "S2.7", "S2.9"]:
            state.advance(step)

        assert state.phase == "ANALYSIS_BUILD"
        assert state.position == "S3"

    def test_persist_and_reload(self, tmp_data_dir):
        state = PipelineState.load("2026-05-30")
        state.advance("S0", {"foo": "bar"})
        state.add_decision("skip_esports")
        state.set_flag("tipster_partial", True)

        # Reload
        loaded = PipelineState.load("2026-05-30")
        assert loaded.completed_steps == ["S0"]
        assert loaded.data_summary["S0"]["foo"] == "bar"
        assert "skip_esports" in loaded.decisions
        assert loaded.flags["tipster_partial"] is True

    def test_can_proceed_respects_order(self, tmp_data_dir):
        state = PipelineState.load("2026-05-30")
        assert state.can_proceed("S0") is True
        assert state.can_proceed("S1") is False  # S0 not done yet

        state.advance("S0")
        assert state.can_proceed("S1") is True
        assert state.can_proceed("S2") is False  # S1 not done

    def test_invalid_step_raises(self, tmp_data_dir):
        state = PipelineState.load("2026-05-30")
        with pytest.raises(ValueError, match="Unknown step"):
            state.advance("S99")

    def test_phase_determination(self):
        assert _determine_phase("S0") == "DATA"
        assert _determine_phase("S2.9") == "DATA"
        assert _determine_phase("S3") == "ANALYSIS_BUILD"
        assert _determine_phase("S10") == "ANALYSIS_BUILD"

    def test_resume_mid_session(self, tmp_data_dir):
        """Simulate context reset: save state, create new instance, resume."""
        state = PipelineState.load("2026-05-30")
        for step in ["S0", "S1", "S1e", "S2"]:
            state.advance(step)

        # Context reset — new instance loads from disk
        resumed = PipelineState.load("2026-05-30")
        assert resumed.position == "S2.3"
        assert resumed.can_proceed("S2.3") is True
        assert len(resumed.completed_steps) == 4

    def test_state_json_size_limit(self, tmp_data_dir):
        """State file should stay under 50 lines as per design."""
        state = PipelineState.load("2026-05-30")
        state.advance("S0", {"candidates": 45, "by_sport": {"football": 15}})
        state.add_decision("focus_corners")
        state.set_flag("odds_stale", False)

        path = tmp_data_dir / "2026-05-30_state.json"
        lines = path.read_text().count("\n")
        assert lines <= 50, f"State file has {lines} lines, should be ≤50"

    def test_date_validation_rejects_path_traversal(self, tmp_data_dir):
        """Dates with path separators must be rejected."""
        import pytest as pt
        with pt.raises(ValueError, match="Invalid date"):
            PipelineState.load("../etc/passwd")

    def test_advance_namespaces_summary_by_step(self, tmp_data_dir):
        """Each step's summary should be stored under its own key."""
        state = PipelineState.load("2026-05-30")
        state.advance("S0", {"pnl": 5.0})
        state.advance("S1", {"fixtures": 200})
        assert state.data_summary["S0"]["pnl"] == 5.0
        assert state.data_summary["S1"]["fixtures"] == 200
