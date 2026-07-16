"""Focused S7b wrapper handoff tests."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from bet.pipeline.canonical_continuity import bind_candidate_identity
from bet.pipeline.run_evidence import sha256_file
from scripts.pipeline_steps import s7_validate


def _runtime_environ(tmp_path: Path) -> dict[str, str]:
    run_root = tmp_path / "bet-s7b-handoff"
    return {
        "BET_PIPELINE_RUNTIME_MODE": "DRY_RUN",
        "BET_PIPELINE_BETTING_DAY": "2026-06-25",
        "BET_PIPELINE_RUN_ID": "run-s7b-handoff",
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
        / "S7b.json"
    )


def test_s7b_wrapper_resolves_s7_output_and_passes_explicit_input(tmp_path: Path):
    environ = _runtime_environ(tmp_path)
    data_dir = Path(environ["BET_PIPELINE_DATA_DIR"])
    data_dir.mkdir(parents=True, exist_ok=True)

    candidate = bind_candidate_identity(
        {
            "home_team": "Alpha",
            "away_team": "Beta",
            "kickoff": "2026-06-25T20:00:00Z",
            "sport": "football",
            "competition": "Test League",
            "best_market": {"name": "Goals Total", "selection": "Over", "line": 2.5},
            "analytical_status": "ANALYTICAL_READY",
            "pricing_status": "PRICE_PENDING",
            "risk_flags": [],
            "counter_evidence": [],
        }
    )
    s7_output = data_dir / "2026-06-25_s7_gate_results.json"
    s7_output.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "artifact_type": "S7_ANALYTICAL_APPROVAL_SET_V2",
                "status": "PASS",
                "outcome": "READY_FOR_ANALYTICAL_OPERATOR_QUOTE_REVIEW",
                "betting_day": "2026-06-25",
                "run_id": "run-s7b-handoff",
                "priced_approved": [],
                "analytical_approved": [candidate],
                "rejected": [],
            }
        ),
        encoding="utf-8",
    )
    s7_evidence = (
        Path(environ["BET_PIPELINE_RUN_ROOT"])
        / "pipeline_runs/2026-06-25/run-s7b-handoff/artifacts/S7.json"
    )
    s7_evidence.parent.mkdir(parents=True, exist_ok=True)
    s7_evidence.write_text(
        json.dumps({
            "schema_version": 2,
            "artifact_type": "SCRIPT_EVIDENCE",
            "step_id": "S7",
            "status": "PASS",
            "betting_day": "2026-06-25",
            "run_id": "run-s7b-handoff",
            "payload": {
                "approved_count": 1,
                "s7_json_output": str(s7_output),
                "s7_output_sha256": sha256_file(s7_output),
            },
        }),
        encoding="utf-8",
    )

    argv = ["s7_validate.py", "--date", "2026-06-25", "--run-id", environ["BET_PIPELINE_RUN_ID"], "--runtime-mode", "DRY_RUN", "--dry-run"]
    with patch.dict(os.environ, environ, clear=False), patch.object(sys, "argv", argv):
        with pytest.raises(SystemExit) as exc_info:
            s7_validate.main()

    assert exc_info.value.code == 0
    evidence = json.loads(_canonical_evidence_path(environ).read_text(encoding="utf-8"))
    assert Path(evidence["payload"]["s7b_input_path"]).resolve() == s7_evidence.resolve()
    assert evidence["payload"]["s7b_json_output"].startswith(environ["BET_PIPELINE_RUN_ROOT"])


def test_s7b_wrapper_missing_s7_input_blocks(tmp_path: Path):
    environ = _runtime_environ(tmp_path)
    argv = ["s7_validate.py", "--date", "2026-06-25", "--run-id", environ["BET_PIPELINE_RUN_ID"], "--runtime-mode", "DRY_RUN", "--dry-run"]

    with patch.dict(os.environ, environ, clear=False), patch.object(sys, "argv", argv):
        with pytest.raises(SystemExit) as exc_info:
            s7_validate.main()

    assert exc_info.value.code == 5
    evidence = json.loads(_canonical_evidence_path(environ).read_text(encoding="utf-8"))
    assert evidence["status"] == "BLOCK"
    assert evidence["blocked_reasons"] == ["BLOCKED_S7B_CANONICAL_S7_MISSING"]
