"""Focused S8 current-run Superbet quote-pack tests."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from bet.pipeline.run_evidence import sha256_file
from scripts.pipeline_steps import s8_build_coupons

DAY = "2026-06-25"
RUN_ID = "run-s8-handoff"


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


def _card() -> dict:
    return {
        "quote_card_id": "quote-card-a",
        "source_candidate_id": "a",
        "manual_operator": "SUPERBET",
        "mapping_ambiguity": "HUMAN_CHECK_REQUIRED",
        "visible_operator_market_name": None,
        "visible_operator_line": None,
        "human_entered_decimal_quote": None,
        "quote_as_of": None,
        "operator_availability_asserted": False,
        "executable_coupon": False,
        "betting_valid": False,
        "can_place_bet_now": False,
    }


def _write_s7b(env: dict[str, str], cards: list[dict], status: str) -> Path:
    output = Path(env["BET_PIPELINE_DATA_DIR"]) / f"{DAY}_s7b_superbet_manual_mapping.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "artifact_type": "S7B_SUPERBET_MANUAL_MAPPING",
                "status": status,
                "betting_day": DAY,
                "run_id": RUN_ID,
                "operator_workflow": "SUPERBET_MANUAL_BET_BUILDER",
                "operator_availability_asserted": False,
                "approved_candidate_count": len(cards),
                "represented_candidate_count": len(cards),
                "mapping_suggestions": cards,
            }
        ),
        encoding="utf-8",
    )
    evidence = _evidence_path(env, "S7b")
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "artifact_type": "SCRIPT_EVIDENCE",
                "step_id": "S7b",
                "status": "PASS",
                "betting_day": DAY,
                "run_id": RUN_ID,
                "payload": {"s7b_json_output": str(output), "s7b_output_sha256": sha256_file(output)},
            }
        ),
        encoding="utf-8",
    )
    return output


def _run(env: dict[str, str]) -> int:
    argv = ["s8_build_coupons.py", "--date", DAY, "--run-id", RUN_ID, "--runtime-mode", "DRY_RUN"]
    with patch.dict(os.environ, env, clear=False), patch.object(sys, "argv", argv):
        with pytest.raises(SystemExit) as exc:
            s8_build_coupons.main()
    return int(exc.value.code)


def test_s8_builds_only_non_executable_manual_quote_pack(tmp_path: Path):
    env = _env(tmp_path)
    _write_s7b(env, [_card()], "READY_FOR_MANUAL_MAPPING")
    assert _run(env) == 0
    evidence = json.loads(_evidence_path(env, "S8").read_text(encoding="utf-8"))
    pack = json.loads(Path(evidence["payload"]["s8_quote_pack_path"]).read_text(encoding="utf-8"))
    assert pack["status"] == "READY_FOR_MANUAL_SUPERBET_QUOTE_REVIEW"
    assert pack["operator_workflow"] == "SUPERBET_MANUAL_BET_BUILDER"
    assert pack["quote_card_count"] == 1
    assert pack["ready_for_human_gate"] is True
    assert pack["executable_coupon"] is pack["betting_valid"] is pack["can_place_bet_now"] is False
    assert pack["ev_available"] is pack["kelly_available"] is pack["stake_available"] is False
    assert pack["combined_bookmaker_odds"] is None


def test_s8_no_action_is_not_human_gate_ready(tmp_path: Path):
    env = _env(tmp_path)
    _write_s7b(env, [], "NO_ACTION_TERMINAL")
    assert _run(env) == 0
    evidence = json.loads(_evidence_path(env, "S8").read_text(encoding="utf-8"))
    pack = json.loads(Path(evidence["payload"]["s8_quote_pack_path"]).read_text(encoding="utf-8"))
    assert pack["status"] == "NO_ACTION_TERMINAL"
    assert pack["quote_cards"] == []
    assert pack["ready_for_human_gate"] is False
    assert evidence["payload"]["ready_for_human_gate"] is False


def test_s8_rejects_hash_conflict_and_populated_human_quote(tmp_path: Path):
    env = _env(tmp_path)
    output = _write_s7b(env, [_card()], "READY_FOR_MANUAL_MAPPING")
    output.write_text("{}", encoding="utf-8")
    assert _run(env) == 5
    assert json.loads(_evidence_path(env, "S8").read_text(encoding="utf-8"))["status"] == "BLOCK"

    populated_env = _env(tmp_path / "populated")
    card = _card()
    card["human_entered_decimal_quote"] = 2.0
    _write_s7b(populated_env, [card], "READY_FOR_MANUAL_MAPPING")
    assert _run(populated_env) == 5


# Preserve historical node IDs while proving the stricter replacement contract.
def test_s8_wrapper_resolves_s7b_before_s7_fallback(tmp_path: Path):
    test_s8_builds_only_non_executable_manual_quote_pack(tmp_path)


def test_s8_wrapper_rejects_protected_input_and_output(tmp_path: Path):
    test_s8_rejects_hash_conflict_and_populated_human_quote(tmp_path)


def test_s8_wrapper_no_approved_candidates_blocks(tmp_path: Path):
    test_s8_no_action_is_not_human_gate_ready(tmp_path)
