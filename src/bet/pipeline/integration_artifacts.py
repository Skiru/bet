"""Helpers for runtime-scoped script evidence and integration artifacts."""
from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bet.pipeline.artifact_gate import (
    artifact_path_for,
    load_artifact,
    validate_pipeline_artifact,
)
from bet.pipeline.artifact_io import publish_run_artifact


def runtime_context(environ: dict[str, str] | None = None) -> dict[str, str | None]:
    env = environ or os.environ
    return {
        "runtime_mode": env.get("BET_PIPELINE_RUNTIME_MODE"),
        "betting_day": env.get("BET_PIPELINE_BETTING_DAY"),
        "run_id": env.get("BET_PIPELINE_RUN_ID"),
        "run_root": env.get("BET_PIPELINE_RUN_ROOT"),
        "artifact_dir": env.get("BET_PIPELINE_ARTIFACT_DIR"),
    }


def script_evidence_base_dir(environ: dict[str, str] | None = None) -> Path | None:
    ctx = runtime_context(environ)
    run_root = ctx.get("run_root")
    if run_root:
        r = Path(run_root)
        if "pipeline_runs" in r.parts:
            idx = r.parts.index("pipeline_runs")
            prefix = r.parts[:idx]
            if prefix:
                if r.is_absolute():
                    return Path("/", *prefix)
                return Path(*prefix)
        return r
    artifact_dir = ctx.get("artifact_dir")
    if artifact_dir:
        return Path(artifact_dir).parent
    return None


def script_evidence_path(step_id: str, environ: dict[str, str] | None = None) -> Path | None:
    ctx = runtime_context(environ)
    base_dir = script_evidence_base_dir(environ)
    betting_day = ctx.get("betting_day")
    run_id = ctx.get("run_id")
    if not (base_dir and betting_day and run_id):
        return None
    return artifact_path_for(base_dir, str(betting_day), str(run_id), step_id)


