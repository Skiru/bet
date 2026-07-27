"""Complete production-path regression suite for S2 shortlist producer-consumer contract closure."""
from __future__ import annotations

import json
import os
from pathlib import Path
import pytest

from build_shortlist import write_shortlist_json
from bet.pipeline.integration_artifacts import (
    resolve_bound_step_output,
    strict_validate_step_output,
    write_script_evidence,
)
from bet.pipeline.manifest import load_pipeline_manifest
from bet.pipeline.run_evidence import sha256_file
from scripts.pipeline_steps._script_evidence import run_wrapper_scripts_with_evidence


def _setup_pipeline_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    run_root = Path("/tmp") / f"bet-s2-closure-{tmp_path.name}"
    data_dir = run_root / "data"
    artifacts_dir = run_root / "artifacts"
    coupon_dir = run_root / "coupons"
    data_dir.mkdir(parents=True, exist_ok=True)
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    coupon_dir.mkdir(parents=True, exist_ok=True)

    betting_day = "2026-07-26"
    run_id = "BET_LIVE_20260726_170814_a0906563_C8B6"

    monkeypatch.setenv("BET_PIPELINE_RUN_ROOT", str(run_root))
    monkeypatch.setenv("BET_PIPELINE_DATA_DIR", str(data_dir))
    monkeypatch.setenv("BET_PIPELINE_ARTIFACT_DIR", str(artifacts_dir))
    monkeypatch.setenv("BET_PIPELINE_COUPON_DIR", str(coupon_dir))
    monkeypatch.setenv("BET_PIPELINE_BETTING_DAY", betting_day)
    monkeypatch.setenv("BET_PIPELINE_RUN_ID", run_id)
    monkeypatch.setattr("build_shortlist.DATA_DIR", data_dir)

    selected = [
        (
            85.0,
            {
                "canonical_event_id": "evt_test123",
                "sport": "football",
                "home_team": "Team A",
                "away_team": "Team B",
                "competition": "Test League",
                "kickoff": "2026-07-26T20:00:00Z",
                "data_tier": "TIER1",
                "odds_markets": [],
                "safety_markets": [],
            },
        )
    ]

    s1e_file = data_dir / f"{betting_day}_s1e_event_universe.json"
    s1e_file.write_text(
        json.dumps({
            "schema_version": 1,
            "artifact_type": "S1E_EVENT_UNIVERSE_LEDGER",
            "betting_day": betting_day,
            "run_id": run_id,
            "canonical_event_ids": ["evt_test123"],
            "event_records": [{"canonical_event_id": "evt_test123", "terminal_status": "CONTINUE"}],
        }),
        encoding="utf-8",
    )

    return run_root, data_dir, artifacts_dir, betting_day, run_id, selected


