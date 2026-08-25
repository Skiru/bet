"""Tests for pipeline readiness contracts (enums, dataclasses, status helpers)."""
from __future__ import annotations

from bet.pipeline.readiness_contracts import (
    AllowedNegativeAssertionKeys,
    ForbiddenDecisionSignal,
    PipelineArtifact,
    PipelineArtifactType,
    PipelineReadinessStatus,
    ReadinessIssue,
    normalize_status,
    required_statuses_for_artifact,
    status_blocks,
    status_is_pass,
    status_satisfies_required_gate,
)


def test_enums_are_stable_strings():
    """Verify that enums have stable string values per contract."""
    assert PipelineReadinessStatus.PASS == "PASS"
    assert PipelineReadinessStatus.WARN == "WARN"
    assert PipelineReadinessStatus.BLOCK == "BLOCK"
    assert PipelineReadinessStatus.UNKNOWN == "UNKNOWN"
    assert PipelineReadinessStatus.SKIPPED == "SKIPPED"
    assert PipelineReadinessStatus.HUMAN_APPROVED == "HUMAN_APPROVED"
    assert PipelineReadinessStatus.HUMAN_REJECTED == "HUMAN_REJECTED"
    assert PipelineReadinessStatus.COMMAND_REQUEST == "COMMAND_REQUEST"

    assert PipelineArtifactType.AGENT_ARTIFACT == "AGENT_ARTIFACT"
    assert PipelineArtifactType.HUMAN_GATE == "HUMAN_GATE"
    assert PipelineArtifactType.STATE_MARKER == "STATE_MARKER"
    assert PipelineArtifactType.SCRIPT_EVIDENCE == "SCRIPT_EVIDENCE"
    assert PipelineArtifactType.RUN_SUMMARY == "RUN_SUMMARY"

    assert ForbiddenDecisionSignal.PICK == "pick"
    assert ForbiddenDecisionSignal.COUPON == "coupon"
    assert ForbiddenDecisionSignal.STAKE == "stake"

    assert AllowedNegativeAssertionKeys.NO_PICK == "no_pick"
    assert AllowedNegativeAssertionKeys.NO_PICK_EDGE_STAKE_COUPON_EMITTED == "no_pick_edge_stake_coupon_emitted"
    assert AllowedNegativeAssertionKeys.PROVIDER_AUTHORIZATION == "provider_authorization"
    assert AllowedNegativeAssertionKeys.SINGLE_FLIGHT_PROBE == "single_flight_probe"


def test_status_helpers():
    """Verify generic status helpers remain stable."""
    assert status_is_pass(PipelineReadinessStatus.PASS) is True
    assert status_is_pass(PipelineReadinessStatus.HUMAN_APPROVED) is True
    assert status_is_pass(PipelineReadinessStatus.WARN) is False
    assert status_is_pass(PipelineReadinessStatus.BLOCK) is False
    assert status_is_pass(PipelineReadinessStatus.UNKNOWN) is False

    assert status_blocks(PipelineReadinessStatus.BLOCK) is True
    assert status_blocks(PipelineReadinessStatus.UNKNOWN) is True
    assert status_blocks(PipelineReadinessStatus.HUMAN_REJECTED) is True
    assert status_blocks(PipelineReadinessStatus.COMMAND_REQUEST) is True
    assert status_blocks(PipelineReadinessStatus.PASS) is False
    assert status_blocks(PipelineReadinessStatus.WARN) is False


def test_required_statuses_for_agent_gate_steps():
    """Verify S2.x and S5 gates accept AGENT_ARTIFACT PASS only."""
    for step_id in ("S2.3", "S2.5", "S2.7", "S2.9", "S5"):
        assert required_statuses_for_artifact(step_id, PipelineArtifactType.AGENT_ARTIFACT) == (
            PipelineReadinessStatus.PASS,
        )
        assert status_satisfies_required_gate(
            PipelineReadinessStatus.PASS,
            step_id,
            PipelineArtifactType.AGENT_ARTIFACT,
        )
        assert not status_satisfies_required_gate(
            PipelineReadinessStatus.WARN,
            step_id,
            PipelineArtifactType.AGENT_ARTIFACT,
        )
        assert not status_satisfies_required_gate(
            PipelineReadinessStatus.SKIPPED,
            step_id,
            PipelineArtifactType.AGENT_ARTIFACT,
        )
        assert not status_satisfies_required_gate(
            PipelineReadinessStatus.UNKNOWN,
            step_id,
            PipelineArtifactType.AGENT_ARTIFACT,
        )
        assert not status_satisfies_required_gate(
            PipelineReadinessStatus.HUMAN_APPROVED,
            step_id,
            PipelineArtifactType.AGENT_ARTIFACT,
        )


