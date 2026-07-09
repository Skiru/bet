"""Pipeline run readiness contracts - dataclasses and enums representing pipeline states."""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Any


class PipelineReadinessStatus(str, Enum):
    PASS = "PASS"
    WARN = "WARN"
    BLOCK = "BLOCK"
    UNKNOWN = "UNKNOWN"
    SKIPPED = "SKIPPED"
    HUMAN_APPROVED = "HUMAN_APPROVED"
    HUMAN_REJECTED = "HUMAN_REJECTED"
    COMMAND_REQUEST = "COMMAND_REQUEST"


class PipelineArtifactType(str, Enum):
    AGENT_ARTIFACT = "AGENT_ARTIFACT"
    HUMAN_GATE = "HUMAN_GATE"
    STATE_MARKER = "STATE_MARKER"
    SCRIPT_EVIDENCE = "SCRIPT_EVIDENCE"
    RUN_SUMMARY = "RUN_SUMMARY"


class ForbiddenDecisionSignal(str, Enum):
    PICK = "pick"
    PICKS = "picks"
    SELECTION = "selection"
    SELECTIONS = "selections"
    BET = "bet"
    BETTING_DECISION = "betting_decision"
    EDGE = "edge"
    EV = "ev"
    EXPECTED_VALUE = "expected_value"
    STAKE = "stake"
    STAKING = "staking"
    COUPON = "coupon"
    ACCUMULATOR = "accumulator"
    PARLAY = "parlay"


class AllowedNegativeAssertionKeys(str, Enum):
    NO_PICK = "no_pick"
    NO_EDGE = "no_edge"
    NO_STAKE = "no_stake"
    NO_COUPON = "no_coupon"
    NO_PICK_EDGE_STAKE_COUPON_EMITTED = "no_pick_edge_stake_coupon_emitted"
    FORBIDDEN_FIELDS_ABSENT = "forbidden_fields_absent"
    BETTING_DECISIONS_ENABLED = "betting_decisions_enabled"
    PRODUCTION_SELECTABLE = "production_selectable"
    ALLOW_REAL_NETWORK = "allow_real_network"
    PROVIDER_AUTHORIZATION = "provider_authorization"
    PROVIDER_AUTHORIZATION_STATUS = "provider_authorization_status"
    AUTHORIZATION_STATUS = "authorization_status"
    AUTHORIZED_FOR_SANITIZED_LIVE_PROBE = "authorized_for_sanitized_live_probe"
    BLOCKED_NO_CREDENTIALS = "blocked_no_credentials"
    SINGLE_FLIGHT_PROBE = "single_flight_probe"


def status_is_pass(status: PipelineReadinessStatus) -> bool:
    """Check if the readiness status represents a non-blocking/passing state."""
    return status in (PipelineReadinessStatus.PASS, PipelineReadinessStatus.HUMAN_APPROVED)


def status_blocks(status: PipelineReadinessStatus) -> bool:
    """Check if the readiness status blocks execution."""
    return status in (
        PipelineReadinessStatus.BLOCK,
        PipelineReadinessStatus.UNKNOWN,
        PipelineReadinessStatus.HUMAN_REJECTED,
        PipelineReadinessStatus.COMMAND_REQUEST,
    )


def normalize_status(value: str) -> PipelineReadinessStatus:
    """Normalize a string status into a PipelineReadinessStatus enum, default to UNKNOWN if invalid."""
    try:
        return PipelineReadinessStatus(value.upper())
    except (ValueError, AttributeError):
        return PipelineReadinessStatus.UNKNOWN


def required_statuses_for_artifact(
    expected_step_id: str,
    artifact_type: PipelineArtifactType,
) -> tuple[PipelineReadinessStatus, ...]:
    """Return statuses that satisfy a required gate for a step/type pair."""
    step_id = expected_step_id.strip()

    if step_id == "S9":
        if artifact_type == PipelineArtifactType.HUMAN_GATE:
            return (PipelineReadinessStatus.HUMAN_APPROVED,)
        return ()

    if step_id == "S10":
        if artifact_type == PipelineArtifactType.STATE_MARKER:
            return (PipelineReadinessStatus.PASS,)
        return ()

    if step_id in {"S2.3", "S2.5", "S2.7", "S2.9", "S5"}:
        if artifact_type == PipelineArtifactType.AGENT_ARTIFACT:
            return (PipelineReadinessStatus.PASS,)
        return ()

    if step_id in {"S7", "S7b"}:
        if artifact_type == PipelineArtifactType.SCRIPT_EVIDENCE:
            return (PipelineReadinessStatus.PASS,)
        return ()

    return ()


