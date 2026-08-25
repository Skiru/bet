"""Focused adversarial tests for mock/S9 production safety closure."""
from __future__ import annotations

import os
import json
from decimal import Decimal
from pathlib import Path
import pytest

from bet.pipeline.readiness_contracts import (
    get_central_safety_classification,
    CentralSafetyClassification,
    PipelineReadinessStatus,
)
from bet.pipeline.artifact_gate import (
    artifact_path_for,
    expected_s8_coupon_draft_path,
    get_final_betting_readiness,
    sha256_file,
    validate_pipeline_artifact,
    validate_s9_human_gate_artifact_for_run,
)
from scripts.coupon_builder import _bm


def test_01_bet_mock_odds_cannot_produce_betting_valid():
    os.environ["BET_MOCK_ODDS"] = "1"
    try:
        classification = get_central_safety_classification()
        assert classification.production_eligibility is False
        assert classification.runtime_classification == "TEST_ONLY_MOCK_ODDS"
        assert classification.betting_valid is False
        assert classification.can_place_bet_now is False
        assert classification.safe_user_action == "DO_NOT_PLACE_BET"
    finally:
        os.environ.pop("BET_MOCK_ODDS", None)


def test_02_bet_mock_now_cannot_produce_betting_valid():
    os.environ["BET_MOCK_NOW"] = "1"
    try:
        classification = get_central_safety_classification()
        assert classification.production_eligibility is False
        assert classification.runtime_classification == "TEST_ONLY_TIME_OVERRIDE"
        assert classification.can_place_bet_now is False
    finally:
        os.environ.pop("BET_MOCK_NOW", None)


def test_03_bet_pipeline_now_cannot_be_treated_as_live():
    os.environ["BET_PIPELINE_NOW"] = "1"
    try:
        classification = get_central_safety_classification()
        assert classification.production_eligibility is False
        assert classification.runtime_classification == "TEST_ONLY_TIME_OVERRIDE"
        assert classification.can_place_bet_now is False
    finally:
        os.environ.pop("BET_PIPELINE_NOW", None)


def test_07_mock_probability_not_promoted():
    # If a payload contains mock probability (0.85), it's detected and classified as synthetic input
    os.environ["BET_FORCE_MAGIC_VALUE_SCAN"] = "True"
    try:
        state = {
            "reviewed": {
                "cand-1": {
                    "probability": 0.85,
                    "best_market": {"name": "test", "probability": 0.85}
                }
            }
        }
        classification = get_central_safety_classification(state)
        assert classification.production_eligibility is False
        assert classification.runtime_classification == "TEST_ONLY_SYNTHETIC_INPUT"
        assert classification.betting_valid is False
    finally:
        os.environ.pop("BET_FORCE_MAGIC_VALUE_SCAN", None)


def test_08_09_synthetic_odds_and_ev_not_promoted():
    # Ev 0.15 and odds 2.10 are detected and quarantined
    os.environ["BET_FORCE_MAGIC_VALUE_SCAN"] = "True"
    try:
        state1 = {"reviewed": {"c1": {"best_odds": 2.10}}}
        state2 = {"reviewed": {"c1": {"ev": 0.15}}}

        classification1 = get_central_safety_classification(state1)
        classification2 = get_central_safety_classification(state2)

        assert classification1.production_eligibility is False
        assert classification1.runtime_classification == "TEST_ONLY_MOCK_ODDS"

        assert classification2.production_eligibility is False
        assert classification2.runtime_classification == "TEST_ONLY_SYNTHETIC_INPUT"
    finally:
        os.environ.pop("BET_FORCE_MAGIC_VALUE_SCAN", None)


def test_10_no_db_synthetic_inputs_are_test_only():
    os.environ["BET_NO_DB"] = "1"
    try:
        classification = get_central_safety_classification()
        assert classification.production_eligibility is False
        assert classification.runtime_classification == "TEST_ONLY_SYNTHETIC_INPUT"
    finally:
        os.environ.pop("BET_NO_DB", None)


def test_11_12_generated_s9_and_agent_s9_rejected():
    base_dir = Path("/tmp")
    raw = {
        "schema_version": 1,
        "artifact_type": "HUMAN_GATE",
        "step_id": "S9",
        "status": "HUMAN_APPROVED",
        "betting_day": "2026-07-11",
        "run_id": "run-test",
        "generated": True,  # synthetic/generated indicator
        "manual_review": {
            "reviewed_by_user": "shadow-acceptance",
            "reviewed_at_utc": "2026-07-11T12:00:00Z",
            "operator_workflow": "SUPERBET_MANUAL_BET_BUILDER",
            "coupon_draft_path": "/tmp/draft.json",
            "coupon_draft_sha256": "abc",
        }
    }
    issues = validate_s9_human_gate_artifact_for_run(raw, base_dir=base_dir, betting_day="2026-07-11", run_id="run-test")
    assert any(issue.code == "TEST_ONLY_GENERATED_HUMAN_GATE" for issue in issues)


