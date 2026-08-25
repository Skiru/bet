from datetime import timedelta

from bet.pipeline.runtime_plan import (
    ContinuationStatus,
    RuntimePlanContinuationService,
    RuntimePlanRepository,
)
from tests._c6_helpers import PLAN_NOW, FakeExactAdapter, build_plan, provider_result


def _validate(built):
    return RuntimePlanContinuationService().validate_for_execution(
        conn=built["conn"],
        plan_id="plan-1",
        runtime_now_utc=PLAN_NOW + timedelta(minutes=1),
        adapters={"api_football": FakeExactAdapter(provider_result())},
        evidence_root=built["run_root"] / "continuation",
    )


def test_selection_ledger_tampering_fails_integrity(tmp_path):
    built = build_plan(tmp_path)
    built["selection"].write_text("tampered", encoding="utf-8")
    assert _validate(built).status is ContinuationStatus.PLAN_INTEGRITY_FAILED


def test_runtime_s1e_tampering_fails_integrity(tmp_path):
    built = build_plan(tmp_path)
    built["runtime_s1e"].write_text("tampered", encoding="utf-8")
    assert _validate(built).status is ContinuationStatus.PLAN_INTEGRITY_FAILED


def test_plan_checkpoint_tampering_fails_integrity(tmp_path):
    built = build_plan(tmp_path)
    built["checkpoint"].write_text("tampered", encoding="utf-8")
    assert _validate(built).status is ContinuationStatus.PLAN_INTEGRITY_FAILED


def test_plan_evidence_tampering_fails_integrity(tmp_path):
    built = build_plan(tmp_path)
    evidence_path = (
        built["conn"]
        .execute(
            "SELECT evidence_path FROM pipeline_provider_observation_attempts "
            "WHERE phase = 'PLAN'"
        )
        .fetchone()[0]
    )
    open(evidence_path, "w", encoding="utf-8").write("tampered")
    assert _validate(built).status is ContinuationStatus.PLAN_INTEGRITY_FAILED


def test_expired_plan_is_blocked(tmp_path):
    built = build_plan(tmp_path, maximum_age=timedelta(seconds=30))
    assert _validate(built).status is ContinuationStatus.PLAN_EXPIRED


def test_concurrent_continuation_is_blocked(tmp_path):
    built = build_plan(tmp_path)
    built["conn"].execute(
        "UPDATE pipeline_runtime_plans SET status = 'VALIDATING' "
        "WHERE plan_id = 'plan-1'"
    )
    built["conn"].commit()
    assert _validate(built).status is ContinuationStatus.CONCURRENT_VALIDATION


def test_frozen_selection_is_not_mutated(tmp_path):
    built = build_plan(tmp_path)
    before = (
        built["conn"]
        .execute("SELECT * FROM pipeline_runtime_event_selection")
        .fetchall()
    )
    result = _validate(built)
    after = (
        built["conn"]
        .execute("SELECT * FROM pipeline_runtime_event_selection")
        .fetchall()
    )
    assert result.status is ContinuationStatus.READY
    assert before == after


def test_frozen_selection_mutation_requires_refresh(tmp_path):
    built = build_plan(tmp_path)
    built["conn"].execute(
        "UPDATE pipeline_runtime_event_selection SET input_fingerprint = 'changed'"
    )
    built["conn"].commit()
    assert _validate(built).status is ContinuationStatus.PLAN_REFRESH_REQUIRED


def test_future_created_at_is_blocked(tmp_path):
    built = build_plan(tmp_path)
    built["conn"].execute(
        "UPDATE pipeline_runtime_plans SET created_at_utc = ? WHERE plan_id = 'plan-1'",
        ((PLAN_NOW + timedelta(hours=1)).isoformat(),),
    )
    built["conn"].commit()
    assert _validate(built).status is ContinuationStatus.PLAN_EXPIRED


def test_expiry_cannot_be_extended_by_row_mutation(tmp_path):
    built = build_plan(tmp_path)
    built["conn"].execute(
        "UPDATE pipeline_runtime_plans SET expires_at_utc = ? WHERE plan_id = 'plan-1'",
        ((PLAN_NOW + timedelta(minutes=6)).isoformat(),),
    )
    built["conn"].commit()
    assert _validate(built).status is ContinuationStatus.PLAN_EXPIRED


def test_invalidated_plan_cannot_be_reactivated(tmp_path):
    built = build_plan(tmp_path)
    built["conn"].execute(
        "UPDATE pipeline_runtime_plans SET status = 'INVALIDATED' "
        "WHERE plan_id = 'plan-1'"
    )
    built["conn"].commit()
    assert _validate(built).status is ContinuationStatus.PLAN_STATE_INVALID


def test_non_selected_event_does_not_enter_frozen_plan(tmp_path):
    built = build_plan(tmp_path)
    built["conn"].execute(
        """INSERT INTO pipeline_runtime_event_selection
           SELECT run_id, '2', NULL, betting_date, 'FINISHED', resume_action,
                  'FINISHED', observed_kickoff, observation_timestamp_utc,
                  provider, 'provider-2', source_evidence_sha256,
                  previous_analysis_status, previous_analysis_sha256,
                  previous_gate_status, previous_gate_sha256,
                  'other-fingerprint', reason, created_at
           FROM pipeline_runtime_event_selection WHERE canonical_event_id = '1'"""
    )
    built["conn"].commit()
    assert _validate(built).status is ContinuationStatus.READY
    assert (
        RuntimePlanRepository(built["conn"]).get("plan-1")["selected_event_count"] == 1
    )
