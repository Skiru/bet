"""Helpers for runtime-scoped script evidence and integration artifacts."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bet.pipeline.artifact_gate import artifact_path_for, load_artifact, validate_pipeline_artifact
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
        return Path(run_root)
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
        "point_in_time_as_of": point_in_time_as_of or datetime.now(timezone.utc).isoformat(),
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
