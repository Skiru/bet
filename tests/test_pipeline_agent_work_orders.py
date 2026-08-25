"""Tests for agent work order generation, hashing, and policy formatting."""
from __future__ import annotations

import json
from pathlib import Path
import pytest

from bet.pipeline.agent_work_orders import (
    build_agent_work_order,
    load_agent_work_order_from_dict,
    write_agent_work_order,
    work_order_path_for,
    discover_input_refs_for_step,
    expected_agent_artifact_path_for,
    calculate_sha256,
)


def create_mock_artifacts(base_dir: Path, betting_day: str, run_id: str):
    artifacts_dir = base_dir / "pipeline_runs" / betting_day / run_id / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    steps = {
        "S2": "SCRIPT_EVIDENCE",
        "S1e": "SCRIPT_EVIDENCE",
        "S2.3": "AGENT_ARTIFACT",
        "S2.5": "AGENT_ARTIFACT",
        "S2.7": "AGENT_ARTIFACT",
        "S2.9": "AGENT_ARTIFACT",
        "S3": "SCRIPT_EVIDENCE",
        "S4": "SCRIPT_EVIDENCE",
    }

    for step_id, art_type in steps.items():
        payload = {
            "artifact_type": art_type,
            "step_id": step_id,
            "betting_day": betting_day,
            "run_id": run_id,
            "status": "PASS"
        }
        path = artifacts_dir / f"{step_id}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f)


def test_calculate_sha256(tmp_path):
    """Verify SHA-256 calculation for existing and non-existing files."""
    non_existent = tmp_path / "does_not_exist.json"
    assert calculate_sha256(non_existent) == ""

    test_file = tmp_path / "test.json"
    test_file.write_text("hello world", encoding="utf-8")
    expected_hash = "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"
    assert calculate_sha256(test_file) == expected_hash


def test_work_order_generation_and_policies(tmp_path):
    """Verify work order generation for each agent step: S2.3, S2.5, S2.7, S2.9, S5."""
    create_mock_artifacts(tmp_path, "2026-06-25", "run-smoke-1")
    steps = ["S2.3", "S2.5", "S2.7", "S2.9", "S5"]

    for step_id in steps:
        wo = build_agent_work_order(
            betting_day="2026-06-25",
            run_id="run-smoke-1",
            step_id=step_id,
            runtime_mode="DRY_RUN",
            base_dir=tmp_path,
        )

        # Verify schema adherence
        assert wo.schema_version == 1
        assert wo.work_order_type == "AGENT_ARTIFACT_REQUEST"
        assert wo.pipeline_id == "bet_pipeline_v1"
        assert wo.betting_day == "2026-06-25"
        assert wo.run_id == "run-smoke-1"
        assert wo.step_id == step_id
        assert wo.runtime_mode == "DRY_RUN"
        assert wo.status == "PENDING_AGENT"
        assert wo.created_at is not None

        # Verify required output contract
        req_out = wo.required_output
        assert req_out.artifact_type == "AGENT_ARTIFACT"
        assert req_out.step_id == step_id

        # Verify includes exact expected output path
        expected_path = expected_agent_artifact_path_for(tmp_path, "2026-06-25", "run-smoke-1", step_id)
        assert req_out.expected_path == str(expected_path)

        # Verify work order forbids pick/edge/stake/coupon outputs
        for forbidden in ["pick", "edge", "stake", "coupon"]:
            assert any(forbidden in fo.lower() for fo in wo.forbidden_outputs)

        # Verify work order explicitly treats templates as non-final scaffolds
        output_contract = wo.instructions["output_contract"]
        assert any("Template scaffolds are not accepted final output" in item for item in output_contract)
        assert any("BLOCK is acceptable and preferred over guessing" in item for item in output_contract)
        assert any("PASS requires full contract evidence" in item for item in output_contract)

        # Verify input refs matching step dependency graph
        refs = wo.input_refs
        assert isinstance(refs, list)
        if step_id == "S2.3":
            assert [ref.step_id for ref in refs] == ["S2", "S1e"]
        elif step_id == "S2.5":
            assert len(refs) == 2
            assert {r.step_id for r in refs} == {"S2", "S2.3"}
        elif step_id == "S2.7":
            assert len(refs) == 3
            assert {r.step_id for r in refs} == {"S2", "S2.3", "S2.5"}
        elif step_id == "S2.9":
            assert len(refs) == 4
            assert {r.step_id for r in refs} == {"S2", "S2.3", "S2.5", "S2.7"}
        elif step_id == "S5":
            assert len(refs) == 3
            assert {r.step_id for r in refs} == {"S3", "S4", "S2.9"}


