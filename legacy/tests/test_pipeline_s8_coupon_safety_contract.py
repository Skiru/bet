"""Focused S8 coupon safety contract tests."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from scripts.coupon_builder import build_coupon_drafts, _is_protected_repo_path


def test_build_coupon_drafts_artifact_conforms_to_safety_contract():
    # Simple mock gate payload
    gate_payload = {
        "gate_results": {
            "approved": [
                {
                    "home_team": "Alpha",
                    "away_team": "Beta",
                    "sport": "football",
                    "odds": {"market_best": 1.95},
                    "best_market": {
                        "name": "Goals Over 2.5",
                        "direction": "OVER",
                        "line": 2.5,
                        "safety_score": 0.85,
                        "probability": 0.85,
                    }
                },
                {
                    "home_team": "Gamma",
                    "away_team": "Delta",
                    "sport": "football",
                    "odds": {"market_best": 1.80},
                    "best_market": {
                        "name": "Goals Under 2.5",
                        "direction": "UNDER",
                        "line": 2.5,
                        "safety_score": 0.75,
                        "probability": 0.75,
                    }
                }
            ]
        }
    }

    artifact = build_coupon_drafts(
        gate_payload,
        betting_day="2026-06-25",
        run_id="run-s8-contract-test",
        runtime_mode="DRY_RUN",
        source_input_path="/tmp/mock_input.json"
    )

    # 1. Core artifact metadata assertions
    assert artifact["schema_version"] == 1
    assert artifact["artifact_type"] == "S8_COUPON_DRAFTS"
    assert artifact["betting_day"] == "2026-06-25"
    assert artifact["run_id"] == "run-s8-contract-test"
    assert artifact["runtime_mode"] == "DRY_RUN"
    assert artifact["source_input_path"] == "/tmp/mock_input.json"

    # 2. Strict safety contract assertions (Non-negotiables!)
    assert artifact["executable_coupon"] is False
    assert artifact["production_coupon_write"] is False
    assert artifact["betclic_execution_enabled"] is False
    assert artifact["requires_human_gate"] is True
    assert artifact["ready_for_human_gate"] is True
    assert artifact["ready_for_production_execution"] is False
    assert artifact["production_selectable"] is False

    # 3. Draft list assertions
    assert artifact["coupon_draft_count"] > 0
    assert len(artifact["drafts"]) > 0


def test_no_protected_writes_detection():
    # Verify that repo-local directories are correctly detected as protected
    assert _is_protected_repo_path("betting/data/some_file.json") is True
    assert _is_protected_repo_path("betting/coupons/some_coupon.md") is True
    assert _is_protected_repo_path("reports/pipeline_runs/some_run.json") is True

    # Temp folders are not protected
    assert _is_protected_repo_path("/tmp/some_file.json") is False
    assert _is_protected_repo_path("/var/folders/some_file.json") is False


def test_s8_output_path_run_scoped_contract():
    from scripts.pipeline_steps.s8_build_coupons import _s8_output_path
    from bet.pipeline.runtime_modes import RuntimeMode

    data_dir = Path("/tmp/run-root/data")
    for mode in [RuntimeMode.DRY_RUN, RuntimeMode.LIVE_SHADOW, RuntimeMode.CERTIFICATION, RuntimeMode.PRODUCTION]:
        path = _s8_output_path(data_dir, "2026-06-25", mode)
        assert str(path).startswith("/tmp/run-root")
        assert "/data/" in str(path)
        assert path.name == "2026-06-25_s8_superbet_manual_quote_pack.json"
