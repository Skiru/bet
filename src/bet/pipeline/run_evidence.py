"""Pipeline run evidence helper functions."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bet.pipeline.readiness_contracts import (
    RunEvidence,
    StepEvidence,
    GateDecision,
    PipelineReadinessStatus,
    status_blocks,
)


def utc_now_iso() -> str:
    """Get the current UTC time in ISO 8601 format with a 'Z' suffix."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_text(text: str) -> str:
    """Calculate the SHA-256 hash of a text string."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    """Calculate the SHA-256 hash of a file's contents."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()


def manifest_hash(repo_root: Path) -> str:
    """Get the SHA-256 hash of the canonical pipeline manifest."""
    manifest_path = Path(repo_root) / "config/pipeline_manifest.json"
    if not manifest_path.exists():
        raise ValueError(f"Manifest file not found: {manifest_path}")
    return sha256_file(manifest_path)


def repo_head_sha(repo_root: Path) -> str:
    """Get the HEAD commit SHA of the repository."""
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=True,
        )
        sha = res.stdout.strip()
        if not sha:
            raise ValueError("Git rev-parse returned empty string")
        return sha
    except Exception as e:
        raise ValueError(f"Failed to get git repository HEAD SHA: {e}")


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    """Atomically write a JSON payload to a file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    fd, temp_path_str = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    temp_path = Path(temp_path_str)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass  # fsync may fail on some systems/environments, fallback gracefully
        os.replace(temp_path, path)
    except Exception as e:
        if temp_path.exists():
            try:
                os.unlink(temp_path)
            except Exception:
                pass
        raise ValueError(f"Failed atomic write to {path}: {e}")


def build_run_evidence(
    run_id: str,
    betting_day: str,
    manifest_hash_val: str,
    repo_sha: str,
    dry_run: bool,
    allow_write: bool,
    steps: tuple[StepEvidence, ...],
    gates: tuple[GateDecision, ...],
) -> RunEvidence:
    """Compile StepEvidence and GateDecisions into a structured RunEvidence artifact."""
    failed_reqs = []
    warnings = []

    # Verify steps status
    for step in steps:
        if status_blocks(step.status):
            failed_reqs.append(f"Step {step.step_id} failed or blocked (status={step.status.value})")
        elif step.status == PipelineReadinessStatus.WARN:
            warnings.append(f"Step {step.step_id} has warning status")

    # Verify gates status
    for gate in gates:
        if status_blocks(gate.verdict):
            failed_reqs.extend(gate.failed_requirements)
        elif gate.verdict == PipelineReadinessStatus.WARN:
            warnings.extend(gate.warnings)

    status = PipelineReadinessStatus.PASS
    if failed_reqs:
        status = PipelineReadinessStatus.BLOCK
    elif warnings:
        status = PipelineReadinessStatus.WARN

    return RunEvidence(
        schema_version=1,
        run_id=run_id,
        betting_day=betting_day,
        manifest_hash=manifest_hash_val,
        repo_head_sha=repo_sha,
        dry_run=dry_run,
        allow_write=allow_write,
        status=status,
        steps=steps,
        gates=gates,
        failed_requirements=tuple(failed_reqs),
        warnings=tuple(warnings),
    )


def write_run_evidence(base_dir: Path, run_evidence: RunEvidence) -> Path:
    """Save RunEvidence artifact to disk and return path."""
    base_dir = Path(base_dir)
    target_path = (
        base_dir
        / "pipeline_runs"
        / run_evidence.betting_day
        / run_evidence.run_id
        / "run_summary.json"
    )
    write_json_atomic(target_path, run_evidence.to_jsonable())
    return target_path