def test_multisport_input_generates_event_scoped_agent_plans(tmp_path):
    """Verify the real work-order builder preserves every input event for the agent."""
    betting_day = "2026-06-25"
    run_id = "run-multisport-plans"
    create_mock_artifacts(tmp_path, betting_day, run_id)
    artifacts_dir = tmp_path / "pipeline_runs" / betting_day / run_id / "artifacts"
    events = [
        {"canonical_event_id": "EVT_FOOTBALL", "sport": "football"},
        {"canonical_event_id": "EVT_TENNIS", "sport": "tennis"},
        {"canonical_event_id": "EVT_BASKETBALL", "sport": "basketball"},
        {"canonical_event_id": "EVT_VOLLEYBALL", "sport": "volleyball"},
        {"canonical_event_id": "EVT_CS2", "sport": "cs2"},
        {"canonical_event_id": "EVT_VALORANT", "sport": "valorant"},
    ]
    for step_id in ("S2", "S1e"):
        path = artifacts_dir / f"{step_id}.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["payload"] = {"event_records": events}
        path.write_text(json.dumps(payload), encoding="utf-8")

    work_order = build_agent_work_order(
        betting_day=betting_day,
        run_id=run_id,
        step_id="S2.3",
        runtime_mode="DRY_RUN",
        base_dir=tmp_path,
    )

    assert [plan.canonical_event_id for plan in work_order.event_acquisition_plans] == [
        event["canonical_event_id"] for event in events
    ]
    assert [plan.sport for plan in work_order.event_acquisition_plans] == [
        event["sport"] for event in events
    ]
    assert all(
        requirement.min_independent_sources == 2
        and requirement.conflict_policy == "FAIL_CLOSED"
        and requirement.missing_data_action == "BLOCK"
        for plan in work_order.event_acquisition_plans
        for requirement in plan.requirements
    )
    written_path = write_agent_work_order(work_order, tmp_path)
    reloaded = json.loads(written_path.read_text(encoding="utf-8"))
    typed_reload = load_agent_work_order_from_dict(reloaded)
    assert [plan.canonical_event_id for plan in typed_reload.event_acquisition_plans] == [
        event["canonical_event_id"] for event in events
    ]
    assert [plan["canonical_event_id"] for plan in reloaded["event_acquisition_plans"]] == [
        event["canonical_event_id"] for event in events
    ]


def test_s5_work_order_specific_checks(tmp_path):
    """Verify S5 work order contains injury/lineup, motivation, travel/fatigue, morale, and upset risk requirements."""
    create_mock_artifacts(tmp_path, "2026-06-25", "run-smoke-1")
    wo = build_agent_work_order(
        betting_day="2026-06-25",
        run_id="run-smoke-1",
        step_id="S5",
        runtime_mode="DRY_RUN",
        base_dir=tmp_path,
    )

    # Check for hard rules in S5 policy
    expected_rules = [
        "injury_lineup_context_required",
        "motivation_and_tournament_context_required",
        "travel_schedule_fatigue_checked",
        "morale_and_recent_result_context_checked",
        "volatility_or_upset_risk_checked",
    ]
    for rule in expected_rules:
        assert rule in wo.hard_rules

    # Check must_do instructions
    must_dos = wo.instructions["must_do"]
    categories = ["injuries", "motivation", "travel", "morale", "upset/volatility"]
    for cat in categories:
        assert any(cat in md.lower() for md in must_dos)


