"""Tests for pipeline readiness contracts (enums, dataclasses, status helpers)."""
from __future__ import annotations

import pytest

from bet.pipeline.readiness_contracts import (
    PipelineReadinessStatus,
    PipelineArtifactType,
    ForbiddenDecisionSignal,
    AllowedNegativeAssertionKeys,
    status_is_pass,
    status_blocks,
    normalize_status,
    ReadinessIssue,
    PipelineArtifact,
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


def test_status_helpers():
    """Verify status evaluation functions correctly categorize pipeline states."""
    # PASS and HUMAN_APPROVED pass
    assert status_is_pass(PipelineReadinessStatus.PASS) is True
    assert status_is_pass(PipelineReadinessStatus.HUMAN_APPROVED) is True
    assert status_is_pass(PipelineReadinessStatus.WARN) is False
    assert status_is_pass(PipelineReadinessStatus.BLOCK) is False
    assert status_is_pass(PipelineReadinessStatus.UNKNOWN) is False

    # BLOCK, UNKNOWN, and HUMAN_REJECTED block
    assert status_blocks(PipelineReadinessStatus.BLOCK) is True
    assert status_blocks(PipelineReadinessStatus.UNKNOWN) is True
    assert status_blocks(PipelineReadinessStatus.HUMAN_REJECTED) is True
    assert status_blocks(PipelineReadinessStatus.PASS) is False
    assert status_blocks(PipelineReadinessStatus.WARN) is False


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
