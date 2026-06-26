"""Focused tests for S1 discovery wrapper evidence semantics."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.pipeline_steps import s1_discover


def _runtime_environ(tmp_path: Path, run_id: str = "run-s1") -> dict[str, str]:
    run_root = tmp_path / "sandbox"
    return {
        "BET_PIPELINE_RUNTIME_MODE": "LIVE_SHADOW",
        "BET_PIPELINE_BETTING_DAY": "2026-06-25",
        "BET_PIPELINE_RUN_ID": run_id,
        "BET_PIPELINE_RUN_ROOT": str(run_root),
        "BET_PIPELINE_DATA_DIR": str(run_root / "data"),
        "BET_PIPELINE_COUPON_DIR": str(run_root / "coupons"),
        "BET_PIPELINE_ARTIFACT_DIR": str(run_root / "artifacts"),
    }


def _evidence_path(tmp_path: Path, run_id: str = "run-s1") -> Path:
    return tmp_path / "sandbox" / "pipeline_runs" / "2026-06-25" / run_id / "artifacts" / "S1.json"


def _load_evidence(tmp_path: Path, run_id: str = "run-s1") -> dict:
    return json.loads(_evidence_path(tmp_path, run_id).read_text(encoding="utf-8"))


def test_s1_wrapper_success_writes_pass_script_evidence(tmp_path: Path):
    environ = _runtime_environ(tmp_path)
    argv = [
        "s1_discover.py",
        "--betting-day", "2026-06-25",
        "--run-id", "run-s1",
        "--runtime-mode", "LIVE_SHADOW",
        "--allow-live-network",
        "--dry-run",
    ]

    with patch.dict(os.environ, environ, clear=False), \
         patch.object(sys, "argv", argv), \
         patch("scripts.pipeline_steps.s1_discover._run_s1_scripts", return_value=0) as mock_run_scripts:
        with pytest.raises(SystemExit) as exc_info:
            s1_discover.main()

    assert exc_info.value.code == 0
    mock_run_scripts.assert_called_once()
    kwargs = mock_run_scripts.call_args.kwargs
    assert kwargs["date"] == "2026-06-25"
    assert kwargs["dry_run"] is True
    assert kwargs["allow_write"] is False
    assert kwargs["runtime_mode"] == "LIVE_SHADOW"
    assert kwargs["allow_live_network"] is True
    assert kwargs["child_env"]["BET_PIPELINE_RUN_ROOT"] == environ["BET_PIPELINE_RUN_ROOT"]
    assert kwargs["child_env"]["BET_PIPELINE_ARTIFACT_DIR"] == environ["BET_PIPELINE_ARTIFACT_DIR"]
    evidence = _load_evidence(tmp_path)
    assert evidence["artifact_type"] == "SCRIPT_EVIDENCE"
    assert evidence["step_id"] == "S1"
    assert evidence["status"] == "PASS"
    assert evidence["payload"] == {
        "discover_and_shortlist_rc": 0,
        "runtime_mode": "LIVE_SHADOW",
        "dry_run": True,
        "allow_write": False,
        "allow_live_network": True,
        "scripts": ["discover_events.py", "generate_market_matrix.py", "build_shortlist.py"],
        "production_write": False,
        "settled_runtime_path_source": "orchestrator_inherited_sandbox",
        "child_run_root": environ["BET_PIPELINE_RUN_ROOT"],
        "child_artifact_dir": environ["BET_PIPELINE_ARTIFACT_DIR"],
        "discovery_rc": -1,
        "market_matrix_rc": -1,
        "shortlist_rc": -1,
        "market_matrix_path": "",
        "market_matrix_event_count": 0,
        "market_matrix_schema_version": 1,
        "market_matrix_pipeline_safe": False,
        "market_matrix_validated": False,
        "shortlist_started": False
    }
    assert evidence["no_pick_edge_stake_coupon_emitted"] is True
    assert evidence["production_selectable"] is False
    assert evidence["betting_decisions_enabled"] is False
    evidence_path = _evidence_path(tmp_path)
    assert evidence_path.exists()
    assert str(evidence_path).startswith(str(tmp_path / "sandbox"))
    assert "/reports/" not in str(evidence_path)


def test_s1_wrapper_block_missing_market_matrix_writes_block_evidence(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    environ = _runtime_environ(tmp_path)
    argv = ["s1_discover.py", "--date", "2026-06-25", "--run-id", "run-s1", "--runtime-mode", "DRY_RUN", "--dry-run"]

    def _controlled_rc(*args, **kwargs):
        print("BLOCKED_MISSING_MARKET_MATRIX")
        return 2

    with patch.dict(os.environ, environ, clear=False), \
         patch.object(sys, "argv", argv), \
         patch("scripts.pipeline_steps.s1_discover._run_s1_scripts", side_effect=_controlled_rc):
        with pytest.raises(SystemExit) as exc_info:
            s1_discover.main()

    assert exc_info.value.code == 2
    captured = capsys.readouterr()
    assert "BLOCKED_MISSING_MARKET_MATRIX" in captured.out
    evidence = _load_evidence(tmp_path)
    assert evidence["status"] == "BLOCK"
    assert evidence["blocked_reasons"] == ["BLOCKED_MISSING_MARKET_MATRIX"]
    assert "/reports/" not in str(_evidence_path(tmp_path))


def test_s1_wrapper_duplicate_fixture_sources_writes_normalized_block_evidence(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    environ = _runtime_environ(tmp_path)
    argv = ["s1_discover.py", "--date", "2026-06-25", "--run-id", "run-s1", "--runtime-mode", "LIVE_SHADOW", "--allow-live-network", "--dry-run"]

    def _duplicate_mapping(*args, **kwargs):
        print("Duplicate fixture_sources mapping for source=api-football, external_id=1389107")
        print("migration preflight error")
        return 2

    with patch.dict(os.environ, environ, clear=False), \
         patch.object(sys, "argv", argv), \
         patch("scripts.pipeline_steps.s1_discover._run_s1_scripts", side_effect=_duplicate_mapping):
        with pytest.raises(SystemExit) as exc_info:
            s1_discover.main()

    assert exc_info.value.code == 2
    captured = capsys.readouterr()
    assert "Duplicate fixture_sources mapping" in captured.out
    evidence = _load_evidence(tmp_path)
    assert evidence["status"] == "BLOCK"
    assert "BLOCKED_FIXTURE_SOURCE_DUPLICATE_MAPPING" in evidence["blocked_reasons"]
    assert "BLOCKED_MIGRATION_PREFLIGHT" in evidence["blocked_reasons"]


def test_s1_wrapper_unexpected_return_code_writes_failed_evidence(tmp_path: Path):
    environ = _runtime_environ(tmp_path)
    argv = ["s1_discover.py", "--date", "2026-06-25", "--run-id", "run-s1", "--runtime-mode", "DRY_RUN", "--dry-run"]

    with patch.dict(os.environ, environ, clear=False), \
         patch.object(sys, "argv", argv), \
         patch("scripts.pipeline_steps.s1_discover._run_s1_scripts", return_value=42):
        with pytest.raises(SystemExit) as exc_info:
            s1_discover.main()

    assert exc_info.value.code == 42
    evidence = _load_evidence(tmp_path)
    assert evidence["status"] == "FAILED"
    assert evidence["blocked_reasons"] == ["FAILED_UNEXPECTED_SUBPROCESS_ERROR"]


def test_s1_wrapper_fail_closed_when_canonical_evidence_cannot_be_written(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    environ = _runtime_environ(tmp_path)
    argv = ["s1_discover.py", "--date", "2026-06-25", "--run-id", "run-s1", "--runtime-mode", "DRY_RUN", "--dry-run"]

    with patch.dict(os.environ, environ, clear=False), \
         patch.object(sys, "argv", argv), \
          patch("scripts.pipeline_steps.s1_discover._run_s1_scripts", return_value=0), \
          patch("scripts.pipeline_steps.s1_discover.write_script_evidence", return_value=None):
        with pytest.raises(SystemExit) as exc_info:
            s1_discover.main()

    assert exc_info.value.code == 70
    captured = capsys.readouterr()
    assert "runtime context missing for canonical S1 script evidence" in captured.err
