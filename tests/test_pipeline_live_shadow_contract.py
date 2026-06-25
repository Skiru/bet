"""Tests for LIVE_SHADOW safety contracts and guards."""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

from bet.pipeline.orchestrator import Orchestrator


def test_dry_run_default_does_not_require_live_ack(tmp_path):
    """Verify that DRY_RUN default runtime mode does not enforce or require live network ack."""
    orch = Orchestrator(
        betting_day="2026-06-25",
        run_id="run-999",
        runtime_mode="DRY_RUN",
        base_run_dir=tmp_path / "reports",
        allow_live_network=False,
    )
    # Check that execution does not crash or block because of live network ack
    # (Since S1e is state_only, it doesn't run live networks either way)
    summary = orch.run(start_step="S1e", stop_after_step="S1e")
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
        with patch("subprocess.run") as mock_run:
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
