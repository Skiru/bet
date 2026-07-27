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
        nested_path = run_root_path / "pipeline_runs" / betting_day / run_id / "artifacts" / f"{step_id}.json"
        if nested_path.exists():
            evidence_path = nested_path
        else:
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
        "S1e": ["s1e_output_path", "s1e_json_output"],
        "S2": ["s2_output_path", "s2_shortlist_path", "shortlist_path"],
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

    if not isinstance(output_val, str) or not output_val:
        raise ValueError(f"No output path declared in step {step_id} evidence payload")

    output_path = Path(output_val).resolve()

    resolved_run_root = run_root_path.resolve()
    resolved_output_path = output_path.resolve()

    try:
        rel = resolved_output_path.relative_to(resolved_run_root)
        curr = resolved_run_root
        for part in rel.parts:
            curr = curr / part
            if curr.is_symlink():
                raise ValueError(f"Step {step_id} output path contains a symlink component: {curr}")
    except ValueError:
        raise ValueError(f"Step {step_id} output path {output_path} is outside run root {run_root_path}")

    if output_path.is_symlink() or resolved_output_path.is_symlink():
        raise ValueError(f"Step {step_id} output path {output_path} is a symlink")

    if not output_path.exists():
        raise FileNotFoundError(f"Step {step_id} output file missing: {output_path}")

    if output_path.stat().st_size == 0:
        raise ValueError(f"Step {step_id} output file is empty")

    expected_sha_keys = [
        f"{step_id.lower()}_output_sha256",
        f"{step_id.lower()}_output_sha",
        "s3_output_sha256",
        "s4_valuation_output_sha256",
        "s7_output_sha256",
        "s7b_output_sha256",
        "s8_quote_pack_sha256",
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

    if step_id in {"S1e", "S2", "S3", "S4", "S6", "S7", "S7b", "S8"} and not (
        isinstance(expected_sha, str) and expected_sha
    ):
        raise ValueError(f"Step {step_id} evidence is missing the required output SHA-256")
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
    if actual_type != expected_artifact_type:
        if not (step_id == "S5" and actual_type == "AGENT_ARTIFACT" and expected_artifact_type == "S5_CONTEXT_RISK_CANDIDATE_SET_V2"):
            raise ValueError(f"STEP_TYPE_MISMATCH: Artifact type mismatch: expected {expected_artifact_type}, got {actual_type}")
    if step_id == "S2":
        if "total_candidates" not in output_data:
            raise ValueError("Artifact structure mismatch for S2: expected total_candidates key")
    elif step_id == "S3":
        if "analyses" not in output_data:
            raise ValueError("Artifact structure mismatch for S3: expected analyses key")

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

    strict_validate_step_output(
        step_id=step_id,
        output_path=output_path,
        output_data=output_data,
        run_root=run_root_path,
        betting_day=betting_day,
        run_id=run_id,
        expected_artifact_type=expected_artifact_type,
    )
    return output_path, output_data


def resolve_manifest_step_output(
    *,
    manifest: Any,
    run_root: Path | str,
    step_id: str,
    betting_day: str,
    run_id: str,
    expected_artifact_type: str,
    expected_source_sha: str | None = None,
) -> tuple[Path, dict[str, Any]]:
    """Canonical predecessor resolver supporting both SCRIPT_EVIDENCE and AGENT_ARTIFACT modes."""
    from bet.pipeline.run_evidence import sha256_file

    steps = []
    if hasattr(manifest, "steps"):
        steps = manifest.steps
    elif isinstance(manifest, dict) and "steps" in manifest:
        steps = manifest["steps"]

    step_entry = None
    for step in steps:
        sid = getattr(step, "id", None) if not isinstance(step, dict) else step.get("id")
        if sid == step_id:
            step_entry = step
            break

    if step_entry is None:
        raise ValueError(f"STEP_ID_MISMATCH: Step {step_id} not found in manifest")

    exec_mode = getattr(step_entry, "execution_mode", None) if not isinstance(step_entry, dict) else step_entry.get("execution_mode")

    run_root_path = Path(run_root).resolve()
    evidence_path = run_root_path / "artifacts" / f"{step_id}.json"
    if not evidence_path.exists():
        nested_path = run_root_path / "pipeline_runs" / betting_day / run_id / "artifacts" / f"{step_id}.json"
        if nested_path.exists():
            evidence_path = nested_path
        else:
            raise FileNotFoundError(f"STEP_EVIDENCE_MISSING: Prerequisite step {step_id} evidence file missing: {evidence_path}")

    if evidence_path.is_symlink():
        raise ValueError(f"STEP_OUTPUT_OUTSIDE_RUN: Prerequisite step {step_id} evidence path is a symlink")
    try:
        evidence_path.resolve().relative_to(run_root_path)
    except ValueError:
        raise ValueError(f"STEP_OUTPUT_OUTSIDE_RUN: Prerequisite step {step_id} evidence path is outside run root")

    try:
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    except Exception as e:
        raise ValueError(f"STEP_EVIDENCE_SCHEMA_INVALID: Failed to parse step {step_id} JSON: {e}")

    if not isinstance(evidence, dict):
        raise ValueError(f"STEP_EVIDENCE_SCHEMA_INVALID: Evidence for {step_id} is not a JSON object")

    if evidence.get("step_id") != step_id:
        raise ValueError(f"STEP_ID_MISMATCH: Step ID mismatch in evidence: expected {step_id}, got {evidence.get('step_id')}")
    if evidence.get("betting_day") != betting_day:
        raise ValueError(f"STEP_DAY_MISMATCH: Betting day mismatch in evidence: expected {betting_day}, got {evidence.get('betting_day')}")
    if evidence.get("run_id") != run_id:
        raise ValueError(f"STEP_RUN_MISMATCH: Run ID mismatch in evidence: expected {run_id}, got {evidence.get('run_id')}")

    if evidence.get("status") != "PASS":
        raise ValueError(f"STEP_OUTPUT_MISSING: Prerequisite step {step_id} did not PASS. Status: {evidence.get('status')}")

    if exec_mode == "agent_artifact":
        if evidence.get("artifact_type") != "AGENT_ARTIFACT":
            raise ValueError(f"STEP_TYPE_MISMATCH: Expected AGENT_ARTIFACT for step {step_id}, got {evidence.get('artifact_type')}")

        payload = evidence.get("payload")
        if not isinstance(payload, dict):
            raise ValueError(f"STEP_EVIDENCE_SCHEMA_INVALID: AGENT_ARTIFACT payload must be an object")

        output_val = None
        for k in ["output_path", f"{step_id.lower()}_output_path", "candidates_path", "result_path"]:
            if k in payload:
                output_val = payload[k]
                break

        if output_val:
            output_path = Path(output_val).resolve()
            if output_path.is_symlink():
                raise ValueError(f"STEP_OUTPUT_OUTSIDE_RUN: Step {step_id} output path {output_path} is a symlink")
            try:
                output_path.relative_to(run_root_path)
            except ValueError:
                raise ValueError(f"STEP_OUTPUT_OUTSIDE_RUN: Step {step_id} output path {output_path} is outside run root {run_root_path}")

            if not output_path.exists():
                raise FileNotFoundError(f"STEP_OUTPUT_MISSING: Step {step_id} output file missing: {output_path}")
            try:
                output_data = json.loads(output_path.read_text(encoding="utf-8"))
            except Exception as e:
                raise ValueError(f"STEP_EVIDENCE_SCHEMA_INVALID: Failed to parse output file JSON: {e}")
        else:
            output_path = evidence_path
            output_data = evidence

        actual_type = output_data.get("artifact_type") or output_data.get("artifact_kind")
        if actual_type == "AGENT_ARTIFACT" and expected_artifact_type == "S5_CONTEXT_RISK_CANDIDATE_SET_V2" and output_data.get("step_id") == "S5":
            if output_data.get("status") == "PASS":
                from bet.pipeline.agent_artifact_contracts import validate_s5_artifact_v2
                validate_s5_artifact_v2(
                    s5_data=output_data,
                    run_root=run_root_path,
                    betting_day=betting_day,
                    run_id=run_id,
                    manifest=manifest,
                )
        elif actual_type != expected_artifact_type:
            raise ValueError(f"STEP_TYPE_MISMATCH: Artifact type mismatch: expected {expected_artifact_type}, got {actual_type}")

        actual_sha = sha256_file(output_path)
        if expected_source_sha and actual_sha != expected_source_sha:
            raise ValueError(f"STEP_OUTPUT_HASH_MISMATCH: Step {step_id} output SHA-256 mismatch: expected {expected_source_sha}, got {actual_sha}")

        strict_validate_step_output(
            step_id=step_id,
            output_path=output_path,
            output_data=output_data,
            run_root=run_root_path,
            betting_day=betting_day,
            run_id=run_id,
            expected_artifact_type=expected_artifact_type,
        )
        return output_path, output_data

    elif exec_mode == "script" or exec_mode is None:
        if evidence.get("artifact_type") != "SCRIPT_EVIDENCE":
            raise ValueError(f"STEP_TYPE_MISMATCH: Expected SCRIPT_EVIDENCE for step {step_id}, got {evidence.get('artifact_type')}")

        payload = evidence.get("payload") or {}
        output_keys = {
            "S2": ["s2_shortlist_path", "s2_output_path", "shortlist_path"],
            "S3": ["s3_output_path", "s3_json_output"],
            "S4": ["s4_valuation_output_path", "s4_output_path"],
            "S6": ["s6_output_path", "repeat_loss_handoff_path", "output_path"],
            "S7": ["s7_json_output", "s7_output_path", "analytical_candidate_handoff_path"],
            "S7b": ["s7b_json_output", "s7b_output_path", "validated_market_availability_path"],
            "S8": ["s8_quote_pack_path", "s8_json_output", "s8_output_path"],
        }.get(step_id, [])

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
            raise ValueError(f"STEP_OUTPUT_MISSING: No output path declared in step {step_id} evidence payload")

        output_path = Path(output_val).resolve()

        if output_path.is_symlink():
            raise ValueError(f"STEP_OUTPUT_OUTSIDE_RUN: Step {step_id} output path {output_path} is a symlink")
        try:
            output_path.relative_to(run_root_path)
        except ValueError:
            raise ValueError(f"STEP_OUTPUT_OUTSIDE_RUN: Step {step_id} output path {output_path} is outside run root {run_root_path}")

        if not output_path.exists():
            raise FileNotFoundError(f"STEP_OUTPUT_MISSING: Step {step_id} output file missing: {output_path}")

        actual_sha = sha256_file(output_path)
        expected_sha_keys = [
            f"{step_id.lower()}_output_sha256",
            f"{step_id.lower()}_output_sha",
            "s3_output_sha256",
            "s4_valuation_output_sha256",
            "s7_output_sha256",
            "s7b_output_sha256",
            "s8_quote_pack_sha256",
            "output_sha256",
        ]
        recorded_sha = None
        for k in expected_sha_keys:
            if k in payload:
                recorded_sha = payload[k]
                break
            if k in evidence:
                recorded_sha = evidence[k]
                break

        if step_id in {"S3", "S4", "S6", "S7", "S7b", "S8"} and not (
            isinstance(recorded_sha, str) and recorded_sha
        ):
            raise ValueError(
                f"STEP_OUTPUT_HASH_MISSING: Step {step_id} evidence is missing the required output SHA-256"
            )
        if recorded_sha and actual_sha != recorded_sha:
            raise ValueError(f"STEP_OUTPUT_HASH_MISMATCH: Step {step_id} output file SHA-256 mismatch: expected {recorded_sha}, got {actual_sha}")

        if expected_source_sha and actual_sha != expected_source_sha:
            raise ValueError(f"STEP_OUTPUT_HASH_MISMATCH: Step {step_id} output file SHA-256 mismatch with expected: expected {expected_source_sha}, got {actual_sha}")

        try:
            output_data = json.loads(output_path.read_text(encoding="utf-8"))
        except Exception as e:
            raise ValueError(f"STEP_EVIDENCE_SCHEMA_INVALID: Failed to parse step {step_id} output file JSON: {e}")

        if not isinstance(output_data, dict):
            raise ValueError(f"STEP_EVIDENCE_SCHEMA_INVALID: Step {step_id} output is not a JSON object")

        actual_type = output_data.get("artifact_type") or output_data.get("artifact_kind")
        if step_id == "S2":
            if expected_artifact_type != "S2_SHORTLIST":
                raise ValueError(f"STEP_TYPE_MISMATCH: Artifact type mismatch: expected {expected_artifact_type}, got {actual_type or 'S2_SHORTLIST'}")
            if actual_type is not None and actual_type != expected_artifact_type:
                raise ValueError(f"STEP_TYPE_MISMATCH: Artifact type mismatch: expected {expected_artifact_type}, got {actual_type}")
        elif step_id == "S3":
            if expected_artifact_type != "S3_DEEP_STATS":
                raise ValueError(f"STEP_TYPE_MISMATCH: Artifact type mismatch: expected {expected_artifact_type}, got {actual_type or 'S3_DEEP_STATS'}")
            if actual_type is not None and actual_type != expected_artifact_type:
                raise ValueError(f"STEP_TYPE_MISMATCH: Artifact type mismatch: expected {expected_artifact_type}, got {actual_type}")
        else:
            if actual_type is not None and actual_type != expected_artifact_type:
                raise ValueError(f"STEP_TYPE_MISMATCH: Artifact type mismatch: expected {expected_artifact_type}, got {actual_type}")

        strict_validate_step_output(
            step_id=step_id,
            output_path=output_path,
            output_data=output_data,
            run_root=run_root_path,
            betting_day=betting_day,
            run_id=run_id,
            expected_artifact_type=expected_artifact_type,
        )
        return output_path, output_data
    else:
        raise ValueError(f"STEP_EVIDENCE_SCHEMA_INVALID: Unsupported execution mode '{exec_mode}' for step {step_id}")


def strict_validate_step_output(
    *,
    step_id: str,
    output_path: Path,
    output_data: dict[str, Any],
    run_root: Path,
    betting_day: str,
    run_id: str,
    expected_artifact_type: str,
) -> None:
    """Strict loader/validator for bound step output."""
    # 1. Required file exists
    if not output_path.exists():
        raise FileNotFoundError(f"STEP_OUTPUT_MISSING: Step {step_id} output file missing: {output_path}")

    # 2. Canonical path is within the current run root
    resolved_path = output_path.resolve()
    try:
        resolved_path.relative_to(run_root.resolve())
    except ValueError:
        raise ValueError(f"STEP_OUTPUT_OUTSIDE_RUN: Step {step_id} output path {output_path} is outside run root {run_root}")

    # 3. No symlinked ancestor or path escape
    if output_path.is_symlink() or resolved_path.is_symlink():
        raise ValueError(f"STEP_OUTPUT_OUTSIDE_RUN: Step {step_id} output path {output_path} is a symlink")

    curr = resolved_path
    while curr != run_root.resolve():
        if curr.is_symlink():
            raise ValueError(f"STEP_OUTPUT_OUTSIDE_RUN: Step {step_id} output path {output_path} has symlinked ancestor: {curr}")
        if curr == curr.parent:
            break
        curr = curr.parent

    # 4. Non-empty regular file
    if not resolved_path.is_file() or resolved_path.stat().st_size == 0:
        raise ValueError(f"STEP_OUTPUT_MISSING: Step {step_id} output file is empty or not a regular file")

    # 5. Expected mapping/list schema
    if not isinstance(output_data, dict):
        raise ValueError(f"STEP_EVIDENCE_SCHEMA_INVALID: Step {step_id} output must be a dictionary")

    # 6. Correct artifact type and step ID
    actual_type = output_data.get("artifact_type") or output_data.get("artifact_kind")
    if actual_type != expected_artifact_type:
        if not (step_id == "S5" and actual_type in ("AGENT_ARTIFACT", "S5_CONTEXT_MOTIVATION_RISK") and expected_artifact_type in ("AGENT_ARTIFACT", "S5_CONTEXT_RISK_CANDIDATE_SET_V2")):
            raise ValueError(f"STEP_TYPE_MISMATCH: Artifact type mismatch: expected {expected_artifact_type}, got {actual_type}")

    # 7. Matching run ID and betting day
    if "betting_day" in output_data and output_data["betting_day"] != betting_day:
        raise ValueError(f"STEP_DAY_MISMATCH: Betting day mismatch: expected {betting_day}, got {output_data['betting_day']}")
    if output_data.get("run_id") and output_data["run_id"] != run_id:
        raise ValueError(f"STEP_RUN_MISMATCH: Run ID mismatch: expected {run_id}, got {output_data['run_id']}")

    # 8. Event records check
    if step_id in {"S2", "S3", "S4", "S5", "S6", "S7", "S7b", "S8"}:
        # Must explicitly produce event_records (possibly in payload for agent_artifacts)
        event_records = output_data.get("event_records")
        if event_records is None and isinstance(output_data.get("payload"), dict):
            event_records = output_data["payload"].get("event_records")

        if event_records is None:
            event_records = []

        if not isinstance(event_records, list):
            raise ValueError(f"EVENT_BOUNDARY_RECORD_INVALID: Step {step_id} 'event_records' must be a list")

        # Load S1e universe if present
        s1e_file = run_root / "data" / f"{betting_day}_s1e_event_universe.json"
        if not s1e_file.exists() or len(event_records) == 0:
            for idx, rec in enumerate(event_records):
                if not isinstance(rec, dict):
                    raise ValueError(f"EVENT_BOUNDARY_RECORD_INVALID: event_records[{idx}] is not a dictionary")
                eid = rec.get("canonical_event_id") or rec.get("event_id")
                if not eid:
                    raise ValueError(f"EVENT_BOUNDARY_STATUS_MISSING: event_records[{idx}] lacks canonical_event_id")
                status = rec.get("terminal_status") or rec.get("status")
                if not status:
                    raise ValueError(f"EVENT_BOUNDARY_STATUS_MISSING: Event {eid} lacks terminal_status")
                valid_outcomes = {"CONTINUE", "DEGRADED_CONTINUE", "REJECTED", "NO_ACTION", "BLOCKED"}
                if status not in valid_outcomes:
                    raise ValueError(f"EVENT_BOUNDARY_RECORD_INVALID: Event {eid} has invalid outcome '{status}'")
            return

        try:
            s1e_data = json.loads(s1e_file.read_text(encoding="utf-8"))
            universe_ids = set(s1e_data.get("canonical_event_ids", []))
        except Exception as exc:
            raise ValueError(f"S1E_JSON_MALFORMED: S1e file is malformed: {exc}")

        # Check: no missing, unknown, or duplicate event
        rec_ids = []
        for idx, rec in enumerate(event_records):
            if not isinstance(rec, dict):
                raise ValueError(f"EVENT_BOUNDARY_RECORD_INVALID: event_records[{idx}] is not a dictionary")

            eid = rec.get("canonical_event_id") or rec.get("event_id")
            if not eid:
                raise ValueError(f"EVENT_BOUNDARY_STATUS_MISSING: event_records[{idx}] lacks canonical_event_id")

            rec_ids.append(eid)

            # Every event has exactly one valid typed outcome
            status = rec.get("terminal_status") or rec.get("status")
            if not status:
                raise ValueError(f"EVENT_BOUNDARY_STATUS_MISSING: Event {eid} lacks terminal_status")

            valid_outcomes = {"CONTINUE", "DEGRADED_CONTINUE", "REJECTED", "NO_ACTION", "BLOCKED"}
            if status not in valid_outcomes:
                raise ValueError(f"EVENT_BOUNDARY_RECORD_INVALID: Event {eid} has invalid outcome '{status}'")

        from collections import Counter
        dups = [k for k, v in Counter(rec_ids).items() if v > 1]
        if dups:
            raise ValueError(f"EVENT_BOUNDARY_DUPLICATE_EVENT: Duplicate event IDs in event_records: {dups}")

        rec_set = set(rec_ids)
        missing_ids = universe_ids - rec_set
        extra_ids = rec_set - universe_ids

        if missing_ids:
            raise ValueError(f"EVENT_BOUNDARY_LOSS: Missing event IDs in event_records: {sorted(missing_ids)}")
        if extra_ids:
            raise ValueError(f"EVENT_BOUNDARY_UNKNOWN_EVENT: Unknown/extra event IDs in event_records: {sorted(extra_ids)}")
