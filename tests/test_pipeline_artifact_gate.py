"""Tests for pipeline artifact gate validation and pre-requisite step checking."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bet.pipeline.artifact_gate import (
    artifact_path_for,
    detect_secrets,
    evaluate_gate_before_step,
    expected_s8_coupon_draft_path,
    find_forbidden_decision_signals,
    load_artifact,
    sha256_file,
    validate_pipeline_artifact,
)
from bet.pipeline.readiness_contracts import PipelineReadinessStatus


def base_artifact(
    step_id: str = "S2.9",
    artifact_type: str = "AGENT_ARTIFACT",
    status: str = "PASS",
) -> dict[str, object]:
    """Build a baseline artifact aligned with the main-aware readiness contract."""
    return {
        "schema_version": 1,
        "artifact_type": artifact_type,
        "step_id": step_id,
        "status": status,
        "betting_day": "2026-06-25",
        "run_id": "run-001",
        "sport": "Football",
        "fixture_id": None,
        "fixture_key": None,
        "point_in_time_as_of": "2026-06-25T12:00:00Z",
        "source_bound": True,
        "no_pick_edge_stake_coupon_emitted": True,
        "production_selectable": False,
        "betting_decisions_enabled": False,
        "sources": ["merged-main-enrichment-shadow-foundation"],
        "unknowns": [],
        "blocked_reasons": [],
        "evidence_refs": ["Betclic market validation evidence event"],
        "payload": {
            "provider_authorization_status": "BLOCKED_NO_CREDENTIALS",
            "single_flight_probe": "Betclic market validation evidence event",
            "production_selectable": False,
            "betting_decisions_enabled": False,
        },
    }


def write_artifact(root: Path, artifact: dict[str, object]) -> Path:
    """Write a pipeline artifact to its canonical location for gate tests."""
    path = artifact_path_for(
        root,
        str(artifact["betting_day"]),
        str(artifact["run_id"]),
        str(artifact["step_id"]),
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(artifact), encoding="utf-8")
    return path


def write_s8_coupon_draft(root: Path, betting_day: str, run_id: str) -> Path:
    """Write a canonical safe S8 draft artifact for S9/S10 gate tests."""
    path = expected_s8_coupon_draft_path(root, betting_day, run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "artifact_type": "S8_COUPON_DRAFTS",
                "betting_day": betting_day,
                "run_id": run_id,
                "requires_human_gate": True,
                "ready_for_human_gate": True,
                "ready_for_production_execution": False,
                "production_selectable": False,
                "production_coupon_write": False,
                "executable_coupon": False,
                "betclic_execution_enabled": False,
                "coupon_draft_count": 1,
                "drafts": [{"id": "quote-card-1"}],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_load_artifact_fails_closed(tmp_path):
    """Verify load_artifact raises errors for missing or invalid JSON."""
    with pytest.raises(ValueError, match="not found"):
        load_artifact(tmp_path / "does_not_exist.json")

    bad_json = tmp_path / "bad.json"
    bad_json.write_text("{malformed", encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid JSON"):
        load_artifact(bad_json)

    list_json = tmp_path / "list.json"
    list_json.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="top-level must be an object"):
        load_artifact(list_json)


def test_validate_pipeline_artifact_valid():
    """Verify that a correct artifact dictionary validates with zero issues."""
    artifact, issues = validate_pipeline_artifact(base_artifact(), "S2.9")
    assert artifact is not None
    assert not issues


def test_forbidden_decision_signals_blocking_keys():
    """Verify nested forbidden decision keys trigger blocks."""
    raw = base_artifact()
    raw["payload"] = {"nested": {"edge": 0.05, "coupon": {"id": "1"}}}
    artifact, issues = validate_pipeline_artifact(raw, "S2.9")
    assert artifact is None
    assert any(i.code == "FORBIDDEN_DECISION_SIGNALS" for i in issues)


def test_allowed_negative_assertions_do_not_block():
    """Verify explicit safety/readiness assertions remain legal."""
    raw = base_artifact()
    raw["payload"] = {
        "no_pick_edge_stake_coupon_emitted": True,
        "betting_decisions_enabled": False,
        "production_selectable": False,
        "provider_authorization": {"status": "BLOCKED_NO_CREDENTIALS"},
        "authorized_for_sanitized_live_probe": False,
    }
    artifact, issues = validate_pipeline_artifact(raw, "S2.9")
    assert artifact is not None
    assert not issues


def test_secrets_blocking():
    """Verify forbidden secret/header keys still block."""
    raw = base_artifact()
    raw["payload"] = {"credentials": {"api_key": "some-value-secret"}}
    artifact, issues = validate_pipeline_artifact(raw, "S2.9")
    assert artifact is None
    assert any(i.code == "RAW_SECRETS_FOUND" for i in issues)


def test_safe_main_enrichment_strings_do_not_false_positive():
    """Verify current main readiness/evidence phrases remain legal."""
    assert (
        find_forbidden_decision_signals(
            {"note": "Betclic market validation evidence event"}
        )
        == []
    )
    assert (
        find_forbidden_decision_signals(
            {"note": "provider_authorization_status=BLOCKED_NO_CREDENTIALS"}
        )
        == []
    )


def test_forbidden_decision_phrases_block():
    """Verify phrase-strict string scanning blocks only explicit decision phrases."""
    assert find_forbidden_decision_signals({"note": "recommended pick: home win"})
    assert find_forbidden_decision_signals({"note": "stake: 1u"})


def test_secret_scanner_allows_main_authorization_metadata():
    """Verify current main authorization metadata does not trip the secret scanner."""
    raw = base_artifact()
    raw["payload"]["provider_authorization"] = {"status": "BLOCKED_NO_CREDENTIALS"}
    assert detect_secrets(raw) == []


def test_authorized_sanitized_live_probe_metadata_does_not_block():
    """Verify sanitized live-probe authorization metadata stays allowed."""
    raw = base_artifact()
    raw["payload"] = {
        "authorization_status": "AUTHORIZED_FOR_SANITIZED_LIVE_PROBE",
        "provider_authorization_status": "AUTHORIZED_FOR_SANITIZED_LIVE_PROBE",
        "authorized_for_sanitized_live_probe": True,
        "single_flight_probe": "sanitized evidence event",
    }
    assert detect_secrets(raw) == []
    assert find_forbidden_decision_signals(raw) == []
    artifact, issues = validate_pipeline_artifact(raw, "S2.9")
    assert artifact is not None
    assert not issues


def test_secret_scanner_blocks_authorization_header():
    """Verify secret/header keys still block even when readiness metadata is allowed."""
    raw = base_artifact()
    raw["payload"]["authorization_header"] = "Bearer abc"
    assert any(path.endswith("authorization_header") for path in detect_secrets(raw))


@pytest.mark.parametrize("key", ["edge", "coupon"])
def test_find_forbidden_decision_keys_block(key: str):
    """Verify exact forbidden decision keys still block."""
    raw = base_artifact()
    raw["payload"][key] = 0.07
    signals = find_forbidden_decision_signals(raw)
    assert any(f"'{key}'" in signal for signal in signals)


@pytest.mark.parametrize(
    ("status", "should_pass"),
    [("WARN", False), ("SKIPPED", False), ("HUMAN_APPROVED", False), ("PASS", True)],
)
def test_s2_9_status_semantics(status: str, should_pass: bool):
    """Verify S2.9 accepts PASS only as a required AGENT_ARTIFACT gate."""
    artifact, issues = validate_pipeline_artifact(base_artifact(status=status), "S2.9")
    if should_pass:
        assert artifact is not None
        assert not issues
    else:
        assert artifact is None
        assert any(issue.code == "INVALID_REQUIRED_ARTIFACT_STATUS" for issue in issues)


def setup_valid_s2_9_environment(
    root: Path, status: str = "PASS", run_id: str = "run-001"
):
    import hashlib
    from bet.pipeline.agent_work_orders import get_source_head, get_manifest_sha
    curr_source_head = get_source_head(root)
    curr_manifest_sha = get_manifest_sha(root)

    art_dir = root / "pipeline_runs" / "2026-06-25" / run_id / "artifacts"
    art_dir.mkdir(parents=True, exist_ok=True)

    pred_data = {}
    for sid in ("S2.3", "S2.5", "S2.7"):
        pred_wo_path = art_dir / f"{sid}_work_order.json"
        pred_wo_data = {
            "schema_version": 1,
            "work_order_id": f"WO-{run_id}-{sid}",
            "work_order_type": "AGENT_WORK_ORDER",
            "pipeline_id": "daily-pipeline",
            "betting_day": "2026-06-25",
            "run_id": run_id,
            "step_id": sid,
            "agent": "bet-researcher",
            "runtime_mode": "DRY_RUN",
            "created_at": "2026-06-25T12:00:00Z",
            "status": "PASS",
            "input_refs": [],
            "required_output": {
                "expected_path": str(art_dir / f"{sid}.json"),
                "required_statuses": ["PASS", "BLOCK"],
                "schema_requirements": {},
                "forbidden_outputs": [],
                "hard_rules": [],
            },
            "hard_rules": [],
            "forbidden_outputs": [],
            "instructions": {},
            "source_head": curr_source_head,
            "manifest_sha256": curr_manifest_sha,
        }
        pred_wo_path.write_text(json.dumps(pred_wo_data), encoding="utf-8")
        pred_wo_sha = hashlib.sha256(pred_wo_path.read_bytes()).hexdigest()

        p_path = art_dir / f"{sid}.json"
        p_data = {
            "schema_version": 1,
            "artifact_type": "AGENT_ARTIFACT",
            "step_id": sid,
            "producer_agent_id": "bet-researcher",
            "status": "PASS",
            "betting_day": "2026-06-25",
            "run_id": run_id,
            "sport": "Football",
            "point_in_time_as_of": "2026-06-25T12:00:00Z",
            "source_bound": True,
            "no_pick_edge_stake_coupon_emitted": True,
            "production_selectable": False,
            "betting_decisions_enabled": False,
            "sources": ["source"],
            "unknowns": [],
            "blocked_reasons": [],
            "evidence_refs": [],
            "work_order_id": f"WO-{run_id}-{sid}",
            "work_order_sha256": pred_wo_sha,
            "payload": {
                "enrichment_gaps": [] if sid == "S2.3" else None,
                "providers": ["source"] if sid == "S2.5" else None,
                "disputed_facts": [] if sid == "S2.7" else None,
                "reconciliation": {"unknown_facts": [], "decision_basis": "basis"}
                if sid == "S2.7"
                else None,
            },
        }
        p_data["payload"] = {
            k: v for k, v in p_data["payload"].items() if v is not None
        }
        p_path.write_text(json.dumps(p_data), encoding="utf-8")

        p_sha = hashlib.sha256(p_path.read_bytes()).hexdigest()
        pred_data[sid] = {"path": str(p_path), "sha256": p_sha}

    wo_path = art_dir / "S2.9_work_order.json"
    wo_data = {
        "schema_version": 1,
        "work_order_id": f"WO-{run_id}-S2.9",
        "work_order_type": "AGENT_WORK_ORDER",
        "pipeline_id": "daily-pipeline",
        "betting_day": "2026-06-25",
        "run_id": run_id,
        "step_id": "S2.9",
        "agent": "bet-researcher",
        "runtime_mode": "DRY_RUN",
        "created_at": "2026-06-25T12:00:00Z",
        "status": "PASS",
        "input_refs": [
            {
                "step_id": sid,
                "path": pred_data[sid]["path"],
                "sha256": pred_data[sid]["sha256"],
                "artifact_kind": "AGENT_ARTIFACT",
            }
            for sid in ("S2.3", "S2.5", "S2.7")
        ],
        "required_output": {
            "expected_path": str(art_dir / "S2.9.json"),
            "required_statuses": ["PASS", "BLOCK"],
            "schema_requirements": {},
            "forbidden_outputs": [],
            "hard_rules": [],
        },
        "hard_rules": [],
        "forbidden_outputs": [],
        "instructions": {},
        "source_head": curr_source_head,
        "manifest_sha256": curr_manifest_sha,
    }
    wo_path.write_text(json.dumps(wo_data), encoding="utf-8")

    wo_sha = hashlib.sha256(wo_path.read_bytes()).hexdigest()

    s29_path = art_dir / "S2.9.json"
    s29_data = {
        "schema_version": 1,
        "artifact_type": "AGENT_ARTIFACT",
        "step_id": "S2.9",
        "producer_agent_id": "bet-researcher",
        "status": status,
        "betting_day": "2026-06-25",
        "run_id": run_id,
        "sport": "Football",
        "point_in_time_as_of": "2026-06-25T12:00:00Z",
        "source_bound": True,
        "no_pick_edge_stake_coupon_emitted": True,
        "production_selectable": False,
        "betting_decisions_enabled": False,
        "sources": ["source"],
        "unknowns": [],
        "blocked_reasons": [] if status == "PASS" else ["BLOCK_REASON"],
        "evidence_refs": [
            f"artifact_S2.3_{run_id}",
            f"artifact_S2.5_{run_id}",
            f"artifact_S2.7_{run_id}",
        ],
        "work_order_id": f"WO-{run_id}-S2.9",
        "work_order_sha256": wo_sha,
        "payload": {
            "readiness": "PASS",
            "s3_may_proceed": True,
            "predecessor_bindings": [
                {
                    "step_id": sid,
                    "path": pred_data[sid]["path"],
                    "sha256": pred_data[sid]["sha256"],
                    "artifact_type": "AGENT_ARTIFACT",
                    "betting_day": "2026-06-25",
                    "run_id": run_id,
                    "status": "PASS",
                }
                for sid in ("S2.3", "S2.5", "S2.7")
            ],
        }
        if status == "PASS"
        else {},
    }
    s29_path.write_text(json.dumps(s29_data), encoding="utf-8")
    return s29_path


def test_evaluate_gate_s3_requires_s2_9(tmp_path):
    """Verify S3 gate requires a valid S2.9 PASS artifact."""
    decision = evaluate_gate_before_step("S3", tmp_path, "2026-06-25", "run-001")
    assert decision.verdict == PipelineReadinessStatus.BLOCK
    assert any(
        "Missing required artifact for S2.9" in item
        for item in decision.failed_requirements
    )

    s2_9_path = artifact_path_for(tmp_path, "2026-06-25", "run-001", "S2.9")
    s2_9_path.parent.mkdir(parents=True, exist_ok=True)
    s2_9_path.write_text("{malformed", encoding="utf-8")
    decision = evaluate_gate_before_step("S3", tmp_path, "2026-06-25", "run-001")
    assert decision.verdict == PipelineReadinessStatus.BLOCK
    assert any(
        "Malformed" in item or "JSON" in item for item in decision.failed_requirements
    )

    for status, expected in (
        ("BLOCK", PipelineReadinessStatus.BLOCK),
        ("PASS", PipelineReadinessStatus.PASS),
    ):
        root = tmp_path / status
        setup_valid_s2_9_environment(root, status=status)
        decision = evaluate_gate_before_step("S3", root, "2026-06-25", "run-001")
        assert decision.verdict == expected


def test_evaluate_gate_s8_requires_s7_and_s7b(tmp_path):
    """Verify S8 gate requires S7 and S7b SCRIPT_EVIDENCE PASS artifacts."""
    s7 = base_artifact(step_id="S7", artifact_type="SCRIPT_EVIDENCE", status="PASS")
    s7["no_pick_edge_stake_coupon_emitted"] = False
    write_artifact(tmp_path, s7)

    decision = evaluate_gate_before_step("S8", tmp_path, "2026-06-25", "run-001")
    assert decision.verdict == PipelineReadinessStatus.BLOCK
    assert any(
        "Missing required artifact for S7b" in item
        for item in decision.failed_requirements
    )

    s7b = base_artifact(step_id="S7b", artifact_type="SCRIPT_EVIDENCE", status="PASS")
    s7b["no_pick_edge_stake_coupon_emitted"] = False
    write_artifact(tmp_path, s7b)

    decision = evaluate_gate_before_step("S8", tmp_path, "2026-06-25", "run-001")
    assert decision.verdict == PipelineReadinessStatus.PASS


def test_evaluate_gate_s8_blocks_agent_artifact_s7b(tmp_path):
    """Verify S7b AGENT_ARTIFACT blocks S8 even with PASS status."""
    s7 = base_artifact(step_id="S7", artifact_type="SCRIPT_EVIDENCE", status="PASS")
    s7["no_pick_edge_stake_coupon_emitted"] = False
    s7b = base_artifact(step_id="S7b", artifact_type="AGENT_ARTIFACT", status="PASS")
    write_artifact(tmp_path, s7)
    write_artifact(tmp_path, s7b)

    decision = evaluate_gate_before_step("S8", tmp_path, "2026-06-25", "run-001")
    assert decision.verdict == PipelineReadinessStatus.BLOCK
    assert "S7b" in decision.blocked_artifacts


def test_evaluate_gate_s8_blocks_agent_artifact_s7(tmp_path):
    """Verify S7 AGENT_ARTIFACT blocks S8 even when S7b is valid script evidence."""
    s7 = base_artifact(step_id="S7", artifact_type="AGENT_ARTIFACT", status="PASS")
    s7b = base_artifact(step_id="S7b", artifact_type="SCRIPT_EVIDENCE", status="PASS")
    s7b["no_pick_edge_stake_coupon_emitted"] = False
    write_artifact(tmp_path, s7)
    write_artifact(tmp_path, s7b)

    decision = evaluate_gate_before_step("S8", tmp_path, "2026-06-25", "run-001")
    assert decision.verdict == PipelineReadinessStatus.BLOCK
    assert "S7" in decision.blocked_artifacts


def test_unknown_step_type_pair_does_not_satisfy_required_gate():
    """Verify unknown step/type pairs fail closed instead of accepting PASS."""
    artifact, issues = validate_pipeline_artifact(base_artifact(), "S8")
    assert artifact is None
    assert any(issue.code == "INVALID_REQUIRED_ARTIFACT_STATUS" for issue in issues)


def test_evaluate_gate_s10_requires_s9(tmp_path):
    """Verify S10 requires S9 HUMAN_GATE/HUMAN_APPROVED."""
    decision = evaluate_gate_before_step("S10", tmp_path, "2026-06-25", "run-001")
    assert decision.verdict == PipelineReadinessStatus.BLOCK

    for status, expected in (
        ("PASS", PipelineReadinessStatus.BLOCK),
        ("HUMAN_REJECTED", PipelineReadinessStatus.BLOCK),
        ("UNKNOWN", PipelineReadinessStatus.BLOCK),
        ("HUMAN_APPROVED", PipelineReadinessStatus.PASS),
    ):
        artifact = base_artifact(
            step_id="S9", artifact_type="HUMAN_GATE", status=status
        )
        artifact["point_in_time_as_of"] = None
        artifact["source_bound"] = False
        artifact["no_pick_edge_stake_coupon_emitted"] = False
        artifact["sources"] = []
        artifact["sport"] = None
        if status == "HUMAN_APPROVED":
            draft_path = write_s8_coupon_draft(
                tmp_path / status, "2026-06-25", "run-001"
            )
            artifact["manual_review"] = {
                "reviewed_by_user": "test-user",
                "reviewed_at_utc": "2026-06-25T12:00:00Z",
                "operator_workflow": "SUPERBET_MANUAL_BET_BUILDER",
                "approval_origin": "HUMAN_OPERATOR",
                "visible_operator_market_name": "Match winner",
                "visible_operator_line": "Home",
                "human_entered_decimal_quote": 2.1,
                "quote_as_of": "2026-06-25T11:59:00Z",
                "source_quote_card_id": "quote-card-1",
                "explicit_operator_decision": "APPROVE",
                "coupon_draft_path": str(draft_path),
                "coupon_draft_sha256": sha256_file(draft_path),
            }
            artifact["checksum"] = sha256_file(draft_path)
        write_artifact(tmp_path / status, artifact)
        decision = evaluate_gate_before_step(
            "S10", tmp_path / status, "2026-06-25", "run-001"
        )
        assert decision.verdict == expected


def test_p0_2_agent_predecessor_binding_direct_resume(tmp_path):
    """Direct-resume tests for P0-2:
    - S2.5 cannot start with S2.3 artifact but no S2.3 work order;
    - S2.7 cannot start with unbound S2.5;
    - S2.9 cannot start with unbound S2.3/S2.5/S2.7;
    - S6 cannot start with unbound S5;
    - wrong work-order SHA blocks before wrapper or delegation;
    - wrong producer blocks before downstream execution.
    """
    import json
    import hashlib
    from bet.pipeline.agent_work_orders import get_source_head, get_manifest_sha
    curr_source_head = get_source_head(tmp_path)
    curr_manifest_sha = get_manifest_sha(tmp_path)
    run_id = "run-resume"
    betting_day = "2026-06-25"

    art_dir = tmp_path / "pipeline_runs" / betting_day / run_id / "artifacts"
    art_dir.mkdir(parents=True, exist_ok=True)

    # Write a dummy script evidence for S2
    s2_path = art_dir / "S2.json"
    s2_data = {
        "schema_version": 1,
        "artifact_type": "SCRIPT_EVIDENCE",
        "step_id": "S2",
        "status": "PASS",
        "betting_day": betting_day,
        "run_id": run_id,
        "payload": {}
    }
    s2_path.write_text(json.dumps(s2_data), encoding="utf-8")

    # Helper to write a basic mock agent artifact and work order
    def write_mock_agent_step(sid, agent="bet-researcher", wo_id=None, wo_sha=None, producer=None, mutate_wo=False):
        p_wo_path = art_dir / f"{sid}_work_order.json"
        p_wo_data = {
            "schema_version": 1,
            "work_order_id": wo_id or f"WO-{run_id}-{sid}",
            "work_order_type": "AGENT_WORK_ORDER",
            "pipeline_id": "daily-pipeline",
            "betting_day": betting_day,
            "run_id": run_id,
            "step_id": sid,
            "agent": agent,
            "runtime_mode": "DRY_RUN",
            "created_at": "2026-06-25T12:00:00Z",
            "status": "PASS",
            "input_refs": [],
            "required_output": {
                "expected_path": str(art_dir / f"{sid}.json"),
                "required_statuses": ["PASS", "BLOCK"],
                "schema_requirements": {},
                "forbidden_outputs": [],
                "hard_rules": [],
            },
            "hard_rules": [],
            "forbidden_outputs": [],
            "instructions": {},
            "source_head": curr_source_head,
            "manifest_sha256": curr_manifest_sha,
        }
        if not mutate_wo:
            p_wo_path.write_text(json.dumps(p_wo_data), encoding="utf-8")
            computed_wo_sha = hashlib.sha256(p_wo_path.read_bytes()).hexdigest()
        else:
            computed_wo_sha = "some-invalid-sha"

        p_path = art_dir / f"{sid}.json"
        p_data = {
            "schema_version": 1,
            "artifact_type": "AGENT_ARTIFACT",
            "step_id": sid,
            "producer_agent_id": producer or agent,
            "status": "PASS",
            "betting_day": betting_day,
            "run_id": run_id,
            "sport": "Football",
            "point_in_time_as_of": "2026-06-25T12:00:00Z",
            "source_bound": True,
            "no_pick_edge_stake_coupon_emitted": True,
            "production_selectable": False,
            "betting_decisions_enabled": False,
            "sources": ["source"],
            "unknowns": [],
            "blocked_reasons": [],
            "evidence_refs": [],
            "work_order_id": wo_id or f"WO-{run_id}-{sid}",
            "work_order_sha256": wo_sha or computed_wo_sha,
            "payload": {},
        }
        p_path.write_text(json.dumps(p_data), encoding="utf-8")
        return p_path, p_wo_path

    # Case 1: S2.5 cannot start with S2.3 artifact but no S2.3 work order
    s23_path, _ = write_mock_agent_step("S2.3")
    s23_wo_path = art_dir / "S2.3_work_order.json"
    if s23_wo_path.exists():
        s23_wo_path.unlink()

    decision = evaluate_gate_before_step("S2.5", tmp_path, betting_day, run_id)
    assert decision.verdict == PipelineReadinessStatus.BLOCK
    assert any("Missing persisted work order" in err for err in decision.failed_requirements)

    # Case 2: S2.7 cannot start with unbound S2.5 (mismatched ID)
    write_mock_agent_step("S2.3")
    p_path, p_wo_path = write_mock_agent_step("S2.5")
    # Mutate artifact to make it unbound
    data = json.loads(p_path.read_text(encoding="utf-8"))
    data["work_order_id"] = "WO-MISMATCHED-ID"
    p_path.write_text(json.dumps(data), encoding="utf-8")

    decision = evaluate_gate_before_step("S2.7", tmp_path, betting_day, run_id)
    assert decision.verdict == PipelineReadinessStatus.BLOCK
    assert any("work_order_id mismatch" in err for err in decision.failed_requirements)

    # Case 3: S2.9 cannot start with unbound S2.3/S2.5/S2.7
    write_mock_agent_step("S2.3")
    write_mock_agent_step("S2.5")
    write_mock_agent_step("S2.7", producer="wrong-agent")
    decision = evaluate_gate_before_step("S2.9", tmp_path, betting_day, run_id)
    assert decision.verdict == PipelineReadinessStatus.BLOCK
    assert any("producer_agent_id mismatch" in err for err in decision.failed_requirements)

    # Case 4: S6 cannot start with unbound S5
    write_mock_agent_step("S5", agent="bet-risk-gatekeeper", producer="wrong-agent")
    decision = evaluate_gate_before_step("S6", tmp_path, betting_day, run_id)
    assert decision.verdict == PipelineReadinessStatus.BLOCK
    assert any("producer_agent_id mismatch" in err for err in decision.failed_requirements)

    # Case 5: wrong work-order SHA blocks
    write_mock_agent_step("S5", agent="bet-risk-gatekeeper", wo_sha="wrong-sha")
    decision = evaluate_gate_before_step("S6", tmp_path, betting_day, run_id)
    assert decision.verdict == PipelineReadinessStatus.BLOCK
    assert any("work_order_sha256 mismatch" in err for err in decision.failed_requirements)

