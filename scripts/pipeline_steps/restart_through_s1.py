from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from bet.pipeline.artifact_io import publish_immutable_json_blob, publish_run_artifact
from bet.pipeline.run_evidence import sha256_file
from bet.pipeline.run_coordination import ResumeLedger


class RestartThroughS1Error(ValueError):
    pass


def _artifact(path: Path, step: str, day: str, run_id: str) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise RestartThroughS1Error(f"SOURCE_{step}_MISSING")
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("artifact_type") != "SCRIPT_EVIDENCE" or data.get("step_id") != step:
        raise RestartThroughS1Error(f"SOURCE_{step}_BINDING_INVALID")
    if data.get("betting_day") != day or data.get("run_id") != run_id or data.get("status") != "PASS":
        raise RestartThroughS1Error(f"SOURCE_{step}_BINDING_INVALID")
    return data


def _empty_target(path: Path) -> None:
    if path.exists():
        if not path.is_dir() or any(path.iterdir()):
            raise RestartThroughS1Error("TARGET_RUN_ROOT_EXISTS_NON_EMPTY")
        raise RestartThroughS1Error("TARGET_RUN_ROOT_EXISTS")


def prepare_restart_through_s1(source_root: Path, target_root: Path, source_run_id: str, target_run_id: str, day: str, expected_s0: str | None = None, expected_s1: str | None = None) -> dict[str, str]:
    if source_run_id == target_run_id:
        raise RestartThroughS1Error("SOURCE_TARGET_RUN_ID_MUST_DIFFER")
    source_root = Path(source_root).resolve(strict=True)
    target_root = Path(target_root).resolve(strict=False)
    _empty_target(target_root)
    s0_path = source_root / "artifacts" / "S0.json"
    s1_path = source_root / "artifacts" / "S1.json"
    s0_sha = sha256_file(s0_path) if s0_path.is_file() else None
    s1_sha = sha256_file(s1_path) if s1_path.is_file() else None
    if expected_s0 and s0_sha != expected_s0:
        raise RestartThroughS1Error("SOURCE_S0_SHA256_MISMATCH")
    if expected_s1 and s1_sha != expected_s1:
        raise RestartThroughS1Error("SOURCE_S1_SHA256_MISMATCH")
    source_ledger = source_root / "resume_ledger.json"
    if not source_ledger.is_file():
        raise RestartThroughS1Error("SOURCE_RESUME_LEDGER_MISSING")
    source_ledger_data = json.loads(source_ledger.read_text(encoding="utf-8"))
    try:
        ResumeLedger.verify(source_ledger_data)
    except Exception as exc:
        raise RestartThroughS1Error("SOURCE_RESUME_LEDGER_INVALID") from exc
    s0 = _artifact(s0_path, "S0", day, source_run_id)
    s1 = _artifact(s1_path, "S1", day, source_run_id)
    matrix_value = (s1.get("payload") or {}).get("market_matrix_path")
    if not isinstance(matrix_value, str):
        raise RestartThroughS1Error("SOURCE_S1_MARKET_MATRIX_BINDING_MISSING")
    matrix_path = Path(matrix_value).resolve(strict=True)
    try:
        matrix_path.relative_to(source_root)
    except ValueError as exc:
        raise RestartThroughS1Error("SOURCE_S1_INPUT_CROSS_RUN") from exc
    if matrix_path.is_symlink() or not matrix_path.is_file():
        raise RestartThroughS1Error("SOURCE_S1_INPUT_INVALID")
    target_root.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{target_run_id}.", dir=target_root.parent))
    try:
        (staging / "data").mkdir()
        (staging / "artifacts").mkdir()
        staged_matrix = staging / "data" / matrix_path.name
        target_matrix = target_root / "data" / matrix_path.name
        publish_immutable_json_blob(run_root=staging, target=staged_matrix, payload=json.loads(matrix_path.read_text(encoding="utf-8")))
        target_s0 = dict(s0, run_id=target_run_id, payload=dict(s0.get("payload") or {}))
        target_s0["payload"].update(source_run_id=source_run_id, source_artifact_sha256=s0_sha)
        publish_run_artifact(run_root=staging, target=staging / "artifacts" / "S0.json", payload=target_s0, betting_day=day, run_id=target_run_id, artifact_type="SCRIPT_EVIDENCE")
        target_s1 = dict(s1, run_id=target_run_id, payload=dict(s1.get("payload") or {}))
        target_s1["payload"].update(market_matrix_path=str(target_matrix), source_run_id=source_run_id, source_artifact_sha256=s1_sha, source_market_matrix_sha256=sha256_file(matrix_path))
        publish_run_artifact(run_root=staging, target=staging / "artifacts" / "S1.json", payload=target_s1, betting_day=day, run_id=target_run_id, artifact_type="SCRIPT_EVIDENCE")
        if any((staging / name).exists() for name in ("event_accounting_ledger.json",)) or (staging / "artifacts" / "S1e.json").exists():
            raise RestartThroughS1Error("RESTART_FORBIDDEN_S1E_OR_ACCOUNTING_MEMBER")
        os.rename(staging, target_root)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return {"source_s0_sha256": str(s0_sha), "source_s1_sha256": str(s1_sha), "target_s0_sha256": sha256_file(target_root / "artifacts" / "S0.json"), "target_s1_sha256": sha256_file(target_root / "artifacts" / "S1.json")}
