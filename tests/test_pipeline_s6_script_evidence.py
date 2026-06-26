"""Focused script evidence tests for S6 repeats wrapper."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.pipeline_steps import s6_repeats


def _runtime_environ(tmp_path: Path) -> dict[str, str]:
    run_root = Path("/tmp") / f"bet-s6-evidence-{tmp_path.name}"
    return {
        "BET_PIPELINE_RUNTIME_MODE": "DRY_RUN",
        "BET_PIPELINE_BETTING_DAY": "2026-06-25",
        "BET_PIPELINE_RUN_ID": "run-s6-evidence",
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
        / "S6.json"
    )


def test_s6_rejects_repo_local_input_or_output_in_non_production_runtime(tmp_path: Path):
    environ = _runtime_environ(tmp_path)
    repo_data_path = Path(__file__).resolve().parents[1] / "betting" / "data" / "some_input.json"
    
    argv = [
        "s6_repeats.py",
        "--date",
        "2026-06-25",
        "--run-id",
        environ["BET_PIPELINE_RUN_ID"],
        "--runtime-mode",
        "DRY_RUN",
        "--input",
        str(repo_data_path),
    ]

    with patch.dict(os.environ, environ, clear=False), patch.object(sys, "argv", argv):
        with pytest.raises(SystemExit) as exc_info:
            s6_repeats.main()

    assert exc_info.value.code == 5
    evidence_path = _canonical_evidence_path(environ)
    assert evidence_path.exists()
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert evidence["status"] == "BLOCK"
    assert "BLOCKED_REPEAT_GUARD_INPUT_MISSING" in evidence["blocked_reasons"]


def test_s6_missing_input_blocks_with_correct_evidence(tmp_path: Path):
    environ = _runtime_environ(tmp_path)
    # Ensure no candidates file exists under sandbox run
    data_dir = Path(environ["BET_PIPELINE_DATA_DIR"])
    data_dir.mkdir(parents=True, exist_ok=True)

    argv = [
        "s6_repeats.py",
        "--date",
        "2026-06-25",
        "--run-id",
        environ["BET_PIPELINE_RUN_ID"],
        "--runtime-mode",
        "DRY_RUN",
    ]

    with patch.dict(os.environ, environ, clear=False), patch.object(sys, "argv", argv):
        with pytest.raises(SystemExit) as exc_info:
            s6_repeats.main()

    assert exc_info.value.code == 5
    evidence_path = _canonical_evidence_path(environ)
    assert evidence_path.exists()
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert evidence["status"] == "BLOCK"
    assert "BLOCKED_REPEAT_GUARD_INPUT_MISSING" in evidence["blocked_reasons"]
    payload = evidence["payload"]
    assert payload["s6_input_path"] is None
    assert payload["checked_candidates_count"] == 0