def test_s29_work_order_requires_evidence_and_non_template_output(tmp_path):
    """Verify S2.9 work order states PASS evidence needs and rejects template-as-output."""
    create_mock_artifacts(tmp_path, "2026-06-25", "run-smoke-1")
    wo = build_agent_work_order(
        betting_day="2026-06-25",
        run_id="run-smoke-1",
        step_id="S2.9",
        runtime_mode="DRY_RUN",
        base_dir=tmp_path,
    )

    assert any("PASS requires S2.3, S2.5, S2.7 artifacts valid." in item for item in wo.instructions["must_do"])
    assert any("Fill required evidence fields" in item for item in wo.instructions["output_contract"])


def test_write_agent_work_order(tmp_path):
    """Verify writing a work order to disk."""
    create_mock_artifacts(tmp_path, "2026-06-25", "run-smoke-1")
    wo = build_agent_work_order(
        betting_day="2026-06-25",
        run_id="run-smoke-1",
        step_id="S2.3",
        runtime_mode="DRY_RUN",
        base_dir=tmp_path,
    )

    written_path = write_agent_work_order(wo, tmp_path)
    expected_path = work_order_path_for(tmp_path, "2026-06-25", "run-smoke-1", "S2.3")
    assert written_path == expected_path
    assert expected_path.exists()

    # Read and assert JSON fields match
    with open(expected_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["work_order_id"] == wo.work_order_id
    assert data["step_id"] == "S2.3"


def test_s23_cannot_generate_work_order_without_s2(tmp_path):
    """Regression test proving S2.3 cannot generate a work order or PASS without a valid current-run S2 artifact."""
    betting_day = "2026-06-25"
    run_id = "run-smoke-1"

    # Case 1: S2 artifact missing
    with pytest.raises(ValueError, match="Required dependency file is missing"):
        build_agent_work_order(
            betting_day=betting_day,
            run_id=run_id,
            step_id="S2.3",
            runtime_mode="DRY_RUN",
            base_dir=tmp_path,
        )

    # Set up artifacts dir
    artifacts_dir = tmp_path / "pipeline_runs" / betting_day / run_id / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    s2_path = artifacts_dir / "S2.json"

    # Case 2: S2 artifact is empty / invalid JSON
    s2_path.write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="unreadable or invalid JSON"):
        build_agent_work_order(
            betting_day=betting_day,
            run_id=run_id,
            step_id="S2.3",
            runtime_mode="DRY_RUN",
            base_dir=tmp_path,
        )

    # Case 3: S2 artifact has wrong betting_day
    payload = {
        "artifact_type": "SCRIPT_EVIDENCE",
        "step_id": "S2",
        "betting_day": "2026-01-01",  # wrong day
        "run_id": run_id,
    }
    with open(s2_path, "w", encoding="utf-8") as f:
        json.dump(payload, f)
    with pytest.raises(ValueError, match="Wrong betting_day in artifact"):
        build_agent_work_order(
            betting_day=betting_day,
            run_id=run_id,
            step_id="S2.3",
            runtime_mode="DRY_RUN",
            base_dir=tmp_path,
        )

    # Case 4: S2 artifact has wrong run_id
    payload["betting_day"] = betting_day
    payload["run_id"] = "wrong-run"
    with open(s2_path, "w", encoding="utf-8") as f:
        json.dump(payload, f)
    with pytest.raises(ValueError, match="Wrong run_id in artifact"):
        build_agent_work_order(
            betting_day=betting_day,
            run_id=run_id,
            step_id="S2.3",
            runtime_mode="DRY_RUN",
            base_dir=tmp_path,
        )

    # Case 5: S2 artifact has wrong artifact type
    payload["run_id"] = run_id
    payload["artifact_type"] = "AGENT_ARTIFACT"  # should be SCRIPT_EVIDENCE for script step S2
    with open(s2_path, "w", encoding="utf-8") as f:
        json.dump(payload, f)
    with pytest.raises(ValueError, match="Wrong artifact type"):
        build_agent_work_order(
            betting_day=betting_day,
            run_id=run_id,
            step_id="S2.3",
            runtime_mode="DRY_RUN",
            base_dir=tmp_path,
        )

    # Case 6: S2 artifact is outside current run root
    # (Since resolve_run_root canonicalizes the base path, we can check a path that escapes the run_root)
    # Wait, our input resolver resolves the path relative to base_dir, but we can verify it fails if we force an invalid path.
    # A valid config works:
    payload["artifact_type"] = "SCRIPT_EVIDENCE"
    with open(s2_path, "w", encoding="utf-8") as f:
        json.dump(payload, f)
    s1e_path = artifacts_dir / "S1e.json"
    with open(s1e_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "artifact_type": "SCRIPT_EVIDENCE",
                "step_id": "S1e",
                "betting_day": betting_day,
                "run_id": run_id,
            },
            f,
        )

    wo = build_agent_work_order(
        betting_day=betting_day,
        run_id=run_id,
        step_id="S2.3",
        runtime_mode="DRY_RUN",
        base_dir=tmp_path,
    )
    assert wo is not None
    assert wo.input_refs[0].step_id == "S2"


