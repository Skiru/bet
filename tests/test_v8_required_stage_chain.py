
import pytest

from bet.pipeline.manifest import PipelineManifestError, load_pipeline_manifest
from bet.pipeline.required_stage_chain import RequiredEventStageChainResolver
from bet.pipeline.stage_conditions import GLOBAL_STAGE_CONDITION_REGISTRY


def test_canonical_manifest_resolves_topological_automated_chain():
    chain = RequiredEventStageChainResolver().resolve_required_stages(
        manifest=load_pipeline_manifest(), event_identity="event-1", sport="football"
    )
    assert chain.stage_ids[0] == "S2"
    assert chain.final_automated_stage == "S8"
    assert "S9" not in chain.stage_ids
    positions = {stage_id: index for index, stage_id in enumerate(chain.stage_ids)}
    for stage in chain.stages:
        for dependency in stage.dependencies:
            if dependency in positions:
                assert positions[dependency] < positions[stage.stage_id]


def test_required_chain_digest_is_deterministic_and_context_bound():
    resolver = RequiredEventStageChainResolver()
    manifest = load_pipeline_manifest()
    first = resolver.resolve_required_stages(
        manifest=manifest, event_identity="event-1", sport="football"
    )
    second = resolver.resolve_required_stages(
        manifest=manifest, event_identity="event-1", sport="football"
    )
    changed = resolver.resolve_required_stages(
        manifest=manifest, event_identity="event-1", sport="basketball"
    )
    assert first.digest == second.digest
    assert first.digest != changed.digest


def test_missing_dependency_fails_closed():
    manifest = load_pipeline_manifest()
    target = manifest.get_step("S3")
    target.depends_on = ["UNKNOWN_STAGE"]
    with pytest.raises(PipelineManifestError):
        RequiredEventStageChainResolver().resolve_required_stages(
            manifest=manifest, event_identity="event-1", sport="football"
        )


def test_event_and_run_chains_are_separate_and_exclude_s9():
    chains = RequiredEventStageChainResolver().resolve_stage_chains(
        manifest=load_pipeline_manifest(), event_identity="event-1", sport="football"
    )
    assert "S3" in chains.event.stage_ids
    assert "S6" in chains.run.stage_ids
    assert "S6" not in chains.event.stage_ids
    assert "S9" not in chains.event.stage_ids
    assert "S9" not in chains.run.stage_ids


def test_optional_event_stage_is_not_required():
    manifest = load_pipeline_manifest()
    manifest.get_step("S5").completion_policy = "optional"
    chain = RequiredEventStageChainResolver().resolve_required_stages(
        manifest=manifest, event_identity="event-1", sport="football"
    )
    assert "S5" not in chain.stage_ids


def test_conditional_stage_is_included_only_when_predicate_is_true():
    condition_id = "test_football_condition"
    GLOBAL_STAGE_CONDITION_REGISTRY._predicates[condition_id] = lambda context: (
        context.sport == "football"
    )
    try:
        manifest = load_pipeline_manifest()
        stage = manifest.get_step("S5")
        stage.completion_policy = "conditional"
        stage.condition_id = condition_id
        resolver = RequiredEventStageChainResolver()
        football = resolver.resolve_required_stages(
            manifest=manifest, event_identity="event-1", sport="football"
        )
        basketball = resolver.resolve_required_stages(
            manifest=manifest, event_identity="event-1", sport="basketball"
        )
        assert "S5" in football.stage_ids
        assert "S5" not in basketball.stage_ids
        assert football.digest != basketball.digest
    finally:
        GLOBAL_STAGE_CONDITION_REGISTRY._predicates.pop(condition_id, None)
