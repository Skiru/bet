from pathlib import Path

from bet.pipeline.event_stage_completion import EventRequiredStageCompletionEvaluator
from bet.pipeline.manifest import load_pipeline_manifest
from bet.pipeline.required_stage_chain import RequiredEventStageChainResolver


def test_missing_required_stage_prevents_complete(tmp_path: Path):
    chain = RequiredEventStageChainResolver().resolve_required_stages(
        manifest=load_pipeline_manifest(), event_identity="event-1", sport="football"
    )
    expected = {
        stage.stage_id: {
            "canonical_event_id": "event-1",
            "stage_id": stage.stage_id,
            "input_fingerprint": "fp",
            "stage_contract_version": stage.contract_version,
            "model_registry_sha256": None,
            "provider_config_sha256": None,
            "policy_config_sha256": None,
            "producer": "pipeline",
            "run_id": "run-1",
            "artifact_root": tmp_path,
            "latest_upstream_at": "2026-07-30T09:00:00Z",
        }
        for stage in chain.stages
    }
    evaluation = EventRequiredStageCompletionEvaluator().evaluate(
        chain=chain,
        stage_states={},
        artifacts={},
        receipts={},
        expected_by_stage=expected,
    )
    assert not evaluation.all_required_stages_reusable
    assert evaluation.missing_stage_ids == chain.stage_ids
    assert evaluation.earliest_non_reusable_stage == chain.stage_ids[0]