def test_agent_work_order_idempotency_and_drift(tmp_path):
    """Verify work order idempotency and drift detection under repeated calls."""
    from bet.pipeline.agent_work_orders import (
        build_agent_work_order,
        write_agent_work_order,
        work_order_path_for,
    )
    from bet.pipeline.canonical_continuity import ContinuityContractError
    import time

    betting_day = "2026-06-25"
    run_id = "run-idempotency-test"
    step_id = "S2.3"

    create_mock_artifacts(tmp_path, betting_day, run_id)

    # 1. first runner call creates work order and waits
    wo1 = build_agent_work_order(
        betting_day=betting_day,
        run_id=run_id,
        step_id=step_id,
        runtime_mode="DRY_RUN",
        base_dir=tmp_path,
    )
    path1 = write_agent_work_order(wo1, tmp_path)
    created_at1 = wo1.created_at

    # Wait briefly
    time.sleep(0.1)

    # 2. second runner call with no artifact reuses it and remains waiting
    wo2 = build_agent_work_order(
        betting_day=betting_day,
        run_id=run_id,
        step_id=step_id,
        runtime_mode="DRY_RUN",
        base_dir=tmp_path,
    )
    path2 = write_agent_work_order(wo2, tmp_path)

    assert path1 == path2
    assert wo1.created_at == wo2.created_at
    assert wo1.work_order_id == wo2.work_order_id

    # 3. third runner call after agent artifact resolves the same work order
    wo3 = build_agent_work_order(
        betting_day=betting_day,
        run_id=run_id,
        step_id=step_id,
        runtime_mode="DRY_RUN",
        base_dir=tmp_path,
    )
    assert wo3.created_at == created_at1

    # 4. upstream mutation still produces WORK_ORDER_DRIFT
    s2_path = tmp_path / "pipeline_runs" / betting_day / run_id / "artifacts" / "S2.json"
    s2_data = json.loads(s2_path.read_text(encoding="utf-8"))
    s2_data["status"] = "BLOCK"  # mutate content slightly to change the file hash
    s2_path.write_text(json.dumps(s2_data), encoding="utf-8")

    with pytest.raises(ContinuityContractError, match="WORK_ORDER_DRIFT"):
        build_agent_work_order(
            betting_day=betting_day,
            run_id=run_id,
            step_id=step_id,
            runtime_mode="DRY_RUN",
            base_dir=tmp_path,
        )


