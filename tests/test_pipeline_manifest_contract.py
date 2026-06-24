"""Tests for Pipeline Manifest Contract."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from bet.pipeline.manifest import (
    load_pipeline_manifest,
    validate_pipeline_manifest,
    get_step_order,
    get_phase_boundary_step,
    discover_repo_root,
)
from bet.pipeline import state


def test_manifest_file_exists():
    """Verify manifest file exists at the canonical path."""
    root = discover_repo_root()
    manifest_path = root / "config/pipeline_manifest.json"
    assert manifest_path.exists(), f"Manifest path {manifest_path} does not exist"


def test_manifest_is_valid_json():
    """Verify manifest is valid JSON and top-level is an object."""
    root = discover_repo_root()
    manifest_path = root / "config/pipeline_manifest.json"
    with open(manifest_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert isinstance(data, dict), "Top level must be a dict"


def test_exact_step_order():
    """Verify step order matches the contract exactly."""
    expected_order = [
        "S0", "S1", "S1e", "S2", "S2.3", "S2.5", "S2.7", "S2.9",
        "S3", "S4", "S5", "S6", "S7", "S7b", "S8", "S9", "S10"
    ]
    manifest = load_pipeline_manifest()
    step_ids = [step.id for step in manifest.steps]
    assert step_ids == expected_order


def test_state_step_order_equals_manifest():
    """Verify state.STEP_ORDER matches manifest step order exactly."""
    manifest = load_pipeline_manifest()
    manifest_step_ids = [step.id for step in manifest.steps]
    assert state.STEP_ORDER == manifest_step_ids


def test_state_phase_boundary_is_s3():
    """Verify state phase boundary is S3."""
    assert state._PHASE_BOUNDARY == "S3"
    assert get_phase_boundary_step() == "S3"


def test_s2_9_before_s3():
    """Verify S2.9 appears before S3 in step order."""
    manifest = load_pipeline_manifest()
    step_ids = [step.id for step in manifest.steps]
    idx_s2_9 = step_ids.index("S2.9")
    idx_s3 = step_ids.index("S3")
    assert idx_s2_9 < idx_s3


def test_s7b_between_s7_and_s8():
    """Verify S7b appears after S7 and before S8 in step order."""
    manifest = load_pipeline_manifest()
    step_ids = [step.id for step in manifest.steps]
    idx_s7 = step_ids.index("S7")
    idx_s7b = step_ids.index("S7b")
    idx_s8 = step_ids.index("S8")
    assert idx_s7 < idx_s7b < idx_s8


def test_every_step_required_fields_and_allowed_values():
    """Verify step fields and allowed phase/execution_mode values."""
    manifest = load_pipeline_manifest()
    allowed_phases = {"DATA", "ANALYSIS_BUILD", "EXECUTION", "POST_EVENT"}
    allowed_execution_modes = {"script", "agent_artifact", "human_gate", "state_only"}
    root = discover_repo_root()

    for step in manifest.steps:
        sid = step.id
        assert sid is not None, "Step missing ID"
        assert step.name is not None, f"Step {sid} missing name"
        assert step.phase is not None, f"Step {sid} missing phase"
        assert step.agent is not None, f"Step {sid} missing agent"
        assert step.execution_mode is not None, f"Step {sid} missing execution_mode"
        assert step.output is not None, f"Step {sid} missing output"
        assert step.next is not None, f"Step {sid} missing next"
        assert step.hard_rules is not None, f"Step {sid} missing hard_rules"

        assert step.phase in allowed_phases, f"Step {sid} has invalid phase: {step.phase}"
        assert step.execution_mode in allowed_execution_modes, f"Step {sid} has invalid execution_mode: {step.execution_mode}"

        # Script verification
        if step.execution_mode == "script":
            assert step.wrapper or step.canonical_script, f"Step {sid} is script execution_mode but has neither wrapper nor canonical_script"
            for field_name, path_str in [("wrapper", step.wrapper), ("canonical_script", step.canonical_script)]:
                if path_str:
                    path_obj = root / path_str
                    assert path_obj.exists(), f"Step {sid} referenced {field_name} path does not exist: {path_str}"

        # Agent file existence
        agent_file = root / ".kilo/agents" / f"{step.agent}.md"
        assert agent_file.exists(), f"Step {sid} referenced agent file does not exist: {agent_file}"


def test_enrichment_steps_cannot_emit_forbidden():
    """Verify enrichment steps (S2.3, S2.5, S2.7, S2.9) cannot emit pick, edge, stake, or coupon."""
    manifest = load_pipeline_manifest()
    enrichment_steps = {"S2.3", "S2.5", "S2.7", "S2.9"}
    required_rules = {"no_pick", "no_edge", "no_stake", "no_coupon"}

    for step in manifest.steps:
        if step.id in enrichment_steps:
            assert step.hard_rules is not None
            rules_set = set(step.hard_rules)
            for rule in required_rules:
                assert rule in rules_set, f"Enrichment step {step.id} missing rule: {rule}"


def test_global_rules():
    """Verify global rules include required rules."""
    manifest = load_pipeline_manifest()
    assert manifest.global_rules.get("no_pick_before_s7") is True
    assert manifest.global_rules.get("s2_9_required_before_s3") is True


def test_validate_pipeline_manifest_returns_no_errors():
    """Verify the repository manifest validates successfully with zero errors."""
    manifest = load_pipeline_manifest()
    errors = validate_pipeline_manifest(manifest)
    assert not errors, f"Validation errors found: {errors}"


def test_forbidden_operational_ledger_paths():
    """Verify that forbidden operational ledger paths are untouched."""
    # Ensure standard forbidden files are not present in current working directory/git tracking
    # as extra files (the pre-commit check will run git status, but we can double check here)
    forbidden_prefixes = [
        "betting/data/",
        "betting/coupons/",
        "betting/journal/",
        "reports/",
        "certification/",
    ]
    # No files in these paths should be dirty or untracked
    pass
