"""S7 valuation input provenance regression tests."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.pipeline_steps import s5_gate


def _runtime_environ(tmp_path: Path) -> dict[str, str]:
    run_root = Path("/tmp") / f"bet-s7-valuation-{tmp_path.name}"
    return {
        "BET_PIPELINE_RUNTIME_MODE": "DRY_RUN",
        "BET_PIPELINE_BETTING_DAY": "2026-06-25",
        "BET_PIPELINE_RUN_ID": "run-s7-valuation",
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
        / "S7.json"
    )


def _write_s6_pass_evidence(environ: dict[str, str], s6_output_path: Path | None = None) -> None:
    artifact_dir = Path(environ["BET_PIPELINE_ARTIFACT_DIR"])
    artifact_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "artifact_type": "SCRIPT_EVIDENCE",
        "step_id": "S6",
        "status": "PASS",
        "betting_day": "2026-06-25",
        "run_id": "run-s7-valuation",
        "payload": {
            "s6_output_path": str(s6_output_path) if s6_output_path else None,
        },
    }
    for path in (
        artifact_dir / "S6.json",
        Path(environ["BET_PIPELINE_RUN_ROOT"]) / "artifacts" / "S6.json"
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _s6_accepted_payload() -> dict:
    return {
        "schema_version": 1,
        "artifact_type": "S6_PORTFOLIO_REPEAT_GUARD_V2",
        "status": "PASS",
        "betting_day": "2026-06-25",
        "run_id": "run-s7-valuation",
        "accepted": [],
        "repeat_rejected": [],
        "correlation_rejected": [],
        "conflict_rejected": [],
        "portfolio_rejected": [],
        "invalid_input": [],
        "accounting": {
            "unaccounted_candidate_ids": [],
            "duplicate_candidate_ids": [],
            "overlapping_terminal_categories": []
        }
    }


def test_s7_prefers_s6_input_and_records_evidence(tmp_path: Path):
    environ = _runtime_environ(tmp_path)
    data_dir = Path(environ["BET_PIPELINE_DATA_DIR"])
    data_dir.mkdir(parents=True, exist_ok=True)
    s6_output_path = _write_json(data_dir / "repeat_loss_handoff_2026-06-25.json", _s6_accepted_payload())
    _write_s6_pass_evidence(environ, s6_output_path)

    argv = ["s5_gate.py", "--date", "2026-06-25", "--run-id", environ["BET_PIPELINE_RUN_ID"], "--runtime-mode", "DRY_RUN", "--dry-run"]
    with patch.dict(os.environ, environ, clear=False), patch.object(sys, "argv", argv), patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        with pytest.raises(SystemExit) as exc_info:
            s5_gate.main()

    assert exc_info.value.code == 0
    evidence = json.loads(_canonical_evidence_path(environ).read_text(encoding="utf-8"))
    assert Path(evidence["payload"]["s7_input_path"]).resolve() == s6_output_path.resolve()
    assert evidence["payload"]["s7_input_source_step"] == "S6"


def test_s7_blocks_when_s6_missing(tmp_path: Path):
    environ = _runtime_environ(tmp_path)
    argv = ["s5_gate.py", "--date", "2026-06-25", "--run-id", environ["BET_PIPELINE_RUN_ID"], "--runtime-mode", "DRY_RUN", "--dry-run"]

    with patch.dict(os.environ, environ, clear=False), patch.object(sys, "argv", argv):
        with pytest.raises(SystemExit) as exc_info:
            s5_gate.main()

    assert exc_info.value.code == 5
    evidence = json.loads(_canonical_evidence_path(environ).read_text(encoding="utf-8"))
    assert evidence["status"] == "BLOCK"
    assert evidence["blocked_reasons"] == ["BLOCKED_S7_S6_INPUT_MISSING"]
