"""Resolve event and run completion chains from the canonical manifest."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from bet.pipeline.manifest import (
    PipelineManifest,
    PipelineManifestError,
    load_pipeline_manifest,
    validate_pipeline_manifest,
)
from bet.pipeline.stage_conditions import (
    GLOBAL_STAGE_CONDITION_REGISTRY,
    StageConditionContext,
    StageConditionRegistry,
)


@dataclass(frozen=True)
class RequiredStage:
    stage_id: str
    stage_scope: str
    contract_version: str
    completion_policy: str
    condition_id: str | None
    condition_result: bool | None
    dependencies: tuple[str, ...]
    reason: str
    producer: str
    uses_model_registry: bool
    uses_provider_config: bool
    uses_policy_config: bool


@dataclass(frozen=True)
class RequiredEventStageChain:
    stages: tuple[RequiredStage, ...]
    final_automated_stage: str
    digest: str

    @property
    def stage_ids(self) -> tuple[str, ...]:
        return tuple(stage.stage_id for stage in self.stages)


@dataclass(frozen=True)
class RequiredRunStageChain:
    stages: tuple[RequiredStage, ...]
    final_automated_stage: str
    digest: str

    @property
    def stage_ids(self) -> tuple[str, ...]:
        return tuple(stage.stage_id for stage in self.stages)


# Compatibility alias retained for callers introduced during C5.
RequiredStageChain = RequiredEventStageChain


@dataclass(frozen=True)
class ResolvedAutomatedStageChains:
    event: RequiredEventStageChain
    run: RequiredRunStageChain


class RequiredEventStageChainResolver:
    """Resolve required stages between explicit manifest graph boundaries."""

    def __init__(
        self, condition_registry: StageConditionRegistry | None = None
    ) -> None:
        self.condition_registry = condition_registry or GLOBAL_STAGE_CONDITION_REGISTRY

    def resolve_stage_chains(
        self,
        *,
        manifest: PipelineManifest | None = None,
        manifest_path=None,
        event_identity: str,
        sport: str,
        event_format: str | None = None,
        market_context: dict | None = None,
        runtime_configuration: dict | None = None,
        provider_capabilities: tuple[str, ...] = (),
        start_stage: str = "S2",
        stop_before_stage: str = "S9",
    ) -> ResolvedAutomatedStageChains:
        manifest = manifest or load_pipeline_manifest(manifest_path)
        errors = validate_pipeline_manifest(manifest)
        if errors:
            raise PipelineManifestError(f"Invalid pipeline manifest: {errors}")
        steps = [step for step in manifest.steps if step.id]
        ids = [step.id for step in steps]
        if start_stage not in ids or stop_before_stage not in ids:
            raise PipelineManifestError("Required chain boundary is absent")
        start = ids.index(start_stage)
        stop = ids.index(stop_before_stage)
        if start >= stop:
            raise PipelineManifestError("Required chain boundaries are contradictory")

        context = StageConditionContext(
            sport=sport,
            event_format=event_format,
            market_families=tuple(
                sorted((market_context or {}).get("market_families", ()))
            ),
            provider_capabilities=tuple(sorted(provider_capabilities)),
            runtime_configuration=runtime_configuration or {},
            manifest_version=manifest.schema_version,
        )
        known = set(ids)
        seen = set(ids[:start])
        event_stages: list[RequiredStage] = []
        run_stages: list[RequiredStage] = []
        condition_results: dict[str, bool] = {}
        for step in steps[start:stop]:
            if not step.automated or step.stage_scope == "human":
                raise PipelineManifestError(
                    f"Non-automated or human stage inside automated boundary: {step.id}"
                )
            dependencies = tuple(step.depends_on or ())
            missing = [
                dependency for dependency in dependencies if dependency not in known
            ]
            if missing:
                raise PipelineManifestError(
                    f"Stage {step.id} has unknown dependencies: {missing}"
                )
            unresolved = [
                dependency for dependency in dependencies if dependency not in seen
            ]
            if unresolved:
                raise PipelineManifestError(
                    f"Stage {step.id} is not topologically ordered: {unresolved}"
                )
            seen.add(step.id)
            condition_result = None
            required = step.completion_policy == "required"
            if step.completion_policy == "conditional":
                condition_result = self.condition_registry.evaluate(
                    step.condition_id, context
                )
                condition_results[step.id] = condition_result
                required = condition_result
            elif step.completion_policy in {"optional", "human_only"}:
                required = False
            if not required:
                continue
            completion = step.completion or {}
            required_stage = RequiredStage(
                stage_id=step.id,
                stage_scope=step.stage_scope,
                contract_version=str(completion.get("schema_version", 1)),
                completion_policy=step.completion_policy,
                condition_id=step.condition_id,
                condition_result=condition_result,
                dependencies=dependencies,
                reason=(
                    "required by canonical manifest"
                    if condition_result is None
                    else f"condition {step.condition_id} evaluated true"
                ),
                producer=step.agent or "",
                uses_model_registry=step.uses_model_registry,
                uses_provider_config=step.uses_provider_config,
                uses_policy_config=step.uses_policy_config,
            )
            if step.stage_scope == "event":
                event_stages.append(required_stage)
            elif step.stage_scope == "run":
                run_stages.append(required_stage)
            else:
                raise PipelineManifestError(
                    f"Unsupported automated stage scope: {step.stage_scope}"
                )
        if not event_stages:
            raise PipelineManifestError("Required event stage chain is empty")

        common = {
            "pipeline_id": manifest.pipeline_id,
            "manifest_version": manifest.schema_version,
            "start_stage": start_stage,
            "stop_before_stage": stop_before_stage,
            "event_identity": event_identity,
            "sport": sport,
            "event_format": event_format,
            "market_context": market_context or {},
            "runtime_configuration": runtime_configuration or {},
            "provider_capabilities": tuple(sorted(provider_capabilities)),
            "condition_results": condition_results,
        }

        def digest(scope: str, stages: list[RequiredStage]) -> str:
            payload = {
                **common,
                "scope": scope,
                "stages": [stage.__dict__ for stage in stages],
            }
            return hashlib.sha256(
                json.dumps(payload, sort_keys=True, default=list).encode("utf-8")
            ).hexdigest()

        final_automated = steps[stop - 1].id
        return ResolvedAutomatedStageChains(
            event=RequiredEventStageChain(
                tuple(event_stages), final_automated, digest("event", event_stages)
            ),
            run=RequiredRunStageChain(
                tuple(run_stages), final_automated, digest("run", run_stages)
            ),
        )

    def resolve_required_stages(self, **kwargs) -> RequiredEventStageChain:
        """Compatibility API returning only the event-level chain."""
        return self.resolve_stage_chains(**kwargs).event
