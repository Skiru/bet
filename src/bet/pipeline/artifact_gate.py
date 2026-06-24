"""Pipeline artifact gate - validates and checks upstream artifact readiness."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from bet.pipeline.readiness_contracts import (
    PipelineArtifact,
    PipelineArtifactType,
    PipelineReadinessStatus,
    GateDecision,
    ReadinessIssue,
    ForbiddenDecisionSignal,
    AllowedNegativeAssertionKeys,
    normalize_status,
    status_blocks,
)


def load_artifact(path: Path) -> dict[str, Any]:
    """Load and parse artifact JSON from path. Fails closed on any error."""
    path = Path(path)
    if not path.exists():
        raise ValueError(f"Artifact file not found: {path}")

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in artifact {path}: {e}")
    except Exception as e:
        raise ValueError(f"Failed to read artifact {path}: {e}")

    if not isinstance(data, dict):
        raise ValueError(f"Artifact JSON top-level must be an object at {path}")

    return data


def artifact_path_for(
    base_dir: Path,
    betting_day: str,
    run_id: str,
    step_id: str,
    fixture_key: str | None = None,
) -> Path:
    """Get the canonical artifact path on disk."""
    base_dir = Path(base_dir)
    if fixture_key:
        return (
            base_dir
            / "pipeline_runs"
            / betting_day
            / run_id
            / "artifacts"
            / "fixtures"
            / fixture_key
            / f"{step_id}.json"
        )
    return (
        base_dir
        / "pipeline_runs"
        / betting_day
        / run_id
        / "artifacts"
        / f"{step_id}.json"
    )


def find_forbidden_decision_signals(payload: Any, path: str = "$") -> list[str]:
    """Recursively search payload for forbidden betting decision terms."""
    found = []
    forbidden_signals = {s.value.lower() for s in ForbiddenDecisionSignal}
    allowed_assertions = {s.value.lower() for s in AllowedNegativeAssertionKeys}

    def recurse(node: Any, current_path: str):
        if isinstance(node, dict):
            for k, v in node.items():
                k_lower = str(k).lower()
                if k_lower in allowed_assertions:
                    continue
                if k_lower == "betting_decisions_enabled" and v is False:
                    continue
                if k_lower == "production_selectable" and v is False:
                    continue

                if k_lower in forbidden_signals:
                    found.append(f"{current_path}.{k}")

                if isinstance(v, str):
                    v_lower = v.lower()
                    for sig in forbidden_signals:
                        if sig in v_lower:
                            found.append(f"{current_path}.{k}='{v}' (contains {sig})")

                recurse(v, f"{current_path}.{k}")

        elif isinstance(node, list):
            for idx, item in enumerate(node):
                if isinstance(item, str):
                    item_lower = item.lower()
                    for sig in forbidden_signals:
                        if sig in item_lower:
                            found.append(f"{current_path}[{idx}]='{item}' (contains {sig})")
                recurse(item, f"{current_path}[{idx}]")

    recurse(payload, path)
    return found


def detect_secrets(node: Any, path: str = "$") -> list[str]:
    """Recursively check for obvious raw secrets (API keys, tokens, etc.)."""
    found = []
    secret_patterns = {"api_key", "token", "secret", "authorization", "bearer", "password"}
    if isinstance(node, dict):
        for k, v in node.items():
            k_lower = str(k).lower()
            if any(p in k_lower for p in secret_patterns):
                if v and not isinstance(v, bool):
                    found.append(f"{path}.{k}")
            found.extend(detect_secrets(v, f"{path}.{k}"))
    elif isinstance(node, list):
        for idx, item in enumerate(node):
            found.extend(detect_secrets(item, f"{path}[{idx}]"))
    return found


def validate_pipeline_artifact(
    raw: dict[str, Any], expected_step_id: str
) -> tuple[PipelineArtifact | None, list[ReadinessIssue]]:
    """Validate a loaded raw artifact dict against schemas and safety constraints."""
    issues: list[ReadinessIssue] = []

    # 1. schema_version check
    if "schema_version" not in raw:
        issues.append(
            ReadinessIssue(
                code="MISSING_SCHEMA_VERSION",
                severity=PipelineReadinessStatus.BLOCK,
                message="schema_version is required",
            )
        )
    else:
        try:
            sv = int(raw["schema_version"])
            if sv < 1:
                issues.append(
                    ReadinessIssue(
                        code="INVALID_SCHEMA_VERSION",
                        severity=PipelineReadinessStatus.BLOCK,
                        message="schema_version must be >= 1",
                    )
                )
        except (ValueError, TypeError):
            issues.append(
                ReadinessIssue(
                    code="INVALID_SCHEMA_VERSION_TYPE",
                    severity=PipelineReadinessStatus.BLOCK,
                    message="schema_version must be an integer",
                )
            )

    # 2. artifact_type check
    art_type = None
    if "artifact_type" not in raw:
        issues.append(
            ReadinessIssue(
                code="MISSING_ARTIFACT_TYPE",
                severity=PipelineReadinessStatus.BLOCK,
                message="artifact_type is required",
            )
        )
    else:
        try:
            art_type = PipelineArtifactType(raw["artifact_type"])
        except ValueError:
            issues.append(
                ReadinessIssue(
                    code="INVALID_ARTIFACT_TYPE",
                    severity=PipelineReadinessStatus.BLOCK,
                    message=f"Invalid artifact_type: {raw['artifact_type']}",
                )
            )

    # 3. step_id check
    if "step_id" not in raw:
        issues.append(
            ReadinessIssue(
                code="MISSING_STEP_ID",
                severity=PipelineReadinessStatus.BLOCK,
                message="step_id is required",
            )
        )
    elif raw["step_id"] != expected_step_id:
        issues.append(
            ReadinessIssue(
                code="MISMATCH_STEP_ID",
                severity=PipelineReadinessStatus.BLOCK,
                message=f"Expected step_id {expected_step_id}, got {raw['step_id']}",
            )
        )

    # 4. status check
    status_val = PipelineReadinessStatus.UNKNOWN
    if "status" not in raw:
        issues.append(
            ReadinessIssue(
                code="MISSING_STATUS",
                severity=PipelineReadinessStatus.BLOCK,
                message="status is required",
            )
        )
    else:
        status_val = normalize_status(raw["status"])
        if status_blocks(status_val):
            issues.append(
                ReadinessIssue(
                    code="BLOCKING_STATUS",
                    severity=PipelineReadinessStatus.BLOCK,
                    message=f"Artifact status is blocking: {status_val.value}",
                )
            )

    # 5. point_in_time_as_of check
    if art_type == PipelineArtifactType.AGENT_ARTIFACT:
        if not raw.get("point_in_time_as_of"):
            issues.append(
                ReadinessIssue(
                    code="MISSING_POINT_IN_TIME",
                    severity=PipelineReadinessStatus.BLOCK,
                    message="point_in_time_as_of is required for agent artifacts",
                )
            )

    # 6. enrichment specific checks (S2.3, S2.5, S2.7, S2.9)
    is_enrichment = expected_step_id in ("S2.3", "S2.5", "S2.7", "S2.9")
    if is_enrichment:
        if raw.get("source_bound") is not True:
            issues.append(
                ReadinessIssue(
                    code="SOURCE_BOUND_REQUIRED",
                    severity=PipelineReadinessStatus.BLOCK,
                    message="source_bound must be true for enrichment artifacts",
                )
            )
        if raw.get("no_pick_edge_stake_coupon_emitted") is not True:
            issues.append(
                ReadinessIssue(
                    code="NO_PICK_EDGE_STAKE_COUPON_EMITTED_REQUIRED",
                    severity=PipelineReadinessStatus.BLOCK,
                    message="no_pick_edge_stake_coupon_emitted must be true for enrichment artifacts",
                )
            )
        if raw.get("production_selectable") is not False:
            issues.append(
                ReadinessIssue(
                    code="PRODUCTION_SELECTABLE_FORBIDDEN",
                    severity=PipelineReadinessStatus.BLOCK,
                    message="production_selectable must be false for enrichment artifacts",
                )
            )
        if raw.get("betting_decisions_enabled") is not False:
            issues.append(
                ReadinessIssue(
                    code="BETTING_DECISIONS_ENABLED_FORBIDDEN",
                    severity=PipelineReadinessStatus.BLOCK,
                    message="betting_decisions_enabled must be false for enrichment artifacts",
                )
            )

    # 7. Recursive forbidden signals & raw secrets
    payload = raw.get("payload", {})
    signals = find_forbidden_decision_signals(payload)
    if signals:
        issues.append(
            ReadinessIssue(
                code="FORBIDDEN_DECISION_SIGNALS",
                severity=PipelineReadinessStatus.BLOCK,
                message=f"Forbidden decision signals found: {', '.join(signals)}",
            )
        )

    secrets = detect_secrets(raw)
    if secrets:
        issues.append(
            ReadinessIssue(
                code="RAW_SECRETS_FOUND",
                severity=PipelineReadinessStatus.BLOCK,
                message=f"Obvious secret fields detected: {', '.join(secrets)}",
            )
        )

    # 8. List/tuple verification
    if art_type == PipelineArtifactType.AGENT_ARTIFACT:
        if "sources" not in raw:
            issues.append(
                ReadinessIssue(
                    code="MISSING_SOURCES",
                    severity=PipelineReadinessStatus.BLOCK,
                    message="sources is required for agent artifacts",
                )
            )
        elif not isinstance(raw["sources"], (list, tuple)):
            issues.append(
                ReadinessIssue(
                    code="INVALID_SOURCES_FORMAT",
                    severity=PipelineReadinessStatus.BLOCK,
                    message="sources must be a list or tuple",
                )
            )

    for field_name in ("unknowns", "blocked_reasons", "evidence_refs"):
        if field_name in raw and not isinstance(raw[field_name], (list, tuple)):
            issues.append(
                ReadinessIssue(
                    code=f"INVALID_{field_name.upper()}_FORMAT",
                    severity=PipelineReadinessStatus.BLOCK,
                    message=f"{field_name} must be a list or tuple",
                )
            )

    # Try building PipelineArtifact
    artifact = None
    if not any(i.severity == PipelineReadinessStatus.BLOCK for i in issues):
        try:
            artifact = PipelineArtifact(
                schema_version=int(raw.get("schema_version", 1)),
                artifact_type=PipelineArtifactType(raw.get("artifact_type", "AGENT_ARTIFACT")),
                step_id=str(raw.get("step_id", expected_step_id)),
                status=status_val,
                betting_day=str(raw.get("betting_day", "")),
                run_id=str(raw.get("run_id", "")),
                sport=raw.get("sport"),
                fixture_id=raw.get("fixture_id"),
                fixture_key=raw.get("fixture_key"),
                point_in_time_as_of=raw.get("point_in_time_as_of"),
                source_bound=bool(raw.get("source_bound", False)),
                no_pick_edge_stake_coupon_emitted=bool(raw.get("no_pick_edge_stake_coupon_emitted", False)),
                production_selectable=bool(raw.get("production_selectable", False)),
                betting_decisions_enabled=bool(raw.get("betting_decisions_enabled", False)),
                sources=tuple(raw.get("sources", ())),
                unknowns=tuple(raw.get("unknowns", ())),
                blocked_reasons=tuple(raw.get("blocked_reasons", ())),
                evidence_refs=tuple(raw.get("evidence_refs", ())),
                payload=payload,
            )
        except Exception as e:
            issues.append(
                ReadinessIssue(
                    code="CONSTRUCTION_FAILED",
                    severity=PipelineReadinessStatus.BLOCK,
                    message=f"Failed to instantiate PipelineArtifact: {e}",
                )
            )

    return artifact, issues


def required_artifacts_before_step(step_id: str) -> tuple[str, ...]:
    """Map pipeline steps to their direct prerequisite step artifacts."""
    if step_id == "S3":
        return ("S2.9",)
    if step_id == "S6":
        return ("S5",)
    if step_id == "S8":
        return ("S7", "S7b")
    if step_id == "S10":
        return ("S9",)
    if step_id == "S2.5":
        return ("S2.3",)
    if step_id == "S2.7":
        return ("S2.5",)
    if step_id == "S2.9":
        return ("S2.7",)
    return ()


def evaluate_gate_before_step(
    step_id: str, artifact_dir: Path, betting_day: str, run_id: str
) -> GateDecision:
    """Evaluate pre-requisite artifacts for a target step, returning detailed verdict."""
    req_steps = required_artifacts_before_step(step_id)
    failed_reqs = []
    warnings = []
    accepted = []
    blocked = []

    for req_step in req_steps:
        path = artifact_path_for(artifact_dir, betting_day, run_id, req_step)
        if not path.exists():
            blocked.append(req_step)
            failed_reqs.append(f"Missing required artifact for {req_step} (expected at {path})")
            continue

        try:
            raw = load_artifact(path)
            artifact, issues = validate_pipeline_artifact(raw, req_step)
        except Exception as e:
            blocked.append(req_step)
            failed_reqs.append(f"Malformed or unreadable artifact for {req_step}: {e}")
            continue

        block_issues = [i for i in issues if i.severity == PipelineReadinessStatus.BLOCK]
        warn_issues = [i for i in issues if i.severity == PipelineReadinessStatus.WARN]

        if block_issues or artifact is None:
            blocked.append(req_step)
            for i in block_issues:
                failed_reqs.append(f"Artifact {req_step} has blocking issue: {i.message} [{i.code}]")
        else:
            accepted.append(req_step)
            for i in warn_issues:
                warnings.append(f"Artifact {req_step} has warning: {i.message} [{i.code}]")

    verdict = PipelineReadinessStatus.PASS
    if blocked or failed_reqs:
        verdict = PipelineReadinessStatus.BLOCK
    elif warnings:
        verdict = PipelineReadinessStatus.WARN

    metrics = {
        "required_count": len(req_steps),
        "accepted_count": len(accepted),
        "blocked_count": len(blocked),
    }

    return GateDecision(
        gate_id=f"gate_before_{step_id}",
        target_step_id=step_id,
        verdict=verdict,
        failed_requirements=tuple(failed_reqs),
        warnings=tuple(warnings),
        required_artifacts=req_steps,
        accepted_artifacts=tuple(accepted),
        blocked_artifacts=tuple(blocked),
        metrics=metrics,
    )
