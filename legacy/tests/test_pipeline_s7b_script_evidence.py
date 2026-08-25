"""Focused S7b current-run Superbet mapping tests."""
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

DAY = "2026-06-25"
RUN_ID = "run-s7b-script"


def _env(tmp_path: Path) -> dict[str, str]:
    run_root = tmp_path / "run"
    return {
        "BET_PIPELINE_RUNTIME_MODE": "DRY_RUN",
        "BET_PIPELINE_BETTING_DAY": DAY,
        "BET_PIPELINE_RUN_ID": RUN_ID,
        "BET_PIPELINE_RUN_ROOT": str(run_root),
        "BET_PIPELINE_DATA_DIR": str(run_root / "data"),
        "BET_PIPELINE_COUPON_DIR": str(run_root / "coupons"),
        "BET_PIPELINE_ARTIFACT_DIR": str(run_root / "artifacts"),
    }


def _evidence_path(env: dict[str, str], step: str) -> Path:
    return Path(env["BET_PIPELINE_RUN_ROOT"]) / "pipeline_runs" / DAY / RUN_ID / "artifacts" / f"{step}.json"


def _write_s7(env: dict[str, str], approved: list[dict], *, output_root: Path | None = None) -> Path:
    run_root = Path(env["BET_PIPELINE_RUN_ROOT"])
    output = (output_root or run_root) / "data" / f"{DAY}_s7_gate_results.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    canonical_approved = []
    for candidate in approved:
        legacy_id = str(candidate.get("candidate_id") or "candidate")
        prepared = {
            "sport": "football",
            "competition": "Test League",
            "kickoff": f"{DAY}T18:00:00Z",
            "home_team": f"Home {candidate.get('fixture_id') or legacy_id}",
            "away_team": f"Away {candidate.get('fixture_id') or legacy_id}",
            "market": "Match Winner",
            "selection": "HOME",
            **candidate,
        }
        canonical_approved.append(bind_candidate_identity(prepared))
    approved[:] = canonical_approved
    outcome = "READY_FOR_ANALYTICAL_OPERATOR_QUOTE_REVIEW" if approved else "NO_ACTION_TERMINAL"
    output.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "artifact_type": "S7_ANALYTICAL_APPROVAL_SET_V2",
                "status": "PASS",
                "outcome": outcome,
                "betting_day": DAY,
                "run_id": RUN_ID,
                "priced_approved": [],
                "analytical_approved": approved,
                "rejected": [],
            }
        ),
        encoding="utf-8",
    )
    evidence = _evidence_path(env, "S7")
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "artifact_type": "SCRIPT_EVIDENCE",
                "step_id": "S7",
                "status": "PASS",
                "betting_day": DAY,
                "run_id": RUN_ID,
                "payload": {
                    "s7_json_output": str(output),
                    "s7_output_sha256": sha256_file(output),
                    "approved_count": len(approved),
                },
            }
        ),
        encoding="utf-8",
    )
    return output


def _run(env: dict[str, str]) -> int:
    argv = ["s7_validate.py", "--date", DAY, "--run-id", RUN_ID, "--runtime-mode", "DRY_RUN"]
    with patch.dict(os.environ, env, clear=False), patch.object(sys, "argv", argv):
        with pytest.raises(SystemExit) as exc:
            s7_validate.main()
    return int(exc.value.code)


def test_s7b_maps_every_approved_candidate_once_with_blank_operator_fields(tmp_path: Path):
    env = _env(tmp_path)
    _write_s7(
        env,
        [
            {"candidate_id": "a", "fixture_id": "f1", "best_market": {"name": "Over 2.5", "line": 2.5}},
            {"candidate_id": "b", "fixture_id": "f2", "market": "Home win"},
        ],
    )

    assert _run(env) == 0
    evidence = json.loads(_evidence_path(env, "S7b").read_text(encoding="utf-8"))
    mapping = json.loads(Path(evidence["payload"]["s7b_json_output"]).read_text(encoding="utf-8"))
    assert mapping["approved_candidate_count"] == mapping["represented_candidate_count"] == 2
    source_ids = {card["source_candidate_id"] for card in mapping["mapping_suggestions"]}
    assert len(source_ids) == 2
    assert all(candidate_id.startswith("sel_") for candidate_id in source_ids)
    for card in mapping["mapping_suggestions"]:
        assert card["manual_operator"] == "SUPERBET"
        assert card["mapping_ambiguity"] == "HUMAN_CHECK_REQUIRED"
        assert all(card[field] is None for field in s7_validate.BLANK_OPERATOR_FIELDS)
        assert card["operator_availability_asserted"] is False
        assert card["executable_coupon"] is False


def test_s7b_zero_approval_is_valid_no_action(tmp_path: Path):
    env = _env(tmp_path)
    _write_s7(env, [])
    assert _run(env) == 0
    evidence = json.loads(_evidence_path(env, "S7b").read_text(encoding="utf-8"))
    mapping = json.loads(Path(evidence["payload"]["s7b_json_output"]).read_text(encoding="utf-8"))
    assert mapping["status"] == "NO_ACTION_TERMINAL"
    assert mapping["mapping_suggestions"] == []
    assert evidence["payload"]["ready_for_human_gate"] is False


def test_s7b_rejects_cross_run_output_and_duplicate_candidates(tmp_path: Path):
    env = _env(tmp_path)
    outside = tmp_path / "another-run"
    _write_s7(env, [{"candidate_id": "a"}], output_root=outside)
    assert _run(env) == 5
    assert json.loads(_evidence_path(env, "S7b").read_text(encoding="utf-8"))["status"] == "BLOCK"

    duplicate_env = _env(tmp_path / "duplicate")
    _write_s7(duplicate_env, [{"candidate_id": "a"}, {"candidate_id": "a"}])
    assert _run(duplicate_env) == 5


def test_s7b_superbet_mapping_preserves_blank_operator_fields(tmp_path: Path):
    test_s7b_maps_every_approved_candidate_once_with_blank_operator_fields(tmp_path)


def test_s7b_superbet_mapping_zero_approval_is_no_action(tmp_path: Path):
    test_s7b_zero_approval_is_valid_no_action(tmp_path)


def test_s7b_superbet_mapping_rejects_cross_run_output(tmp_path: Path):
    test_s7b_rejects_cross_run_output_and_duplicate_candidates(tmp_path)
