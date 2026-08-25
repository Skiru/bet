"""Evaluate reuse of every stage required for one event."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from bet.pipeline.event_runtime_contract import compute_runtime_input_fingerprint
from bet.pipeline.required_stage_chain import RequiredStageChain
from bet.pipeline.reusable_stage_output import (
    ReusableStageOutputValidator,
    ReuseValidationResult,
)


def build_stage_input_fingerprint(
    *,
    base_fingerprint_input: dict[str, Any],
    stage,
    required_chain_digest: str,
    dependency_output_hashes: dict[str, str | None],
    code_manifest_sha256: str,
    policy_config_sha256: str | None,
    provider_config_sha256: str | None,
    model_registry_sha256: str | None,
) -> str:
    payload = {
        **base_fingerprint_input,
        "stage_id": stage.stage_id,
        "stage_contract_version": stage.contract_version,
        "dependency_output_hashes": dependency_output_hashes,
        "policy_config_sha256": policy_config_sha256
        if stage.uses_policy_config
        else None,
        "provider_config_sha256": provider_config_sha256
        if stage.uses_provider_config
        else None,
        "model_registry_sha256": model_registry_sha256
        if stage.uses_model_registry
        else None,
        "required_event_chain_digest": required_chain_digest,
        "code_manifest_sha256": code_manifest_sha256,
    }
    return compute_runtime_input_fingerprint(payload)


@dataclass(frozen=True)
class EventStageCompletionEvaluation:
    required_stage_ids: tuple[str, ...]
    reusable_stage_ids: tuple[str, ...]
    invalid_stage_ids: tuple[str, ...]
    missing_stage_ids: tuple[str, ...]
    earliest_non_reusable_stage: str | None
    all_required_stages_reusable: bool
    per_stage_results: dict[str, ReuseValidationResult]
    required_chain_digest: str


class EventRequiredStageCompletionEvaluator:
    def __init__(self, validator: ReusableStageOutputValidator | None = None):
        self.validator = validator or ReusableStageOutputValidator()

    def evaluate(
        self,
        *,
        chain: RequiredStageChain,
        stage_states: dict[str, dict[str, Any]],
        artifacts: dict[str, dict[str, Any]],
        receipts: dict[str, dict[str, Any]],
        expected_by_stage: dict[str, dict[str, Any]],
    ) -> EventStageCompletionEvaluation:
        results = {}
        reusable = []
        missing = []
        invalid = []
        for stage in chain.stages:
            state = stage_states.get(stage.stage_id)
            expected = expected_by_stage.get(stage.stage_id)
            if expected is None:
                raise ValueError(f"Missing expected contract for {stage.stage_id}")
            result = self.validator.validate(
                state,
                artifacts.get(stage.stage_id),
                receipts.get(stage.stage_id),
                **expected,
            )
            results[stage.stage_id] = result
            if result.reusable:
                reusable.append(stage.stage_id)
            elif state is None:
                missing.append(stage.stage_id)
            else:
                invalid.append(stage.stage_id)
        non_reusable = [
            stage.stage_id for stage in chain.stages if stage.stage_id not in reusable
        ]
        return EventStageCompletionEvaluation(
            required_stage_ids=chain.stage_ids,
            reusable_stage_ids=tuple(reusable),
            invalid_stage_ids=tuple(invalid),
            missing_stage_ids=tuple(missing),
            earliest_non_reusable_stage=non_reusable[0] if non_reusable else None,
            all_required_stages_reusable=not non_reusable,
            per_stage_results=results,
            required_chain_digest=chain.digest,
        )

    def evaluate_from_repository(
        self,
        *,
        canonical_event_id: str,
        chain: RequiredStageChain,
        repository,
        base_fingerprint_input: dict[str, Any],
        code_manifest_sha256: str,
        policy_config_sha256_by_stage: dict[str, str | None],
        provider_config_sha256_by_stage: dict[str, str | None],
        model_registry_sha256_by_stage: dict[str, str | None],
        latest_upstream_at: datetime,
        run_id: str,
    ) -> EventStageCompletionEvaluation:
        """Build stage-specific contexts and validate canonical repository rows."""
        states: dict[str, dict[str, Any]] = {}
        artifacts: dict[str, dict[str, Any]] = {}
        receipts: dict[str, dict[str, Any]] = {}
        expected: dict[str, dict[str, Any]] = {}
        output_hashes: dict[str, str] = {}
        chain_ids = set(chain.stage_ids)
        for stage in chain.stages:
            state = repository.get_stage_state(canonical_event_id, stage.stage_id)
            artifact = repository.get_artifact(canonical_event_id, stage.stage_id)
            receipt = repository.get_receipt(canonical_event_id, stage.stage_id)
            dependency_hashes = {
                dependency: output_hashes.get(dependency)
                for dependency in stage.dependencies
                if dependency in chain_ids
            }
            fingerprint = build_stage_input_fingerprint(
                base_fingerprint_input=base_fingerprint_input,
                stage=stage,
                required_chain_digest=chain.digest,
                dependency_output_hashes=dependency_hashes,
                code_manifest_sha256=code_manifest_sha256,
                policy_config_sha256=policy_config_sha256_by_stage.get(stage.stage_id),
                provider_config_sha256=provider_config_sha256_by_stage.get(
                    stage.stage_id
                ),
                model_registry_sha256=model_registry_sha256_by_stage.get(
                    stage.stage_id
                ),
            )
            if state:
                states[stage.stage_id] = state
                if state.get("output_sha256"):
                    output_hashes[stage.stage_id] = state["output_sha256"]
            if artifact:
                artifacts[stage.stage_id] = artifact
            if receipt:
                receipts[stage.stage_id] = receipt
            expected[stage.stage_id] = {
                "canonical_event_id": canonical_event_id,
                "stage_id": stage.stage_id,
                "input_fingerprint": fingerprint,
                "stage_contract_version": stage.contract_version,
                "model_registry_sha256": model_registry_sha256_by_stage.get(
                    stage.stage_id
                )
                if stage.uses_model_registry
                else None,
                "provider_config_sha256": provider_config_sha256_by_stage.get(
                    stage.stage_id
                )
                if stage.uses_provider_config
                else None,
                "policy_config_sha256": policy_config_sha256_by_stage.get(
                    stage.stage_id
                )
                if stage.uses_policy_config
                else None,
                "producer": stage.producer,
                "run_id": state.get("run_id", run_id) if state else run_id,
                "artifact_root": Path(artifact["artifact_root"])
                if artifact
                else Path("."),
                "latest_upstream_at": latest_upstream_at,
                "code_manifest_sha256": code_manifest_sha256,
                "dependency_output_hashes": dependency_hashes,
            }
        return self.evaluate(
            chain=chain,
            stage_states=states,
            artifacts=artifacts,
            receipts=receipts,
            expected_by_stage=expected,
        )