def test_real_s2_writer_contract(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A. Real S2 writer contract test."""
    run_root, data_dir, artifacts_dir, betting_day, run_id, selected = _setup_pipeline_env(tmp_path, monkeypatch)

    shortlist_path = write_shortlist_json(selected, date=betting_day)
    assert shortlist_path.exists()

    s2_data = json.loads(shortlist_path.read_text(encoding="utf-8"))
    assert s2_data["artifact_type"] == "S2_SHORTLIST"
    assert s2_data["schema_version"] == 1
    assert s2_data["betting_day"] == betting_day
    assert s2_data["total_candidates"] == len(selected)
    assert s2_data["total_candidates"] == len(s2_data["candidates"])
    assert "sports" in s2_data
    assert "selection_telemetry" in s2_data


def test_real_producer_to_real_consumer_pass(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """B. Real producer -> real consumer integration test."""
    run_root, data_dir, artifacts_dir, betting_day, run_id, selected = _setup_pipeline_env(tmp_path, monkeypatch)

    shortlist_path = write_shortlist_json(selected, date=betting_day)
    assert shortlist_path.exists()

    def _mock_run_scripts(*args, **kwargs):
        return 0

    monkeypatch.setattr("scripts.pipeline_steps._script_evidence.run_scripts", _mock_run_scripts)

    with pytest.raises(SystemExit) as exc_info:
        run_wrapper_scripts_with_evidence(
            step_id="S2",
            wrapper_scripts=["tipster_aggregator.py"],
            date=betting_day,
            dry_run=True,
            allow_write=False,
            runtime_mode="DRY_RUN",
            betting_day=betting_day,
            run_id=run_id,
            allow_live_network=False,
        )
    assert exc_info.value.code == 0

    resolved_path, resolved_data = resolve_bound_step_output(
        run_root=str(run_root),
        step_id="S2",
        betting_day=betting_day,
        run_id=run_id,
        expected_artifact_type="S2_SHORTLIST",
    )
    assert resolved_path.resolve() == shortlist_path.resolve()
    assert resolved_data["artifact_type"] == "S2_SHORTLIST"
    assert "event_records" in resolved_data


def test_negative_missing_type_rejection(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """C. Negative missing-type test."""
    run_root, data_dir, artifacts_dir, betting_day, run_id, selected = _setup_pipeline_env(tmp_path, monkeypatch)

    shortlist_path = write_shortlist_json(selected, date=betting_day)
    s2_data = json.loads(shortlist_path.read_text(encoding="utf-8"))
    s2_data.pop("artifact_type", None)
    shortlist_path.write_text(json.dumps(s2_data), encoding="utf-8")

    s2_sha = sha256_file(shortlist_path)
    write_script_evidence(
        step_id="S2",
        status="PASS",
        payload={
            "s2_shortlist_path": str(shortlist_path),
            "s2_output_path": str(shortlist_path),
            "s2_output_sha256": s2_sha,
            "event_records": [{"canonical_event_id": "evt_test123", "terminal_status": "CONTINUE", "reason_codes": [], "candidate_ids": []}],
        },
        sources=("scripts/build_shortlist.py",),
        evidence_refs=(),
        environ={
            "BET_PIPELINE_RUN_ROOT": str(run_root),
            "BET_PIPELINE_DATA_DIR": str(data_dir),
            "BET_PIPELINE_ARTIFACT_DIR": str(artifacts_dir),
            "BET_PIPELINE_BETTING_DAY": betting_day,
            "BET_PIPELINE_RUN_ID": run_id,
        },
        no_pick_edge_stake_coupon_emitted=True,
    )

    with pytest.raises(ValueError) as exc_info:
        resolve_bound_step_output(
            run_root=str(run_root),
            step_id="S2",
            betting_day=betting_day,
            run_id=run_id,
            expected_artifact_type="S2_SHORTLIST",
        )
    assert "STEP_TYPE_MISMATCH" in str(exc_info.value) or "Artifact type mismatch" in str(exc_info.value)


def test_wrong_type_rejection(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """D. Wrong-type test."""
    run_root, data_dir, artifacts_dir, betting_day, run_id, selected = _setup_pipeline_env(tmp_path, monkeypatch)

    shortlist_path = write_shortlist_json(selected, date=betting_day)
    s2_data = json.loads(shortlist_path.read_text(encoding="utf-8"))
    s2_data["artifact_type"] = "FOREIGN_ARTIFACT_TYPE"
    shortlist_path.write_text(json.dumps(s2_data), encoding="utf-8")

    s2_sha = sha256_file(shortlist_path)
    write_script_evidence(
        step_id="S2",
        status="PASS",
        payload={
            "s2_shortlist_path": str(shortlist_path),
            "s2_output_path": str(shortlist_path),
            "s2_output_sha256": s2_sha,
            "event_records": [{"canonical_event_id": "evt_test123", "terminal_status": "CONTINUE", "reason_codes": [], "candidate_ids": []}],
        },
        sources=("scripts/build_shortlist.py",),
        evidence_refs=(),
        environ={
            "BET_PIPELINE_RUN_ROOT": str(run_root),
            "BET_PIPELINE_DATA_DIR": str(data_dir),
            "BET_PIPELINE_ARTIFACT_DIR": str(artifacts_dir),
            "BET_PIPELINE_BETTING_DAY": betting_day,
            "BET_PIPELINE_RUN_ID": run_id,
        },
        no_pick_edge_stake_coupon_emitted=True,
    )

    with pytest.raises(ValueError) as exc_info:
        resolve_bound_step_output(
            run_root=str(run_root),
            step_id="S2",
            betting_day=betting_day,
            run_id=run_id,
            expected_artifact_type="S2_SHORTLIST",
        )
    assert "STEP_TYPE_MISMATCH" in str(exc_info.value) or "Artifact type mismatch" in str(exc_info.value)


def test_hash_mutation_rejection(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """E. Hash mutation test."""
    run_root, data_dir, artifacts_dir, betting_day, run_id, selected = _setup_pipeline_env(tmp_path, monkeypatch)

    shortlist_path = write_shortlist_json(selected, date=betting_day)
    original_sha = sha256_file(shortlist_path)

    write_script_evidence(
        step_id="S2",
        status="PASS",
        payload={
            "s2_shortlist_path": str(shortlist_path),
            "s2_output_path": str(shortlist_path),
            "s2_output_sha256": original_sha,
            "event_records": [{"canonical_event_id": "evt_test123", "terminal_status": "CONTINUE", "reason_codes": [], "candidate_ids": []}],
        },
        sources=("scripts/build_shortlist.py",),
        evidence_refs=(),
        environ={
            "BET_PIPELINE_RUN_ROOT": str(run_root),
            "BET_PIPELINE_DATA_DIR": str(data_dir),
            "BET_PIPELINE_ARTIFACT_DIR": str(artifacts_dir),
            "BET_PIPELINE_BETTING_DAY": betting_day,
            "BET_PIPELINE_RUN_ID": run_id,
        },
        no_pick_edge_stake_coupon_emitted=True,
    )

    # Mutate output file after evidence creation
    s2_data = json.loads(shortlist_path.read_text(encoding="utf-8"))
    s2_data["mutated"] = True
    shortlist_path.write_text(json.dumps(s2_data), encoding="utf-8")

    with pytest.raises(ValueError) as exc_info:
        resolve_bound_step_output(
            run_root=str(run_root),
            step_id="S2",
            betting_day=betting_day,
            run_id=run_id,
            expected_artifact_type="S2_SHORTLIST",
        )
    assert "STEP_OUTPUT_HASH_MISMATCH" in str(exc_info.value) or "SHA-256 mismatch" in str(exc_info.value)


def test_s2_wrapper_gate_blocks_malformed_producer_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """F. S2 wrapper gate test."""
    run_root, data_dir, artifacts_dir, betting_day, run_id, selected = _setup_pipeline_env(tmp_path, monkeypatch)

    # Write malformed shortlist (missing artifact_type)
    shortlist_path = data_dir / f"{betting_day}_s2_shortlist.json"
    shortlist_path.write_text(json.dumps({"total_candidates": 1, "candidates": []}), encoding="utf-8")

    def _mock_run_scripts(*args, **kwargs):
        return 0

    monkeypatch.setattr("scripts.pipeline_steps._script_evidence.run_scripts", _mock_run_scripts)

    with pytest.raises(SystemExit) as exc_info:
        run_wrapper_scripts_with_evidence(
            step_id="S2",
            wrapper_scripts=["tipster_aggregator.py"],
            date=betting_day,
            dry_run=True,
            allow_write=False,
            runtime_mode="DRY_RUN",
            betting_day=betting_day,
            run_id=run_id,
            allow_live_network=False,
        )
    assert exc_info.value.code != 0

    s2_ev_file = artifacts_dir / "S2.json"
    assert s2_ev_file.exists()
    s2_ev = json.loads(s2_ev_file.read_text(encoding="utf-8"))
    assert s2_ev["status"] == "BLOCK"
    assert "BLOCKED_S2_SHORTLIST_INVALID" in s2_ev.get("blocked_reasons", [])


def test_full_script_contract_matrix():
    """G. Full script contract matrix validation against manifest."""
    repo_root = Path(__file__).resolve().parents[1]
    manifest = load_pipeline_manifest(repo_root / "config/pipeline_manifest.json")

    script_steps = [step for step in manifest.steps if step.execution_mode == "script"]
    assert len(script_steps) >= 5

    expected_types = {
        "S1e": "S1E_EVENT_UNIVERSE_LEDGER",
        "S2": "S2_SHORTLIST",
        "S3": "S3_DEEP_STATS",
        "S4": "S4_VALUATION_CANDIDATE_SET_V2",
        "S6": "S6_PORTFOLIO_REPEAT_GUARD_V2",
        "S7": "S7_ANALYTICAL_APPROVAL_SET_V2",
        "S7b": "S7B_SUPERBET_MANUAL_MAPPING",
        "S8": "S8_SUPERBET_MANUAL_QUOTE_PACK",
    }

    for step in script_steps:
        if step.id in expected_types:
            assert step.wrapper is not None
            assert (repo_root / step.wrapper).exists()