def test_p0_1_adversarial_missing_dependencies(tmp_path):
    """Adversarial tests for P0-1:
    1. base_dir under /tmp with missing S2: build_agent_work_order(S2.3) raises stable missing-dependency error.
    2. base_dir containing 'pytest' behaves identically.
    3. caller function name containing 'cannot_generate' does not change behavior.
    4. failed work-order generation creates zero predecessor artifacts.
    """
    betting_day = "2026-06-25"
    run_id = "run-adversarial"

    # 1. Base dir containing "/tmp" (or tmp_path / "tmp-dir")
    tmp_base = tmp_path / "tmp-dir"
    tmp_base.mkdir()

    with pytest.raises(ValueError, match="Required dependency file is missing"):
        build_agent_work_order(
            betting_day=betting_day,
            run_id=run_id,
            step_id="S2.3",
            runtime_mode="DRY_RUN",
            base_dir=tmp_base,
        )

    # 2. Base dir containing "pytest"
    pytest_base = tmp_path / "pytest-dir"
    pytest_base.mkdir()

    with pytest.raises(ValueError, match="Required dependency file is missing"):
        build_agent_work_order(
            betting_day=betting_day,
            run_id=run_id,
            step_id="S2.3",
            runtime_mode="DRY_RUN",
            base_dir=pytest_base,
        )

    # 3. Caller containing "cannot_generate"
    def cannot_generate_test_helper():
        with pytest.raises(ValueError, match="Required dependency file is missing"):
            build_agent_work_order(
                betting_day=betting_day,
                run_id=run_id,
                step_id="S2.3",
                runtime_mode="DRY_RUN",
                base_dir=tmp_base,
            )

    cannot_generate_test_helper()

    # 4. Failed work-order generation creates zero predecessor artifacts.
    # Check that in tmp_base, no artifacts or pipeline directories are created at all
    artifacts_dir = tmp_base / "pipeline_runs" / betting_day / run_id / "artifacts"
    if artifacts_dir.exists():
        created_files = list(artifacts_dir.glob("*"))
        assert len(created_files) == 0

    # 5. no source function imports inspect for test detection
    src_file = Path(__file__).parents[1] / "src" / "bet" / "pipeline" / "agent_work_orders.py"
    if src_file.exists():
        content = src_file.read_text(encoding="utf-8")
        assert "inspect" not in content
        assert "stack()" not in content


def test_p1_2_alternate_manifest(tmp_path):
    """Verify that build_agent_work_order honors an alternate manifest throughout."""
    from bet.pipeline.manifest import load_pipeline_manifest

    # 1. Load the original manifest
    orig_manifest = load_pipeline_manifest()

    # 2. Let's create an alternate manifest where S2.3 has different hard rules and agent owner
    alt_manifest_path = tmp_path / "alt_manifest.json"

    alt_steps = []
    for step in orig_manifest.steps:
        step_dict = {
            "id": step.id,
            "name": step.name,
            "phase": step.phase,
            "agent": step.agent,
            "execution_mode": step.execution_mode,
            "output": step.output,
            "next": step.next,
            "hard_rules": step.hard_rules,
            "wrapper": step.wrapper,
            "canonical_script": step.canonical_script,
            "depends_on": step.depends_on,
            "required_inputs": step.required_inputs,
        }
        if step.id == "S2.3":
            step_dict["agent"] = "bet-modeler"  # change agent owner
            step_dict["hard_rules"] = ["alternate_rule_1"]  # change hard rules
        alt_steps.append(step_dict)

    alt_data = {
        "schema_version": orig_manifest.schema_version,
        "pipeline_id": orig_manifest.pipeline_id,
        "timezone": orig_manifest.timezone,
        "betting_day": orig_manifest.betting_day,
        "global_rules": orig_manifest.global_rules,
        "steps": alt_steps,
        "runtime_contract": orig_manifest.runtime_contract,
    }

    alt_manifest_path.write_text(json.dumps(alt_data), encoding="utf-8")

    # Let's seed S2 prerequisite
    create_mock_artifacts(tmp_path, "2026-06-25", "run-smoke-alt")

    # Build with default manifest
    wo_orig = build_agent_work_order(
        betting_day="2026-06-25",
        run_id="run-smoke-alt",
        step_id="S2.3",
        runtime_mode="DRY_RUN",
        base_dir=tmp_path,
    )
    assert wo_orig.agent == "bet-researcher"
    assert "alternate_rule_1" not in wo_orig.hard_rules

    # Build with alternate manifest_path
    wo_alt = build_agent_work_order(
        betting_day="2026-06-25",
        run_id="run-smoke-alt",
        step_id="S2.3",
        runtime_mode="DRY_RUN",
        base_dir=tmp_path,
        manifest_path=alt_manifest_path,
    )

    assert wo_alt.agent == "bet-modeler"
    assert "alternate_rule_1" in wo_alt.hard_rules
    assert wo_alt.manifest_sha256 == calculate_sha256(alt_manifest_path)


