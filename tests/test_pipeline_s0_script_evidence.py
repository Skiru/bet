"""Focused tests for S0 settlement wrapper evidence semantics."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from bet.pipeline.orchestrator import Orchestrator
from bet.pipeline.integration_artifacts import write_script_evidence
from scripts.pipeline_steps import s0_settler


def _runtime_environ(tmp_path: Path, run_id: str = "run-s0") -> dict[str, str]:
    run_root = tmp_path / "sandbox"
    return {
        "BET_PIPELINE_RUNTIME_MODE": "DRY_RUN",
        "BET_PIPELINE_BETTING_DAY": "2026-06-25",
        "BET_PIPELINE_RUN_ID": run_id,
        "BET_PIPELINE_RUN_ROOT": str(run_root),
        "BET_PIPELINE_DATA_DIR": str(run_root / "betting" / "data"),
        "BET_PIPELINE_COUPON_DIR": str(run_root / "betting" / "coupons"),
        "BET_PIPELINE_ARTIFACT_DIR": str(run_root / "artifacts"),
    }


def _evidence_path(tmp_path: Path, run_id: str = "run-s0") -> Path:
    return tmp_path / "sandbox" / "pipeline_runs" / "2026-06-25" / run_id / "artifacts" / "S0.json"


def _load_evidence(tmp_path: Path, run_id: str = "run-s0") -> dict:
    return json.loads(_evidence_path(tmp_path, run_id).read_text(encoding="utf-8"))


def test_s0_wrapper_success_writes_pass_script_evidence(tmp_path: Path):
    environ = _runtime_environ(tmp_path)
    argv = ["s0_settler.py", "--date", "2026-06-25", "--run-id", "run-s0", "--runtime-mode", "DRY_RUN", "--dry-run"]

    with patch.dict(os.environ, environ, clear=False), \
         patch.object(sys, "argv", argv), \
         patch("scripts.pipeline_steps.s0_settler.run_scripts", return_value=0):
        with pytest.raises(SystemExit) as exc_info:
            s0_settler.main()

    assert exc_info.value.code == 0
    evidence = _load_evidence(tmp_path)
    assert evidence["artifact_type"] == "SCRIPT_EVIDENCE"
    assert evidence["step_id"] == "S0"
    assert evidence["status"] == "PASS"
    assert evidence["payload"] == {
        "settle_on_finish_rc": 0,
        "runtime_mode": "DRY_RUN",
        "dry_run": True,
        "allow_write": False,
        "allow_live_network": False,
        "settlement_execution": "sandboxed_live_shadow_or_dry_run",
        "production_write": False,
    }
    assert evidence["no_pick_edge_stake_coupon_emitted"] is True
    assert evidence["production_selectable"] is False
    assert evidence["betting_decisions_enabled"] is False


def test_s0_wrapper_controlled_return_code_writes_block_evidence(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    environ = _runtime_environ(tmp_path)
    argv = ["s0_settler.py", "--date", "2026-06-25", "--run-id", "run-s0", "--runtime-mode", "LIVE_SHADOW", "--allow-live-network", "--dry-run"]

    def _controlled_rc(*args, **kwargs):
        print("BLOCKED_SETTLEMENT_DATA_UNAVAILABLE")
        return 5

    with patch.dict(os.environ, environ, clear=False), \
         patch.object(sys, "argv", argv), \
         patch("scripts.pipeline_steps.s0_settler.run_scripts", side_effect=_controlled_rc):
        with pytest.raises(SystemExit) as exc_info:
            s0_settler.main()

    assert exc_info.value.code == 5
    captured = capsys.readouterr()
    assert "BLOCKED_SETTLEMENT_DATA_UNAVAILABLE" in captured.out
    evidence = _load_evidence(tmp_path)
    assert evidence["status"] == "BLOCK"
    assert evidence["blocked_reasons"] == ["BLOCKED_SETTLEMENT_DATA_UNAVAILABLE"]


def test_s0_wrapper_unexpected_return_code_writes_failed_evidence(tmp_path: Path):
    environ = _runtime_environ(tmp_path)
    argv = ["s0_settler.py", "--date", "2026-06-25", "--run-id", "run-s0", "--runtime-mode", "DRY_RUN", "--dry-run"]

    with patch.dict(os.environ, environ, clear=False), \
         patch.object(sys, "argv", argv), \
         patch("scripts.pipeline_steps.s0_settler.run_scripts", return_value=42):
        with pytest.raises(SystemExit) as exc_info:
            s0_settler.main()

    assert exc_info.value.code == 42
    evidence = _load_evidence(tmp_path)
    assert evidence["status"] == "FAILED"
    assert evidence["blocked_reasons"] == ["FAILED_UNEXPECTED_SUBPROCESS_ERROR"]


def test_s0_wrapper_accepts_orchestrator_runtime_arguments(tmp_path: Path):
    environ = _runtime_environ(tmp_path, run_id="run-args")
    argv = [
        "s0_settler.py",
        "--betting-day", "2026-06-25",
        "--run-id", "run-args",
        "--runtime-mode", "LIVE_SHADOW",
        "--allow-live-network",
        "--dry-run",
    ]

    with patch.dict(os.environ, environ, clear=False), \
         patch.object(sys, "argv", argv), \
         patch("scripts.pipeline_steps.s0_settler.run_scripts", return_value=0) as mock_run_scripts:
        with pytest.raises(SystemExit) as exc_info:
            s0_settler.main()

    assert exc_info.value.code == 0
    mock_run_scripts.assert_called_once_with(
        ["settle_on_finish.py"],
        date="2026-06-25",
        dry_run=True,
        allow_write=False,
        date_arg="--betting-day",
        runtime_mode="LIVE_SHADOW",
        betting_day="2026-06-25",
        run_id="run-args",
        allow_live_network=True,
    )


def test_orchestrator_s0_no_longer_blocks_on_missing_script_evidence_when_wrapper_writes_evidence(tmp_path: Path):
    orch = Orchestrator(
        betting_day="2026-06-25",
        run_id="run-orch-s0-pass",
        runtime_mode="DRY_RUN",
        base_run_dir=tmp_path / "sandbox",
        allow_live_network=False,
    )

    with patch("bet.pipeline.orchestrator.run_bounded_process") as mock_run:
        def side_effect(*args, **kwargs):
            write_script_evidence(
                "S0",
                status="PASS",
                payload={"test": True},
                sources=(),
                evidence_refs=(),
                environ=orch.env,
                no_pick_edge_stake_coupon_emitted=True,
                production_selectable=False,
                betting_decisions_enabled=False,
            )
            result = MagicMock()
            result.returncode = 0
            return result

        mock_run.side_effect = side_effect
        summary = orch.run(start_step="S0", stop_after_step="S0")

    assert summary["status"] == "PASS"
    assert summary["blocked_at_step"] is None
    assert not any("BLOCKED_SCRIPT_EVIDENCE_MISSING" in str(blocker) for blocker in summary["blockers"])
    s0_step = next(step for step in summary["steps"] if step["step_id"] == "S0")
    assert s0_step["status"] == "PASS"
    assert s0_step["evidence_path"]


def test_dry_run_s0_does_not_require_live_ack(tmp_path: Path):
    orch = Orchestrator(
        betting_day="2026-06-25",
        run_id="run-s0-dry-ack",
        runtime_mode="DRY_RUN",
        base_run_dir=tmp_path / "sandbox",
        allow_live_network=False,
    )

    with patch("bet.pipeline.orchestrator.run_bounded_process") as mock_run:
        def side_effect(*args, **kwargs):
            write_script_evidence(
                "S0",
                status="PASS",
                payload={"test": True},
                sources=(),
                evidence_refs=(),
                environ=orch.env,
                no_pick_edge_stake_coupon_emitted=True,
                production_selectable=False,
                betting_decisions_enabled=False,
            )
            result = MagicMock()
            result.returncode = 0
            return result

        mock_run.side_effect = side_effect
        summary = orch.run(start_step="S0", stop_after_step="S0")

    assert summary["status"] == "PASS"
    assert summary["last_completed_step"] == "S0"


def test_live_shadow_s0_without_ack_blocks_before_wrapper_execution(tmp_path: Path):
    with patch.dict(os.environ, {"BET_PIPELINE_LIVE_ACK": ""}):
        orch = Orchestrator(
            betting_day="2026-06-25",
            run_id="run-s0-live-no-ack",
            runtime_mode="LIVE_SHADOW",
            base_run_dir=tmp_path / "sandbox",
            allow_live_network=False,
        )
        with patch("bet.pipeline.orchestrator.run_bounded_process") as mock_run:
            summary = orch.run(start_step="S0", stop_after_step="S0")

    assert summary["status"] == "BLOCK"
    assert summary["blocked_at_step"] == "S0"
    assert any("live network acknowledgment missing" in blocker for blocker in summary["blockers"])
    mock_run.assert_not_called()


def test_live_shadow_s0_with_ack_reaches_wrapper_and_consumes_evidence(tmp_path: Path):
    with patch.dict(os.environ, {"BET_PIPELINE_LIVE_ACK": "I_UNDERSTAND_LIVE_PROVIDER_CALLS"}):
        orch = Orchestrator(
            betting_day="2026-06-25",
            run_id="run-s0-live-ack",
            runtime_mode="LIVE_SHADOW",
            base_run_dir=tmp_path / "sandbox",
            allow_live_network=True,
        )
        with patch("bet.pipeline.orchestrator.run_bounded_process") as mock_run:
            def side_effect(*args, **kwargs):
                write_script_evidence(
                    "S0",
                    status="BLOCK",
                    payload={"test": True},
                    sources=(),
                    evidence_refs=(),
                    environ=orch.env,
                    no_pick_edge_stake_coupon_emitted=True,
                    production_selectable=False,
                    betting_decisions_enabled=False,
                    blocked_reasons=("BLOCKED_SETTLEMENT_DATA_UNAVAILABLE",),
                )
                result = MagicMock()
                result.returncode = 5
                return result

            mock_run.side_effect = side_effect
            summary = orch.run(start_step="S0", stop_after_step="S0")

    assert summary["status"] == "BLOCK"
    assert summary["blocked_at_step"] == "S0"
    s0_step = next(step for step in summary["steps"] if step["step_id"] == "S0")
    assert s0_step["evidence_path"]
    assert any("BLOCKED_SETTLEMENT_DATA_UNAVAILABLE" in blocker for blocker in summary["blockers"])