def test_required_statuses_for_s7_and_s7b_script_evidence():
    """Verify S7/S7b gates accept SCRIPT_EVIDENCE PASS only."""
    for step_id in ("S7", "S7b"):
        assert required_statuses_for_artifact(step_id, PipelineArtifactType.SCRIPT_EVIDENCE) == (
            PipelineReadinessStatus.PASS,
        )
        assert status_satisfies_required_gate(
            PipelineReadinessStatus.PASS,
            step_id,
            PipelineArtifactType.SCRIPT_EVIDENCE,
        )
        assert not status_satisfies_required_gate(
            PipelineReadinessStatus.PASS,
            step_id,
            PipelineArtifactType.AGENT_ARTIFACT,
        )
        assert not status_satisfies_required_gate(
            PipelineReadinessStatus.HUMAN_APPROVED,
            step_id,
            PipelineArtifactType.SCRIPT_EVIDENCE,
        )


def test_required_statuses_for_s9_human_gate():
    """Verify S9 accepts HUMAN_APPROVED only for HUMAN_GATE artifacts."""
    assert required_statuses_for_artifact("S9", PipelineArtifactType.HUMAN_GATE) == (
        PipelineReadinessStatus.HUMAN_APPROVED,
    )
    assert status_satisfies_required_gate(
        PipelineReadinessStatus.HUMAN_APPROVED,
        "S9",
        PipelineArtifactType.HUMAN_GATE,
    )
    assert not status_satisfies_required_gate(
        PipelineReadinessStatus.PASS,
        "S9",
        PipelineArtifactType.HUMAN_GATE,
    )
    assert not status_satisfies_required_gate(
        PipelineReadinessStatus.HUMAN_REJECTED,
        "S9",
        PipelineArtifactType.HUMAN_GATE,
    )
    assert not status_satisfies_required_gate(
        PipelineReadinessStatus.UNKNOWN,
        "S9",
        PipelineArtifactType.HUMAN_GATE,
    )


def test_required_statuses_for_s10_state_marker():
    """Verify S10 state markers accept PASS only when explicitly required."""
    assert required_statuses_for_artifact("S10", PipelineArtifactType.STATE_MARKER) == (
        PipelineReadinessStatus.PASS,
    )
    assert status_satisfies_required_gate(
        PipelineReadinessStatus.PASS,
        "S10",
        PipelineArtifactType.STATE_MARKER,
    )
    assert not status_satisfies_required_gate(
        PipelineReadinessStatus.HUMAN_APPROVED,
        "S10",
        PipelineArtifactType.STATE_MARKER,
    )


def test_unknown_step_type_pairs_require_no_default_status():
    """Verify unknown step/type pairs fail closed with no implicit PASS."""
    assert required_statuses_for_artifact("S1e", PipelineArtifactType.RUN_SUMMARY) == ()
    assert required_statuses_for_artifact("S8", PipelineArtifactType.AGENT_ARTIFACT) == ()
    assert not status_satisfies_required_gate(
        PipelineReadinessStatus.PASS,
        "S1e",
        PipelineArtifactType.RUN_SUMMARY,
    )
    assert not status_satisfies_required_gate(
        PipelineReadinessStatus.PASS,
        "S8",
        PipelineArtifactType.AGENT_ARTIFACT,
    )


def test_normalize_status():
    """Verify normalize_status matches casing or defaults to UNKNOWN."""
    assert normalize_status("pass") == PipelineReadinessStatus.PASS
    assert normalize_status("WARN") == PipelineReadinessStatus.WARN
    assert normalize_status("human_approved") == PipelineReadinessStatus.HUMAN_APPROVED
    assert normalize_status("garbage_status") == PipelineReadinessStatus.UNKNOWN
    assert normalize_status("") == PipelineReadinessStatus.UNKNOWN


def test_dataclasses_serialize_to_jsonable():
    """Verify dataclasses serialize cleanly to JSON-compatible structures."""
    issue = ReadinessIssue(
        code="TEST_CODE",
        severity=PipelineReadinessStatus.BLOCK,
        message="A test warning block",
        path="$.payload",
    )
    json_val = issue.to_jsonable()
    assert json_val == {
        "code": "TEST_CODE",
        "severity": "BLOCK",
        "message": "A test warning block",
        "path": "$.payload",
    }

    artifact = PipelineArtifact(
        schema_version=1,
        artifact_type=PipelineArtifactType.AGENT_ARTIFACT,
        step_id="S2.9",
        status=PipelineReadinessStatus.PASS,
        betting_day="2026-06-24",
        run_id="run-123",
        sport="Football",
        fixture_id="fix-99",
        fixture_key="fb_99",
        point_in_time_as_of="2026-06-24T22:00:00Z",
        source_bound=True,
        no_pick_edge_stake_coupon_emitted=True,
        production_selectable=False,
        betting_decisions_enabled=False,
        sources=("understat", "fbref"),
        unknowns=(),
        blocked_reasons=(),
        evidence_refs=(),
        payload={"metrics": {"accuracy": 0.85}},
    )

    serialized = artifact.to_jsonable()
    assert serialized["schema_version"] == 1
    assert serialized["artifact_type"] == "AGENT_ARTIFACT"
    assert serialized["step_id"] == "S2.9"
    assert serialized["status"] == "PASS"
    assert serialized["sources"] == ["understat", "fbref"]
    assert serialized["payload"] == {"metrics": {"accuracy": 0.85}}
