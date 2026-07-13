"""Tests for LIVE_SHADOW safety contracts and guards."""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock
from unittest.mock import patch

from bet.pipeline.orchestrator import Orchestrator
from bet.pipeline.integration_artifacts import write_script_evidence


def test_dry_run_default_does_not_require_live_ack(tmp_path):
    """Verify that DRY_RUN default runtime mode does not enforce or require live network ack."""
    orch = Orchestrator(
        betting_day="2026-06-25",
        run_id="run-999",
        runtime_mode="DRY_RUN",
        base_run_dir=tmp_path / "reports",
        allow_live_network=False,
    )
    def side_effect(*args, **kwargs):
        write_script_evidence(
            "S0", status="PASS", payload={}, sources=(), evidence_refs=(), environ=orch.env
        )
        result = MagicMock()
        result.returncode = 0
        return result
    with patch("bet.pipeline.orchestrator.run_bounded_process", side_effect=side_effect):
        summary = orch.run(start_step="S0", stop_after_step="S0")
    assert summary["status"] == "PASS"


def test_live_shadow_without_ack_blocks(tmp_path):
    """Verify that LIVE_SHADOW mode blocks execution before invoking live wrappers when ack is missing."""
    # Let's run a live script step (S0) without live ack or network allowed
    with patch.dict(os.environ, {"BET_PIPELINE_LIVE_ACK": ""}):
        orch = Orchestrator(
            betting_day="2026-06-25",
            run_id="run-999",
            runtime_mode="LIVE_SHADOW",
            base_run_dir=tmp_path / "reports",
            allow_live_network=False,
        )
        summary = orch.run(start_step="S0", stop_after_step="S0")

    assert summary["status"] == "BLOCK"
    assert summary["blocked_at_step"] == "S0"
    assert any("live network acknowledgment missing" in b for b in summary["blockers"])


def test_live_shadow_with_ack_passes_guard(tmp_path):
    """Verify that LIVE_SHADOW passes the live guard when allow_live_network is True and ack env is set."""
    # Since S0 is script execution, we mock its execution so it passes cleanly when guard is passed
    with patch.dict(os.environ, {"BET_PIPELINE_LIVE_ACK": "I_UNDERSTAND_LIVE_PROVIDER_CALLS"}):
        orch = Orchestrator(
            betting_day="2026-06-25",
            run_id="run-999",
            runtime_mode="LIVE_SHADOW",
            base_run_dir=tmp_path / "reports",
            allow_live_network=True,
        )
        with patch("bet.pipeline.orchestrator.run_bounded_process") as mock_run:
            def side_effect(*args, **kwargs):
                from bet.pipeline.integration_artifacts import write_script_evidence
                write_script_evidence(
                    "S0",
                    status="PASS",
                    payload={"test": True},
                    sources=(),
                    evidence_refs=(),
                    environ=orch.env,
                )
                from unittest.mock import MagicMock
                m = MagicMock()
                m.returncode = 0
                return m
            mock_run.side_effect = side_effect
            summary = orch.run(start_step="S0", stop_after_step="S0")

    assert summary["status"] == "PASS"
    assert summary["last_completed_step"] == "S0"


def test_live_shadow_s1_without_ack_blocks_before_wrapper_execution(tmp_path):
    with patch.dict(os.environ, {"BET_PIPELINE_LIVE_ACK": ""}):
        orch = Orchestrator(
            betting_day="2026-06-25",
            run_id="run-s1-no-ack",
            runtime_mode="LIVE_SHADOW",
            base_run_dir=tmp_path / "sandbox",
            allow_live_network=False,
        )
        with patch("bet.pipeline.orchestrator.run_bounded_process") as mock_run:
            summary = orch.run(start_step="S1", stop_after_step="S1")

    assert summary["status"] == "BLOCK"
    assert summary["blocked_at_step"] == "S1"
    assert any("live network acknowledgment missing" in blocker for blocker in summary["blockers"])
    mock_run.assert_not_called()


def test_live_shadow_s1_with_ack_can_execute_wrapper(tmp_path):
    with patch.dict(os.environ, {"BET_PIPELINE_LIVE_ACK": "I_UNDERSTAND_LIVE_PROVIDER_CALLS"}):
        orch = Orchestrator(
            betting_day="2026-06-25",
            run_id="run-s1-live-ack",
            runtime_mode="LIVE_SHADOW",
            base_run_dir=tmp_path / "sandbox",
            allow_live_network=True,
        )
        with patch("bet.pipeline.orchestrator.run_bounded_process") as mock_run:
            def side_effect(*args, **kwargs):
                write_script_evidence(
                    "S1",
                    status="BLOCK",
                    payload={"test": True},
                    sources=(),
                    evidence_refs=(),
                    environ=orch.env,
                    no_pick_edge_stake_coupon_emitted=True,
                    production_selectable=False,
                    betting_decisions_enabled=False,
                    blocked_reasons=("BLOCKED_MISSING_MARKET_MATRIX",),
                )
                result = MagicMock()
                result.returncode = 2
                return result

            mock_run.side_effect = side_effect
            summary = orch.run(start_step="S1", stop_after_step="S1")

    assert summary["status"] == "BLOCK"
    assert summary["blocked_at_step"] == "S1"
    s1_step = next(step for step in summary["steps"] if step["step_id"] == "S1")
    assert s1_step["evidence_path"]
    assert not any("BLOCKED_SCRIPT_EVIDENCE_MISSING" in str(blocker) for blocker in summary["blockers"])
    mock_run.assert_called_once()