def test_13_14_real_s9_fields_required_and_missing_rejected():
    base_dir = Path("/tmp")
    # Missing all Superbet manual quote fields
    raw = {
        "schema_version": 1,
        "artifact_type": "HUMAN_GATE",
        "step_id": "S9",
        "status": "HUMAN_APPROVED",
        "betting_day": "2026-07-11",
        "run_id": "run-test",
        "manual_review": {
            "reviewed_by_user": "human-operator",
            "reviewed_at_utc": "2026-07-11T12:00:00Z",
            "operator_workflow": "SUPERBET_MANUAL_BET_BUILDER",
            "coupon_draft_path": "/tmp/draft.json",
            "coupon_draft_sha256": "abc",
        }
    }
    issues = validate_s9_human_gate_artifact_for_run(raw, base_dir=base_dir, betting_day="2026-07-11", run_id="run-test")
    # Should flag missing visible market, line, quote, etc.
    codes = [issue.code for issue in issues]
    assert "MISSING_VISIBLE_MARKET" in codes
    assert "MISSING_VISIBLE_LINE" in codes
    assert "MISSING_HUMAN_QUOTE" in codes


def test_20_21_propagation_and_downstream_cannot_clear():
    # Verify that the central safety classification preserves reasons and does not clear them
    os.environ["BET_FORCE_MAGIC_VALUE_SCAN"] = "True"
    try:
        state = {
            "reviewed": {
                "cand-1": {
                    "ev": 0.15,
                    "test_only": True
                }
            }
        }
        classification = get_central_safety_classification(state)
        assert classification.production_eligibility is False
        assert classification.can_place_bet_now is False

        # Downstream serialization
        json_data = json.dumps(classification.to_jsonable())
        loaded = json.loads(json_data)
        assert loaded["production_eligibility"] is False
        assert loaded["can_place_bet_now"] is False
    finally:
        os.environ.pop("BET_FORCE_MAGIC_VALUE_SCAN", None)


def test_22_mixed_real_and_mock_fails_closed():
    # Payload with mixed valid and mock/synthetic entries
    os.environ["BET_FORCE_MAGIC_VALUE_SCAN"] = "True"
    try:
        state = {
            "reviewed": {
                "valid-cand": {
                    "probability": 0.54,
                    "odds_decimal": 1.95,
                },
                "mock-cand": {
                    "probability": 0.85,  # mock
                }
            }
        }
        classification = get_central_safety_classification(state)
        assert classification.production_eligibility is False
        assert classification.runtime_classification == "TEST_ONLY_SYNTHETIC_INPUT"
    finally:
        os.environ.pop("BET_FORCE_MAGIC_VALUE_SCAN", None)


def test_24_clean_unquoted_analytical_run():
    # If there are no mock/synthetic values, and no odds/quotes entered, it remains clean but unpriced (MANUAL_QUOTE_REQUIRED)
    state = {
        "reviewed": {
            "cand-1": {
                "probability": 0.62,
                "odds_decimal": 1.0,  # unpriced
            }
        }
    }
    classification = get_central_safety_classification(state)
    assert classification.production_eligibility is True
    assert classification.runtime_classification == "PRODUCTION_STABLE"
    assert classification.betting_valid is False
    assert classification.can_place_bet_now is False
    assert classification.safe_user_action == "CONTINUE_ANALYSIS_OR_REQUEST_MANUAL_QUOTE"


def test_26_production_code_contains_no_mock_injection():
    # Verify _bm fallback injection does NOT trigger if inject allowed is not explicitly True
    os.environ["BET_MOCK_ODDS"] = "1"
    import sys
    # Temporarily remove pytest from sys.modules to simulate production environment
    has_pytest = "pytest" in sys.modules
    if has_pytest:
        pytest_mod = sys.modules.pop("pytest")
    try:
        pick = {"market": "match_winner", "direction": "OVER"}
        _bm(pick)
        assert pick.get("best_market") is None
        assert "odds_decimal" not in pick
    finally:
        if has_pytest:
            sys.modules["pytest"] = pytest_mod
        os.environ.pop("BET_MOCK_ODDS", None)


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _valid_s9_run(tmp_path: Path) -> tuple[dict, Path]:
    day = "2026-07-11"
    run_id = "run-final"
    draft_path = expected_s8_coupon_draft_path(tmp_path, day, run_id)
    _write_json(draft_path, {
        "schema_version": 1,
        "artifact_type": "S8_COUPON_DRAFTS",
        "betting_day": day,
        "run_id": run_id,
        "requires_human_gate": True,
        "ready_for_human_gate": True,
        "ready_for_production_execution": False,
        "production_selectable": False,
        "production_coupon_write": False,
        "executable_coupon": False,
        "coupon_draft_count": 1,
        "drafts": [{"id": "quote-card-1"}],
    })
    digest = sha256_file(draft_path)
    raw = {
        "schema_version": 1,
        "artifact_type": "HUMAN_GATE",
        "step_id": "S9",
        "status": "HUMAN_APPROVED",
        "betting_day": day,
        "run_id": run_id,
        "checksum": digest,
        "manual_review": {
            "reviewed_by_user": "operator-user",
            "reviewed_at_utc": "2026-07-11T12:00:00Z",
            "operator_workflow": "SUPERBET_MANUAL_BET_BUILDER",
            "approval_origin": "HUMAN_OPERATOR",
            "visible_operator_market_name": "Match winner",
            "visible_operator_line": "Home",
            "human_entered_decimal_quote": 2.1,
            "quote_as_of": "2026-07-11T11:59:00Z",
            "source_quote_card_id": "quote-card-1",
            "explicit_operator_decision": "APPROVE",
            "coupon_draft_path": str(draft_path),
            "coupon_draft_sha256": digest,
        },
    }
    return raw, draft_path


