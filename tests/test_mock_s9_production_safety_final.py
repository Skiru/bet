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
from bet.pipeline.artifact_gate import validate_s9_human_gate_artifact_for_run
from bet.pipeline.rich_coupon_package import build_rich_coupon_package
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


def test_04_to_06_mock_odds_force_zero_and_block_quote_review():
    os.environ["BET_MOCK_ODDS"] = "1"
    try:
        # Simulate a daily session state with mock odds
        packages, report = build_rich_coupon_package(
            betting_day="2026-07-11",
            session_id="session-test",
            session_ledger_path=Path("/tmp/mock_ledger.jsonl"),
            operator_name="Superbet",
        )
        assert report.classification == "TEST_ONLY_MOCK_ODDS"
        assert report.bettable_count == 0
        assert report.positive_ev_with_operator_odds_count == 0
        assert report.ready_for_manual_operator_quote_review is False
        assert report.can_place_bet_now is False
    finally:
        os.environ.pop("BET_MOCK_ODDS", None)


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


def test_15_betclic_evidence_cannot_satisfy_superbet():
    base_dir = Path("/tmp")
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
            "operator_workflow": "BETCLIC_MANUAL_WORKFLOW",  # Wrong workflow
            "coupon_draft_path": "/tmp/draft.json",
            "coupon_draft_sha256": "abc",
        }
    }
    issues = validate_s9_human_gate_artifact_for_run(raw, base_dir=base_dir, betting_day="2026-07-11", run_id="run-test")
    assert any(issue.code == "INVALID_S9_WORKFLOW" for issue in issues)


def test_16_17_s8_and_coupon_test_only_under_mock_odds():
    os.environ["BET_MOCK_ODDS"] = "1"
    try:
        packages, report = build_rich_coupon_package(
            betting_day="2026-07-11",
            session_id="session-test",
            session_ledger_path=Path("/tmp/mock_ledger.jsonl"),
            operator_name="Superbet",
        )
        assert report.classification == "TEST_ONLY_MOCK_ODDS"
        assert report.ready_for_production_coupon_building is False
    finally:
        os.environ.pop("BET_MOCK_ODDS", None)


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
    assert classification.betting_valid is True


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


def test_27_previous_run_classification():
    # The task-scoped audit artifact categorizes the historical 2026-07-10 run correctly
    audit_file = Path("reports/pipeline_runs/MOCK_S9_PRODUCTION_SAFETY_FINAL_CLOSURE/audit/invalidated_run_20260710.json")
    assert audit_file.exists()
    audit_data = json.loads(audit_file.read_text(encoding="utf-8"))
    assert audit_data["runtime_classification"] == "TEST_ONLY_SYNTHETIC_RUN"
    assert audit_data["betting_valid"] is False
    assert audit_data["can_place_bet_now"] is False
