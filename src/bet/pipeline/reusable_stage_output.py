"""Cryptographic validation for reusable event-stage output."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from bet.pipeline.event_runtime_contract import parse_utc_timestamp


class ReuseStatus(StrEnum):
    REUSABLE = "REUSABLE"
    MISSING_STATE = "MISSING_STATE"
    INVALID_STATUS = "INVALID_STATUS"
    FINGERPRINT_MISMATCH = "FINGERPRINT_MISMATCH"
    CONTRACT_MISMATCH = "CONTRACT_MISMATCH"
    MODEL_MISMATCH = "MODEL_MISMATCH"
    CONFIG_MISMATCH = "CONFIG_MISMATCH"
    OUTPUT_MISSING = "OUTPUT_MISSING"
    OUTPUT_HASH_MISMATCH = "OUTPUT_HASH_MISMATCH"
    RECEIPT_MISSING = "RECEIPT_MISSING"
    RECEIPT_HASH_MISMATCH = "RECEIPT_HASH_MISMATCH"
    RECEIPT_BINDING_MISMATCH = "RECEIPT_BINDING_MISMATCH"
    UPSTREAM_NEWER = "UPSTREAM_NEWER"
    DEPENDENCY_STALE = "DEPENDENCY_STALE"
    UNSAFE_PATH = "UNSAFE_PATH"


@dataclass(frozen=True)
class ReuseValidationResult:
    status: ReuseStatus
    reason: str

    @property
    def reusable(self) -> bool:
        return self.status is ReuseStatus.REUSABLE


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _safe_file(
    path_value: str | Path | None, root: Path, missing: ReuseStatus
) -> tuple[Path | None, ReuseValidationResult | None]:
    if not path_value:
        return None, ReuseValidationResult(missing, "Path is missing")
    path = Path(path_value).resolve()
    root = root.resolve()
    try:
        path.relative_to(root)
    except ValueError:
        return None, ReuseValidationResult(
            ReuseStatus.UNSAFE_PATH, f"Path escapes artifact root: {path}"
        )
    if not path.exists() or not path.is_file():
        return None, ReuseValidationResult(missing, f"Regular file is missing: {path}")
    return path, None


class ReusableStageOutputValidator:
    def validate(
        self,
        stage_state: dict[str, Any] | None,
        artifact: dict[str, Any] | None,
        receipt: dict[str, Any] | None,
        *,
        canonical_event_id: str,
        stage_id: str,
        input_fingerprint: str,
        stage_contract_version: str,
        model_registry_sha256: str | None,
        provider_config_sha256: str | None,
        policy_config_sha256: str | None,
        producer: str,
        run_id: str,
        artifact_root: Path,
        latest_upstream_at: datetime,
        code_manifest_sha256: str | None = None,
        dependency_output_hashes: dict[str, str | None] | None = None,
    ) -> ReuseValidationResult:
        if not stage_state:
            return ReuseValidationResult(
                ReuseStatus.MISSING_STATE, "Event stage state is missing"
            )
        if str(stage_state.get("status", "")).upper() not in {
            "PASS",
            "SUCCESS",
            "COMPLETED",
        }:
            return ReuseValidationResult(
                ReuseStatus.INVALID_STATUS, "Stage status is not reusable"
            )
        if stage_state.get("dependency_status", "CURRENT") in {"STALE", "INVALIDATED"}:
            return ReuseValidationResult(
                ReuseStatus.DEPENDENCY_STALE, "Dependency state is stale"
            )
        if (
            code_manifest_sha256 is not None
            and stage_state.get("source_manifest_sha256") != code_manifest_sha256
        ):
            return ReuseValidationResult(
                ReuseStatus.CONTRACT_MISMATCH, "Code/source manifest digest changed"
            )
        if stage_state.get("input_fingerprint") != input_fingerprint:
            return ReuseValidationResult(
                ReuseStatus.FINGERPRINT_MISMATCH, "Input fingerprint changed"
            )
        if stage_state.get("stage_contract_version") != stage_contract_version:
            return ReuseValidationResult(
                ReuseStatus.CONTRACT_MISMATCH, "Stage contract version changed"
            )
        if stage_state.get("model_registry_sha256") != model_registry_sha256:
            return ReuseValidationResult(
                ReuseStatus.MODEL_MISMATCH, "Model registry digest changed"
            )
        if (
            stage_state.get("provider_config_sha256") != provider_config_sha256
            or stage_state.get("policy_config_sha256") != policy_config_sha256
        ):
            return ReuseValidationResult(
                ReuseStatus.CONFIG_MISMATCH,
                "Provider or policy configuration digest changed",
            )
        if not artifact:
            return ReuseValidationResult(
                ReuseStatus.OUTPUT_MISSING, "Artifact registry row is missing"
            )
        output_path, error = _safe_file(
            artifact.get("path"), artifact_root, ReuseStatus.OUTPUT_MISSING
        )
        if error:
            return error
        output_sha = _sha256(output_path)
        expected_output_sha = stage_state.get("output_sha256")
        if (
            output_sha != expected_output_sha
            or artifact.get("sha256") != expected_output_sha
        ):
            return ReuseValidationResult(
                ReuseStatus.OUTPUT_HASH_MISMATCH,
                "Output bytes do not match stage state and registry",
            )
        if dependency_output_hashes is not None:
            try:
                registered_dependencies = json.loads(
                    artifact.get("dependency_output_hashes_json", "{}")
                )
            except (TypeError, json.JSONDecodeError):
                return ReuseValidationResult(
                    ReuseStatus.DEPENDENCY_STALE,
                    "Registered dependency output hashes are invalid",
                )
            if registered_dependencies != dependency_output_hashes:
                return ReuseValidationResult(
                    ReuseStatus.DEPENDENCY_STALE,
                    "Dependency output hashes changed",
                )
        if not receipt:
            return ReuseValidationResult(
                ReuseStatus.RECEIPT_MISSING, "Receipt registry row is missing"
            )
        receipt_path, error = _safe_file(
            receipt.get("path"), artifact_root, ReuseStatus.RECEIPT_MISSING
        )
        if error:
            return error
        receipt_sha = _sha256(receipt_path)
        expected_receipt_sha = stage_state.get("receipt_sha256")
        if (
            receipt_sha != expected_receipt_sha
            or receipt.get("sha256") != expected_receipt_sha
        ):
            return ReuseValidationResult(
                ReuseStatus.RECEIPT_HASH_MISMATCH,
                "Receipt bytes do not match stage state and registry",
            )
        try:
            payload = json.loads(receipt_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return ReuseValidationResult(
                ReuseStatus.RECEIPT_BINDING_MISMATCH, "Receipt is not valid JSON"
            )
        bindings = {
            "canonical_event_id": canonical_event_id,
            "stage_id": stage_id,
            "output_sha256": output_sha,
            "input_fingerprint": input_fingerprint,
            "producer": producer,
            "run_id": run_id,
        }
        if any(payload.get(key) != value for key, value in bindings.items()):
            return ReuseValidationResult(
                ReuseStatus.RECEIPT_BINDING_MISMATCH,
                "Receipt bindings do not match current stage",
            )
        completed_at = parse_utc_timestamp(stage_state["completed_at"])
        if completed_at <= parse_utc_timestamp(latest_upstream_at):
            return ReuseValidationResult(
                ReuseStatus.UPSTREAM_NEWER,
                "Relevant upstream input is newer than output",
            )
        return ReuseValidationResult(
            ReuseStatus.REUSABLE,
            "Artifact, receipt, fingerprint, digests, and freshness are valid",
        )
