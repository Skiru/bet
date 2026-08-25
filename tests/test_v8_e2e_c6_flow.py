from datetime import timedelta

from bet.pipeline.event_runtime_contract import CanonicalEventStatus
from bet.pipeline.runtime_plan import ContinuationStatus, RuntimePlanContinuationService
from tests._c6_helpers import PLAN_NOW, FakeExactAdapter, build_plan, provider_result


def test_c6_end_to_end_ready_and_refresh_paths(tmp_path):
    ready_plan = build_plan(tmp_path / "ready")
    ready = RuntimePlanContinuationService().validate_for_execution(
        conn=ready_plan["conn"],
        plan_id="plan-1",
        runtime_now_utc=PLAN_NOW + timedelta(minutes=1),
        adapters={"api_football": FakeExactAdapter(provider_result())},
        evidence_root=ready_plan["run_root"] / "continuation",
    )
    assert ready.status is ContinuationStatus.READY

    changed_plan = build_plan(tmp_path / "changed")
    changed = RuntimePlanContinuationService().validate_for_execution(
        conn=changed_plan["conn"],
        plan_id="plan-1",
        runtime_now_utc=PLAN_NOW + timedelta(minutes=1),
        adapters={
            "api_football": FakeExactAdapter(
                provider_result(canonical_status=CanonicalEventStatus.LIVE)
            )
        },
        evidence_root=changed_plan["run_root"] / "continuation",
    )
    assert changed.status is ContinuationStatus.PLAN_REFRESH_REQUIRED
    assert changed.changed_event_ids == ("1",)


def test_execute_existing_plan_stops_at_ready_before_s2(monkeypatch):
    import sys

    from scripts.pipeline_steps import run_daily_pipeline

    monkeypatch.setattr(
        "bet.pipeline.launch_bridge.verify_and_prepare_plan_continuation",
        lambda **kwargs: {
            "status": "PASS",
            "plan_status": "READY",
            "shadow_db_path": "/unused/shadow.db",
        },
    )
    monkeypatch.setattr(
        run_daily_pipeline.Orchestrator,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("S2-S8 must not execute in C6")
        ),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_daily_pipeline.py",
            "--date",
            "2027-07-30",
            "--run-id",
            "run-1",
            "--execute-existing-plan",
        ],
    )
    try:
        run_daily_pipeline.main()
    except SystemExit as exc:
        assert exc.code == 0
    else:
        raise AssertionError("continuation preflight must terminate before S2")
