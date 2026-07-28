"""Typed receipt schemas and cryptographic binding validators for BET PIPELINE V5."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator, model_validator
from bet.pipeline.contracts.base import StrictBaseModel
from bet.pipeline.contracts.common import _validate_sha256


def get_git_commit_head(repo_root: Path) -> str:
    res = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=True,
    )
    return res.stdout.strip()


def get_git_tree_sha(repo_root: Path) -> str:
    res = subprocess.run(
        ["git", "rev-parse", "HEAD^{tree}"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=True,
    )
    return res.stdout.strip()


def compute_source_manifest_sha256(repo_root: Path) -> str:
    raw = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=str(repo_root),
        check=False,
        capture_output=True,
    )
    if raw.returncode != 0:
        return "UNKNOWN"
    entries: list[dict[str, Any]] = []
    for encoded in sorted(filter(None, raw.stdout.split(b"\0"))):
        relative = os.fsdecode(encoded)
        path = repo_root / relative
        if path.is_symlink():
            entries.append({"path": relative, "kind": "symlink", "target": os.readlink(path)})
        elif path.is_file():
            h = hashlib.sha256()
            with path.open("rb") as f:
                while chunk := f.read(65536):
                    h.update(chunk)
            entries.append({"path": relative, "kind": "file", "size": path.stat().st_size, "sha256": h.hexdigest()})
        else:
            entries.append({"path": relative, "kind": "deleted"})
    canonical = json.dumps(entries, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def get_sanitized_env_fingerprint() -> dict[str, str]:
    sensitive_keywords = ("KEY", "SECRET", "TOKEN", "PASSWORD", "AUTH", "COOKIE", "CREDENTIAL", "PRIVATE")
    fingerprint = {}
    for k, v in sorted(os.environ.items()):
        if any(kw in k.upper() for kw in sensitive_keywords):
            fingerprint[k] = "[REDACTED]"
        else:
            fingerprint[k] = str(v)
    return fingerprint


class BaseReceiptV1(StrictBaseModel):
    head_sha: str
    git_tree_sha: str
    source_manifest_sha256: str
    command_argv: list[str]
    cwd: str
    environment_fingerprint: dict[str, str] = Field(default_factory=dict)
    started_at: str
    finished_at: str
    exit_code: int
    stdout_sha256: str = ""
    stderr_sha256: str = ""
    artifact_sha256: str = ""

    @field_validator("head_sha", "git_tree_sha")
    @classmethod
    def check_sha40(cls, v: str) -> str:
        if not isinstance(v, str) or len(v) != 40 or not all(c in "0123456789abcdefABCDEF" for c in v):
            raise ValueError(f"Invalid 40-char commit/tree SHA: {v}")
        return v.lower()

    @field_validator("source_manifest_sha256")
    @classmethod
    def check_sha64(cls, v: str) -> str:
        res = _validate_sha256(v)
        if res is None:
            raise ValueError(f"Invalid 64-char hex source_manifest_sha256: {v}")
        return res

    @field_validator("started_at", "finished_at")
    @classmethod
    def check_iso_time(cls, v: str) -> str:
        if not v or v in ("UNKNOWN", ""):
            raise ValueError("Timestamp cannot be empty or UNKNOWN")
        return v


class CommandReceiptV1(BaseReceiptV1):
    status: str = "PASS"


class PytestReceiptV1(BaseReceiptV1):
    collected: int = Field(ge=0)
    passed: int = Field(ge=0)
    failed: int = Field(ge=0)
    skipped: int = Field(ge=0)
    errors: int = Field(ge=0)
    junit_sha256: str = ""


class ValidatorReceiptV1(BaseReceiptV1):
    status: str = "PASS"
    validator_name: str
    results: dict[str, Any] = Field(default_factory=dict)


class CertifierReceiptV1(BaseReceiptV1):
    status: str = "PASS"
    decision: str = "READY_FOR_BET_EXECUTOR_SESSION"
    READY_FOR_BET_EXECUTOR_ANALYSIS_SESSION: str = "YES"
    READY_FOR_PRICED_COUPON_SESSION: str = "NO"
    source: dict[str, Any] = Field(default_factory=dict)
    validators: list[dict[str, Any]] = Field(default_factory=list)
    test_run: dict[str, Any] = Field(default_factory=dict)


class AcceptanceReceiptV1(BaseReceiptV1):
    overall_status: str = "PASS"
    passed_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    total_count: int = Field(ge=0)
    results: dict[str, dict[str, Any]] = Field(default_factory=dict)


class MutationReceiptV1(BaseReceiptV1):
    mutation_score: str
    total_mutations: int = Field(ge=1)
    detected_mutations: int = Field(ge=0)
    all_detected: bool
    expected_mutation_set: list[str] = Field(default_factory=list)
    detected_mutation_set: list[str] = Field(default_factory=list)
    results: dict[str, dict[str, Any]] = Field(default_factory=dict)


class QualityReceiptV1(BaseReceiptV1):
    status: str = "PASS"
    format_lint_typecheck: str = "PASS"
    focused_tests: str = "PASS"
    pipeline_tests: str = "PASS"
    validators: str = "PASS"
    offline_e2e: str = "PASS"


def verify_receipt_bindings(
    receipt_data: dict[str, Any],
    expected_head: str,
    expected_tree: str,
    expected_manifest_sha: str,
) -> tuple[bool, str]:
    if not isinstance(receipt_data, dict):
        return False, "Receipt is not a JSON object"

    head = str(receipt_data.get("head_sha") or receipt_data.get("head") or "")
    tree = str(receipt_data.get("git_tree_sha") or receipt_data.get("tree") or "")
    manifest_sha = str(
        receipt_data.get("source_manifest_sha256")
        or (receipt_data.get("source") or {}).get("source_manifest_sha256")
        or ""
    )

    if not head or head.lower() != expected_head.lower():
        return False, f"Receipt head_sha '{head}' does not match target HEAD '{expected_head}'"

    if not tree or tree.lower() != expected_tree.lower():
        return False, f"Receipt git_tree_sha '{tree}' does not match target tree '{expected_tree}'"

    if not manifest_sha or manifest_sha.lower() != expected_manifest_sha.lower():
        return False, f"Receipt source_manifest_sha256 '{manifest_sha}' does not match target manifest SHA '{expected_manifest_sha}'"

    exit_code = receipt_data.get("exit_code")
    if exit_code is None and "return_code" in receipt_data:
        exit_code = receipt_data.get("return_code")
    if exit_code is None and (
        (receipt_data.get("test_run") or {}).get("return_code") is not None
    ):
        exit_code = (receipt_data.get("test_run") or {}).get("return_code")

    if exit_code != 0:
        return False, f"Receipt recorded non-zero exit code: {exit_code}"

    started = receipt_data.get("started_at") or receipt_data.get("generated_at_utc")
    finished = receipt_data.get("finished_at") or receipt_data.get("generated_at_utc")
    if not started or not finished or started in ("UNKNOWN", "") or finished in ("UNKNOWN", ""):
        return False, "Receipt missing valid timestamps"

    return True, "OK"