def status_satisfies_required_gate(
    status: PipelineReadinessStatus,
    expected_step_id: str,
    artifact_type: PipelineArtifactType,
) -> bool:
    """Return True when the artifact status is valid for the required gate."""
    return status in required_statuses_for_artifact(expected_step_id, artifact_type)


def _to_jsonable_value(value: Any) -> Any:
    """Recursively convert a value to a JSON-compatible type."""
    if hasattr(value, "to_jsonable"):
        return value.to_jsonable()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(k): _to_jsonable_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_to_jsonable_value(v) for v in value]
    if isinstance(value, Path):
        return str(value)
    return value


@dataclass
class ReadinessIssue:
    code: str
    severity: PipelineReadinessStatus
    message: str
    path: str | None = None

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity.value,
            "message": self.message,
            "path": self.path,
        }


@dataclass
class PipelineArtifact:
    schema_version: int
    artifact_type: PipelineArtifactType
    step_id: str
    status: PipelineReadinessStatus
    betting_day: str
    run_id: str
    sport: str | None
    fixture_id: str | None
    fixture_key: str | None
    point_in_time_as_of: str | None
    source_bound: bool
    no_pick_edge_stake_coupon_emitted: bool
    production_selectable: bool
    betting_decisions_enabled: bool
    sources: tuple[str, ...]
    unknowns: tuple[str, ...]
    blocked_reasons: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    payload: dict[str, Any]

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "artifact_type": self.artifact_type.value,
            "step_id": self.step_id,
            "status": self.status.value,
            "betting_day": self.betting_day,
            "run_id": self.run_id,
            "sport": self.sport,
            "fixture_id": self.fixture_id,
            "fixture_key": self.fixture_key,
            "point_in_time_as_of": self.point_in_time_as_of,
            "source_bound": self.source_bound,
            "no_pick_edge_stake_coupon_emitted": self.no_pick_edge_stake_coupon_emitted,
            "production_selectable": self.production_selectable,
            "betting_decisions_enabled": self.betting_decisions_enabled,
            "sources": list(self.sources),
            "unknowns": list(self.unknowns),
            "blocked_reasons": list(self.blocked_reasons),
            "evidence_refs": list(self.evidence_refs),
            "payload": _to_jsonable_value(self.payload),
        }


@dataclass
class GateDecision:
    gate_id: str
    target_step_id: str
    verdict: PipelineReadinessStatus
    failed_requirements: tuple[str, ...]
    warnings: tuple[str, ...]
    required_artifacts: tuple[str, ...]
    accepted_artifacts: tuple[str, ...]
    blocked_artifacts: tuple[str, ...]
    metrics: dict[str, Any]

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "gate_id": self.gate_id,
            "target_step_id": self.target_step_id,
            "verdict": self.verdict.value,
            "failed_requirements": list(self.failed_requirements),
            "warnings": list(self.warnings),
            "required_artifacts": list(self.required_artifacts),
            "accepted_artifacts": list(self.accepted_artifacts),
            "blocked_artifacts": list(self.blocked_artifacts),
            "metrics": _to_jsonable_value(self.metrics),
        }


@dataclass
class StepEvidence:
    step_id: str
    execution_mode: str
    status: PipelineReadinessStatus
    command: tuple[str, ...]
    started_at: str | None
    finished_at: str | None
    return_code: int | None
    stdout_path: str | None
    stderr_path: str | None
    artifact_path: str | None
    blocked_reason: str | None

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "execution_mode": self.execution_mode,
            "status": self.status.value,
            "command": list(self.command),
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "return_code": self.return_code,
            "stdout_path": self.stdout_path,
            "stderr_path": self.stderr_path,
            "artifact_path": self.artifact_path,
            "blocked_reason": self.blocked_reason,
        }


@dataclass
class RunEvidence:
    schema_version: int
    run_id: str
    betting_day: str
    manifest_hash: str
    repo_head_sha: str
    dry_run: bool
    allow_write: bool
    status: PipelineReadinessStatus
    steps: tuple[StepEvidence, ...]
    gates: tuple[GateDecision, ...]
    failed_requirements: tuple[str, ...]
    warnings: tuple[str, ...]

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "betting_day": self.betting_day,
            "manifest_hash": self.manifest_hash,
            "repo_head_sha": self.repo_head_sha,
            "dry_run": self.dry_run,
            "allow_write": self.allow_write,
            "status": self.status.value,
            "steps": [_to_jsonable_value(s) for s in self.steps],
            "gates": [_to_jsonable_value(g) for g in self.gates],
            "failed_requirements": list(self.failed_requirements),
            "warnings": list(self.warnings),
        }
