from datetime import timedelta

import pytest

from bet.pipeline.event_runtime_contract import (
    CanonicalEventStatus,
    ProviderRequestStatus,
)
from bet.pipeline.runtime_plan import ContinuationStatus, RuntimePlanContinuationService
from tests._c6_helpers import PLAN_NOW, FakeExactAdapter, build_plan, provider_result


def _continue(built, result):
    adapter = FakeExactAdapter(result)
    validation = RuntimePlanContinuationService().validate_for_execution(
        conn=built["conn"],
        plan_id="plan-1",
        runtime_now_utc=PLAN_NOW + timedelta(minutes=1),
        adapters={"api_football": adapter},
        evidence_root=built["run_root"] / "evidence" / "continuation",
    )
    return validation, adapter


def test_identical_fresh_exact_revalidation_is_ready(tmp_path):
    built = build_plan(tmp_path)
    validation, adapter = _continue(built, provider_result())
    assert validation.status is ContinuationStatus.READY
    assert adapter.calls == 1
    assert adapter.received_ids == ["provider-1"]
    row = (
        built["conn"]
        .execute(
            "SELECT phase FROM pipeline_provider_observation_attempts WHERE id = ?",
            (validation.continuation_attempt_ids[0],),
        )
        .fetchone()
    )
    assert row[0] == "CONTINUATION"


@pytest.mark.parametrize(
    "result",
    [
        provider_result(request_status=ProviderRequestStatus.FAILED),
        provider_result(request_status=ProviderRequestStatus.UNSUPPORTED),
        provider_result(request_status=ProviderRequestStatus.IDENTITY_MISSING),
        provider_result(request_status=ProviderRequestStatus.IDENTITY_CONFLICT),
    ],
)
def test_non_success_revalidation_requires_new_plan(tmp_path, result):
    validation, _ = _continue(build_plan(tmp_path), result)
    assert validation.status is ContinuationStatus.PLAN_REFRESH_REQUIRED


def test_equivalent_iso_kickoff_is_not_material_change(tmp_path):
    result = provider_result(kickoff="2027-07-30T16:00:00+02:00")
    validation, _ = _continue(build_plan(tmp_path), result)
    assert validation.status is ContinuationStatus.READY


def test_live_status_requires_plan_refresh(tmp_path):
    result = provider_result(canonical_status=CanonicalEventStatus.LIVE)
    validation, _ = _continue(build_plan(tmp_path), result)
    assert validation.status is ContinuationStatus.PLAN_REFRESH_REQUIRED


def test_participant_change_requires_plan_refresh(tmp_path):
    result = provider_result(home="Different Team")
    validation, _ = _continue(build_plan(tmp_path), result)
    assert validation.status is ContinuationStatus.PLAN_REFRESH_REQUIRED


def test_provider_event_id_change_requires_plan_refresh(tmp_path):
    result = provider_result(provider_event_id="changed")
    validation, _ = _continue(build_plan(tmp_path), result)
    assert validation.status is ContinuationStatus.PLAN_REFRESH_REQUIRED


def test_ready_result_is_idempotent_without_second_provider_call(tmp_path):
    built = build_plan(tmp_path)
    adapter = FakeExactAdapter(provider_result())
    service = RuntimePlanContinuationService()
    first = service.validate_for_execution(
        conn=built["conn"],
        plan_id="plan-1",
        runtime_now_utc=PLAN_NOW + timedelta(minutes=1),
        adapters={"api_football": adapter},
        evidence_root=built["run_root"] / "continuation",
    )
    second = service.validate_for_execution(
        conn=built["conn"],
        plan_id="plan-1",
        runtime_now_utc=PLAN_NOW + timedelta(minutes=2),
        adapters={"api_football": adapter},
        evidence_root=built["run_root"] / "continuation",
    )
    assert first.status is second.status is ContinuationStatus.READY
    assert adapter.calls == 1


def test_insufficient_fresh_lead_requires_plan_refresh(tmp_path):
    built = build_plan(tmp_path)
    validation, _ = _continue(built, provider_result(kickoff="2027-07-30T10:10:00Z"))
    assert validation.status is ContinuationStatus.PLAN_REFRESH_REQUIRED
    assert "INSUFFICIENT_LEAD" in validation.reason_codes["1"]


def test_kickoff_change_requires_plan_refresh(tmp_path):
    validation, _ = _continue(
        build_plan(tmp_path), provider_result(kickoff="2027-07-30T14:05:00Z")
    )
    assert validation.status is ContinuationStatus.PLAN_REFRESH_REQUIRED


def test_missing_provider_event_id_requires_plan_refresh(tmp_path):
    validation, _ = _continue(
        build_plan(tmp_path), provider_result(provider_event_id=None)
    )
    assert validation.status is ContinuationStatus.PLAN_REFRESH_REQUIRED


def test_provider_exception_is_persisted_as_failed_attempt(tmp_path):
    built = build_plan(tmp_path)

    class RaisingAdapter:
        def fetch_exact_event(self, **kwargs):
            raise TimeoutError("network timeout")

    validation = RuntimePlanContinuationService().validate_for_execution(
        conn=built["conn"],
        plan_id="plan-1",
        runtime_now_utc=PLAN_NOW + timedelta(minutes=1),
        adapters={"api_football": RaisingAdapter()},
        evidence_root=built["run_root"] / "continuation",
    )
    assert validation.status is ContinuationStatus.PLAN_REFRESH_REQUIRED
    status = (
        built["conn"]
        .execute(
            "SELECT request_status FROM pipeline_provider_observation_attempts "
            "WHERE id = ?",
            (validation.continuation_attempt_ids[0],),
        )
        .fetchone()[0]
    )
    assert status == "FAILED"