def build_script_evidence(
    *,
    step_id: str,
    status: str,
    betting_day: str,
    run_id: str,
    payload: dict[str, Any],
    sources: tuple[str, ...],
    evidence_refs: tuple[str, ...],
    point_in_time_as_of: str | None = None,
    no_pick_edge_stake_coupon_emitted: bool = False,
    production_selectable: bool = False,
    betting_decisions_enabled: bool = False,
    blocked_reasons: tuple[str, ...] = (),
    extra_top_level_fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    artifact = {
        "schema_version": 1,
        "artifact_type": "SCRIPT_EVIDENCE",
        "step_id": step_id,
        "status": status,
        "betting_day": betting_day,
        "run_id": run_id,
        "sport": None,
        "fixture_id": None,
        "fixture_key": None,
        "point_in_time_as_of": point_in_time_as_of or datetime.now(UTC).isoformat(),
        "source_bound": True,
        "no_pick_edge_stake_coupon_emitted": no_pick_edge_stake_coupon_emitted,
        "production_selectable": production_selectable,
        "betting_decisions_enabled": betting_decisions_enabled,
        "sources": list(sources),
        "unknowns": [],
        "blocked_reasons": list(blocked_reasons),
        "evidence_refs": list(evidence_refs),
        "payload": payload,
    }
    artifact.update(extra_top_level_fields or {})
    return artifact


def write_script_evidence(
    step_id: str,
    *,
    status: str,
    payload: dict[str, Any],
    sources: tuple[str, ...],
    evidence_refs: tuple[str, ...],
    environ: dict[str, str] | None = None,
    no_pick_edge_stake_coupon_emitted: bool = False,
    production_selectable: bool = False,
    betting_decisions_enabled: bool = False,
    blocked_reasons: tuple[str, ...] = (),
    extra_top_level_fields: dict[str, Any] | None = None,
) -> Path | None:
    ctx = runtime_context(environ)
    evidence_path = script_evidence_path(step_id, environ)
    if evidence_path is None or not ctx.get("betting_day") or not ctx.get("run_id"):
        return None

    artifact = build_script_evidence(
        step_id=step_id,
        status=status,
        betting_day=str(ctx["betting_day"]),
        run_id=str(ctx["run_id"]),
        payload=payload,
        sources=sources,
        evidence_refs=evidence_refs,
        no_pick_edge_stake_coupon_emitted=no_pick_edge_stake_coupon_emitted,
        production_selectable=production_selectable,
        betting_decisions_enabled=betting_decisions_enabled,
        blocked_reasons=blocked_reasons,
        extra_top_level_fields=extra_top_level_fields,
    )
    run_root = Path(str(ctx.get("run_root") or evidence_path.parent.parent))
    run_root.mkdir(parents=True, exist_ok=True)
    publish_run_artifact(
        run_root=run_root,
        target=evidence_path,
        payload=artifact,
        betting_day=str(ctx["betting_day"]),
        run_id=str(ctx["run_id"]),
        artifact_type="SCRIPT_EVIDENCE",
        immutable=False,
    )
    return evidence_path


def require_pass_script_evidence(step_ids: tuple[str, ...], environ: dict[str, str] | None = None) -> dict[str, dict[str, Any]]:
    loaded: dict[str, dict[str, Any]] = {}
    for step_id in step_ids:
        path = script_evidence_path(step_id, environ)
        if path is None or not path.exists():
            raise FileNotFoundError(f"Missing required script evidence for {step_id}")
        raw = load_artifact(path)
        artifact, issues = validate_pipeline_artifact(raw, step_id)
        if artifact is None or issues:
            raise ValueError(f"Invalid required script evidence for {step_id}")
        loaded[step_id] = raw
    return loaded


def build_market_availability_artifact(
    *,
    date: str,
    scanned_at: str,
    summary: dict[str, Any],
    validation: list[dict[str, Any]] | None,
    events: list[dict[str, Any]],
    runtime_mode: str | None,
    timeout_seconds: int,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "artifact_kind": "market_availability",
        "stage": "S7b",
        "source_contract": "LEGACY_OPERATOR",
        "date": date,
        "scanned_at": scanned_at,
        "runtime_mode": runtime_mode or "UNMANAGED",
        "timeout_seconds": timeout_seconds,
        "summary": summary,
        "validation": validation,
        "events": events,
    }


def resolve_bound_step_output(
    *,
    run_root: Path | str,
    step_id: str,
    betting_day: str,
    run_id: str,
    expected_artifact_type: str,
    expected_source_step: str | None = None,
) -> tuple[Path, dict[str, Any]]:
    """Canonical resolver for step outputs with strict schema, path and hash validation."""
    from bet.pipeline.run_evidence import sha256_file

    run_root_path = Path(run_root).resolve()
    evidence_path = run_root_path / "artifacts" / f"{step_id}.json"
    if not evidence_path.exists():
        raise FileNotFoundError(f"Prerequisite step {step_id} evidence missing: {evidence_path}")

    # Reject symlinks and directory traversal
    if evidence_path.is_symlink():
        raise ValueError(f"Prerequisite step {step_id} evidence path is a symlink")
    try:
        evidence_path.resolve().relative_to(run_root_path)
    except ValueError:
        raise ValueError(f"Prerequisite step {step_id} evidence path is outside run root")

    try:
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    except Exception as e:
        raise ValueError(f"Failed to parse SCRIPT_EVIDENCE JSON for {step_id}: {e}")

    if not isinstance(evidence, dict) or evidence.get("artifact_type") != "SCRIPT_EVIDENCE" or "step_id" not in evidence:
        raise ValueError(f"Invalid SCRIPT_EVIDENCE schema for {step_id}")

    if evidence.get("step_id") != step_id:
        raise ValueError(f"Step ID mismatch in evidence: expected {step_id}, got {evidence.get('step_id')}")
    if evidence.get("betting_day") != betting_day:
        raise ValueError(f"Betting day mismatch in evidence: expected {betting_day}, got {evidence.get('betting_day')}")
    if evidence.get("run_id") != run_id:
        raise ValueError(f"Run ID mismatch in evidence: expected {run_id}, got {evidence.get('run_id')}")
    if evidence.get("status") != "PASS":
        raise ValueError(f"Prerequisite step {step_id} did not PASS. Status: {evidence.get('status')}")

    payload = evidence.get("payload") or {}

    step_keys = {
        "S2": ["s2_shortlist_path", "s2_output_path", "shortlist_path"],
        "S3": ["s3_output_path", "s3_json_output"],
        "S4": ["s4_valuation_output_path", "s4_output_path"],
        "S7": ["s7_json_output", "s7_output_path", "analytical_candidate_handoff_path"],
        "S7b": ["s7b_json_output", "s7b_output_path", "validated_market_availability_path"],
        "S8": ["s8_output_path"],
    }
    output_keys = step_keys.get(step_id, [])

    output_val = None
    for k in output_keys:
        if k in payload:
            output_val = payload[k]
            break
        if k in evidence:
            output_val = evidence[k]
            break

    if not output_val and step_id == "S3":
        paths = payload.get("s3_report_paths") or evidence.get("s3_report_paths")
        if isinstance(paths, list) and paths:
            for p_str in paths:
                if p_str.endswith(".json"):
                    output_val = p_str
                    break

    if not output_val:
        defaults = {
            "S2": run_root_path / "data" / f"{betting_day}_s2_shortlist.json",
            "S3": run_root_path / "data" / f"{betting_day}_s3_deep_stats.json",
            "S4": run_root_path / "data" / f"{betting_day}_s4_valuation_candidates.json",
            "S7": run_root_path / "data" / "analytical_candidate_handoff.json",
        }
        if step_id in defaults:
            output_val = str(defaults[step_id])

    if not isinstance(output_val, str) or not output_val:
        raise ValueError(f"No output path declared in step {step_id} evidence payload")

    output_path = Path(output_val).resolve()

    try:
        output_path.relative_to(run_root_path)
    except ValueError:
        raise ValueError(f"Step {step_id} output path {output_path} is outside run root {run_root_path}")

    if output_path.is_symlink():
        raise ValueError(f"Step {step_id} output path {output_path} is a symlink")

    if not output_path.exists():
        raise FileNotFoundError(f"Step {step_id} output file missing: {output_path}")

    expected_sha_keys = [
        f"{step_id.lower()}_output_sha256",
        f"{step_id.lower()}_output_sha",
        "s3_output_sha256",
        "s4_valuation_output_sha256",
        "s7b_output_sha256",
        "output_sha256",
    ]
    expected_sha = None
    for k in expected_sha_keys:
        if k in payload:
            expected_sha = payload[k]
            break
        if k in evidence:
            expected_sha = evidence[k]
            break

    if expected_sha and isinstance(expected_sha, str):
        actual_sha = sha256_file(output_path)
        if actual_sha != expected_sha:
            raise ValueError(f"Step {step_id} output file SHA-256 mismatch: expected {expected_sha}, got {actual_sha}")

    try:
        output_data = json.loads(output_path.read_text(encoding="utf-8"))
    except Exception as e:
        raise ValueError(f"Failed to parse step {step_id} output file JSON: {e}")

    if not isinstance(output_data, dict):
        raise ValueError(f"Step {step_id} output is not a JSON object")

    actual_type = output_data.get("artifact_type") or output_data.get("artifact_kind")
    if step_id == "S2":
        if expected_artifact_type != "S2_SHORTLIST":
            raise ValueError(f"Artifact type mismatch: expected {expected_artifact_type}, got {actual_type or 'S2_SHORTLIST'}")
        if actual_type is not None and actual_type != expected_artifact_type:
            raise ValueError(f"Artifact type mismatch: expected {expected_artifact_type}, got {actual_type}")
        if "total_candidates" not in output_data:
            raise ValueError("Artifact structure mismatch for S2: expected total_candidates key")
    elif step_id == "S3":
        if expected_artifact_type != "S3_DEEP_STATS":
            raise ValueError(f"Artifact type mismatch: expected {expected_artifact_type}, got {actual_type or 'S3_DEEP_STATS'}")
        if actual_type is not None and actual_type != expected_artifact_type:
            raise ValueError(f"Artifact type mismatch: expected {expected_artifact_type}, got {actual_type}")
        if "analyses" not in output_data:
            raise ValueError("Artifact structure mismatch for S3: expected analyses key")
    else:
        if actual_type != expected_artifact_type:
            raise ValueError(f"Artifact type mismatch: expected {expected_artifact_type}, got {actual_type}")

    if expected_source_step:
        source_evidence_path = run_root_path / "artifacts" / f"{expected_source_step}.json"
        if source_evidence_path.exists():
            try:
                source_evidence = json.loads(source_evidence_path.read_text(encoding="utf-8"))
            except Exception:
                source_evidence = {}
            source_payload = source_evidence.get("payload") or {}

            source_sha = None
            for k in expected_sha_keys:
                src_k = k.replace(step_id.lower(), expected_source_step.lower())
                if src_k in source_payload:
                    source_sha = source_payload[src_k]
                    break
                if src_k in source_evidence:
                    source_sha = source_evidence[src_k]
                    break

            if source_sha:
                recorded_source_sha = None
                recorded_keys = [
                    f"source_{expected_source_step.lower()}_sha256",
                    f"source_{expected_source_step.lower()}_sha",
                    "source_s3_sha256",
                    "source_s4_sha256",
                    "source_s4_hash",
                    "source_sha256",
                ]
                for k in recorded_keys:
                    if k in output_data:
                        recorded_source_sha = output_data[k]
                        break

                if recorded_source_sha and recorded_source_sha != source_sha:
                    raise ValueError(f"Upstream source SHA mismatch: {expected_source_step} SHA is {source_sha}, but recorded as {recorded_source_sha}")

    return output_path, output_data