def test_strict_superbet_s9_schema_and_generic_validator_agree(tmp_path: Path):
    raw, _ = _valid_s9_run(tmp_path)
    detailed = validate_s9_human_gate_artifact_for_run(
        raw, base_dir=tmp_path, betting_day="2026-07-11", run_id="run-final"
    )
    artifact, generic = validate_pipeline_artifact(raw, "S9")
    assert detailed == []
    assert generic == []
    assert artifact is not None
    assert "betclic_manual_verification" not in raw["manual_review"]

    invalid = json.loads(json.dumps(raw))
    del invalid["manual_review"]["operator_workflow"]
    assert "MISSING_S9_OPERATOR_WORKFLOW" in {issue.code for issue in validate_pipeline_artifact(invalid, "S9")[1]}
    assert "MISSING_S9_OPERATOR_WORKFLOW" in {
        issue.code for issue in validate_s9_human_gate_artifact_for_run(
            invalid, base_dir=tmp_path, betting_day="2026-07-11", run_id="run-final"
        )
    }


@pytest.mark.parametrize(
    ("field", "value", "expected_code"),
    [
        ("approval_origin", None, "INVALID_S9_ORIGIN"),
        ("visible_operator_market_name", "", "MISSING_VISIBLE_MARKET"),
        ("visible_operator_line", None, "MISSING_VISIBLE_LINE"),
        ("human_entered_decimal_quote", None, "MISSING_HUMAN_QUOTE"),
        ("human_entered_decimal_quote", 1.0, "INVALID_HUMAN_QUOTE"),
        ("quote_as_of", "", "MISSING_QUOTE_AS_OF"),
        ("source_quote_card_id", "", "MISSING_SOURCE_ID"),
    ],
)
def test_strict_superbet_required_quote_fields(tmp_path: Path, field: str, value: object, expected_code: str):
    raw, _ = _valid_s9_run(tmp_path)
    raw["manual_review"][field] = value
    issues = validate_s9_human_gate_artifact_for_run(
        raw, base_dir=tmp_path, betting_day="2026-07-11", run_id="run-final"
    )
    assert expected_code in {issue.code for issue in issues}


def test_missing_checksum_cannot_satisfy_superbet(tmp_path: Path):
    raw, _ = _valid_s9_run(tmp_path)
    del raw["checksum"]
    assert "MISSING_CHECKSUM" in {issue.code for issue in validate_pipeline_artifact(raw, "S9")[1]}


def test_generated_s9_blocks_s10_and_final_readiness(tmp_path: Path):
    raw, _ = _valid_s9_run(tmp_path)
    raw["generated"] = True
    raw["manual_review"]["reviewed_by_user"] = "shadow-acceptance"
    _write_json(artifact_path_for(tmp_path, "2026-07-11", "run-final", "S9"), raw)
    readiness = get_final_betting_readiness(base_dir=tmp_path, betting_day="2026-07-11", run_id="run-final")
    assert readiness.betting_valid is False
    assert readiness.can_place_bet_now is False


def test_magic_values_require_provenance_or_forced_diagnostic(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("BET_FORCE_MAGIC_VALUE_SCAN", raising=False)
    values = {"probability": 0.85, "odds_decimal": 2.10, "ev": 0.15}
    clean = get_central_safety_classification(values)
    contaminated = get_central_safety_classification({**values, "mock": True})
    assert clean.production_eligibility is True
    assert clean.betting_valid is False
    assert contaminated.production_eligibility is False


def test_only_valid_superbet_s9_enables_manual_placement(tmp_path: Path):
    clean = get_central_safety_classification({"odds_decimal": 2.1})
    assert clean.production_eligibility is True
    assert clean.can_place_bet_now is False

    raw, _ = _valid_s9_run(tmp_path)
    for step_id in ("S7", "S7b"):
        _write_json(artifact_path_for(tmp_path, "2026-07-11", "run-final", step_id), {
            "schema_version": 1,
            "artifact_type": "SCRIPT_EVIDENCE",
            "step_id": step_id,
            "status": "PASS",
            "betting_day": "2026-07-11",
            "run_id": "run-final",
        })
    _write_json(artifact_path_for(tmp_path, "2026-07-11", "run-final", "S9"), raw)
    readiness = get_final_betting_readiness(base_dir=tmp_path, betting_day="2026-07-11", run_id="run-final")
    assert readiness.production_eligibility is True
    assert readiness.betting_valid is True
    assert readiness.can_place_bet_now is True
    assert readiness.safe_user_action == "MANUAL_PLACEMENT_ALLOWED"