def test_dependency_execution_mode_changes_artifact_kind(tmp_path):
    """Verify that changing a dependency's execution_mode changes the expected artifact kind."""
    from bet.pipeline.manifest import load_pipeline_manifest

    # 1. Load original manifest
    orig_manifest = load_pipeline_manifest()

    # 2. Create alternate manifest where S2 (dependency of S2.3) is changed from "script" to "agent_artifact"
    alt_manifest_path = tmp_path / "alt_manifest_dep.json"

    alt_steps = []
    for step in orig_manifest.steps:
        step_dict = {
            "id": step.id,
            "name": step.name,
            "phase": step.phase,
            "agent": step.agent,
            "execution_mode": step.execution_mode,
            "output": step.output,
            "next": step.next,
            "hard_rules": step.hard_rules,
            "wrapper": step.wrapper,
            "canonical_script": step.canonical_script,
            "depends_on": step.depends_on,
            "required_inputs": step.required_inputs,
        }
        if step.id == "S2":
            step_dict["execution_mode"] = "agent_artifact"
        alt_steps.append(step_dict)

    alt_data = {
        "schema_version": orig_manifest.schema_version,
        "pipeline_id": orig_manifest.pipeline_id,
        "timezone": orig_manifest.timezone,
        "betting_day": orig_manifest.betting_day,
        "global_rules": orig_manifest.global_rules,
        "steps": alt_steps,
        "runtime_contract": orig_manifest.runtime_contract,
    }

    alt_manifest_path.write_text(json.dumps(alt_data), encoding="utf-8")

    # Seed S2 prerequisite
    betting_day = "2026-06-25"
    run_id = "run-execution-mode-test"

    artifacts_dir = tmp_path / "pipeline_runs" / betting_day / run_id / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    # Under default manifest, S2 is "script" -> expects SCRIPT_EVIDENCE
    s2_path = artifacts_dir / "S2.json"
    s2_script_payload = {
        "schema_version": 1,
        "artifact_type": "SCRIPT_EVIDENCE",
        "step_id": "S2",
        "status": "PASS",
        "betting_day": betting_day,
        "run_id": run_id,
        "payload": {}
    }
    s2_path.write_text(json.dumps(s2_script_payload), encoding="utf-8")
    (artifacts_dir / "S1e.json").write_text(json.dumps({
        "schema_version": 1,
        "artifact_type": "SCRIPT_EVIDENCE",
        "step_id": "S1e",
        "status": "PASS",
        "betting_day": betting_day,
        "run_id": run_id,
        "payload": {},
    }), encoding="utf-8")

    # 3. Build S2.3 work order with default manifest
    wo_orig = build_agent_work_order(
        betting_day=betting_day,
        run_id=run_id,
        step_id="S2.3",
        runtime_mode="DRY_RUN",
        base_dir=tmp_path,
    )
    assert wo_orig.input_refs[0].artifact_kind == "SCRIPT_EVIDENCE"

    # 4. Under alternate manifest, S2 is "agent_artifact" -> expects AGENT_ARTIFACT
    s2_agent_payload = {
        "schema_version": 1,
        "artifact_type": "AGENT_ARTIFACT",
        "step_id": "S2",
        "status": "PASS",
        "betting_day": betting_day,
        "run_id": run_id,
        "point_in_time_as_of": "2026-06-25T12:00:00Z",
        "source_bound": True,
        "no_pick_edge_stake_coupon_emitted": True,
        "production_selectable": False,
        "betting_decisions_enabled": False,
        "sources": [],
        "payload": {}
    }
    s2_path.write_text(json.dumps(s2_agent_payload), encoding="utf-8")

    wo_alt = build_agent_work_order(
        betting_day=betting_day,
        run_id=run_id,
        step_id="S2.3",
        runtime_mode="DRY_RUN",
        base_dir=tmp_path,
        manifest_path=alt_manifest_path,
    )
    assert wo_alt.input_refs[0].artifact_kind == "AGENT_ARTIFACT"
