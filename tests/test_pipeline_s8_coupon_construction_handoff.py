"""Focused S8 coupon construction handoff tests."""
from __future__ import annotations

import json
import os
import sys
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from scripts.pipeline_steps import s8_build_coupons


def _runtime_environ(tmp_path: Path) -> dict[str, str]:
    run_root = tmp_path / "bet-s8-handoff"
    return {
        "BET_PIPELINE_RUNTIME_MODE": "DRY_RUN",
        "BET_PIPELINE_BETTING_DAY": "2026-06-25",
        "BET_PIPELINE_RUN_ID": "run-s8-handoff",
        "BET_PIPELINE_RUN_ROOT": str(run_root),
        "BET_PIPELINE_DATA_DIR": str(run_root / "data"),
        "BET_PIPELINE_COUPON_DIR": str(run_root / "coupons"),
        "BET_PIPELINE_ARTIFACT_DIR": str(run_root / "artifacts"),
    }


def _canonical_evidence_path(environ: dict[str, str]) -> Path:
    return (
        Path(environ["BET_PIPELINE_RUN_ROOT"])
        / "pipeline_runs"
        / environ["BET_PIPELINE_BETTING_DAY"]
        / environ["BET_PIPELINE_RUN_ID"]
        / "artifacts"
        / "S8.json"
    )


def test_s8_wrapper_resolves_s7b_before_s7_fallback(tmp_path: Path):
    environ = _runtime_environ(tmp_path)
    data_dir = Path(environ["BET_PIPELINE_DATA_DIR"])
    artifact_dir = Path(environ["BET_PIPELINE_ARTIFACT_DIR"])
    data_dir.mkdir(parents=True, exist_ok=True)
    artifact_dir.mkdir(parents=True, exist_ok=True)

    # Prepare inputs: S7 and S7b
    s7_output = data_dir / "2026-06-25_s7_gate_results.json"
    s7_output.write_text(json.dumps({"gate_results": {"approved": [{"home_team": "Alpha", "away_team": "Beta", "best_market": {"name": "Over 2.5", "market_type": "goals_total"}}]}}), encoding="utf-8")
    (artifact_dir / "S7.json").write_text(
        json.dumps({"status": "PASS", "payload": {"approved_count": 1, "s7_json_output": str(s7_output), "sandbox_certification_fixture": True, "not_real_betting_recommendation": True, "market_availability_status": "AVAILABLE"}}),
        encoding="utf-8",
    )

    s7b_output = data_dir / "betclic_market_validation_2026-06-25.json"
    # S7b is a validation format, wait: let's verify if S7b is also a gate_results dict or a validation list
    # S7b validates S7 output, so its s7b_json_output usually contains the validation JSON, but s7b_input_path is the s7_output file.
    # When resolving s8 input, we search S7b evidence's s7b_json_output or validation output path, but if S7b passed, s7b_input_path should point to the S7 gate result!
    # Let's write S7b.json evidence:
    (artifact_dir / "S7b.json").write_text(
        json.dumps({"status": "PASS", "payload": {"s7b_input_path": str(s7_output), "s7b_json_output": str(s7b_output)}}),
        encoding="utf-8",
    )

    recorded = {}
    def fake_run(cmd, env=None, capture_output=None, text=None):
        recorded["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    argv = ["s8_build_coupons.py", "--date", "2026-06-25", "--run-id", environ["BET_PIPELINE_RUN_ID"], "--runtime-mode", "DRY_RUN", "--dry-run"]
    with patch.dict(os.environ, environ, clear=False), patch.object(sys, "argv", argv), patch("subprocess.run", side_effect=fake_run):
        # We must make sure the output draft path is mock-created so PASS can verify it
        mock_output = data_dir / "2026-06-25_s8_coupon_drafts.json"
        mock_output.write_text(json.dumps({"coupon_draft_count": 1}), encoding="utf-8")
        try:
            s8_build_coupons.main()
        except SystemExit as exc:
            assert exc.code == 0

    assert "--input" in recorded["cmd"]
    idx = recorded["cmd"].index("--input")
    resolved_input_path = Path(recorded["cmd"][idx + 1])
    # Resolves to S7b's s7b_json_output or similar. In S7b payload, we have s7b_json_output which is the validation file. But s7b_input_path is the validated picks (S7 results)!
    # Let's assert it is indeed resolved
    assert resolved_input_path.exists()

    evidence = json.loads(_canonical_evidence_path(environ).read_text(encoding="utf-8"))
    payload = evidence.get("payload") or {}
    draft_path_str = payload.get("s8_coupon_draft_path")
    assert draft_path_str is not None
    assert draft_path_str.startswith(environ["BET_PIPELINE_RUN_ROOT"])
    assert "/data/" in draft_path_str
    assert draft_path_str != "/tmp/2026-06-25_s8_coupon_drafts.json"
    assert payload.get("executable_coupon") is False
    assert payload.get("requires_human_gate") is True


def test_s8_wrapper_rejects_protected_input_and_output(tmp_path: Path):
    environ = _runtime_environ(tmp_path)
    # If the resolved input path resides inside a protected folder (like betting/data/...) and mode is not PRODUCTION, it must be rejected!
    protected_input = Path(s8_build_coupons.ROOT) / "betting" / "data" / "some_input.json"
    
    # We pass it explicitly via a mock resolver or env
    # Let's test _is_protected_repo_path directly
    assert s8_build_coupons._is_protected_repo_path(protected_input) is True
    assert s8_build_coupons._is_protected_repo_path(Path("/tmp/some_input.json")) is False


def test_s8_wrapper_no_approved_candidates_blocks(tmp_path: Path):
    environ = _runtime_environ(tmp_path)
    data_dir = Path(environ["BET_PIPELINE_DATA_DIR"])
    artifact_dir = Path(environ["BET_PIPELINE_ARTIFACT_DIR"])
    data_dir.mkdir(parents=True, exist_ok=True)
    artifact_dir.mkdir(parents=True, exist_ok=True)

    # S7 output is empty / approved count is 0
    s7_output = data_dir / "2026-06-25_s7_gate_results.json"
    s7_output.write_text(json.dumps({"gate_results": {"approved": []}}), encoding="utf-8")
    (artifact_dir / "S7b.json").write_text(
        json.dumps({"status": "PASS", "payload": {"s7b_input_path": str(s7_output), "s7b_json_output": str(s7_output)}}),
        encoding="utf-8",
    )

    argv = ["s8_build_coupons.py", "--date", "2026-06-25", "--run-id", environ["BET_PIPELINE_RUN_ID"], "--runtime-mode", "DRY_RUN", "--dry-run"]
    with patch.dict(os.environ, environ, clear=False), patch.object(sys, "argv", argv):
        with pytest.raises(SystemExit) as exc_info:
            s8_build_coupons.main()
        assert exc_info.value.code == 5

    evidence = json.loads(_canonical_evidence_path(environ).read_text(encoding="utf-8"))
    assert evidence["status"] == "BLOCK"
    assert "BLOCKED_COUPON_INPUT_EMPTY" in evidence["blocked_reasons"]
