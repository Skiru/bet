import pytest


def test_scope_requires_ready_plan_and_blocks_excluded_ids(tmp_path):
    from tests._c6_helpers import build_plan
    from bet.pipeline.runtime_execution import RuntimeExecutionContext
    from bet.pipeline.runtime_selection import RuntimeSelectionScope

    built = build_plan(tmp_path)
    built["conn"].execute("UPDATE pipeline_runtime_plans SET status = 'READY'")
    built["conn"].commit()
    context = RuntimeExecutionContext.for_test(run_root=built["run_root"], run_id="run-1", plan_id="plan-1", shadow_db_path=built["shadow"])
    # C6 artifacts bind the production context in actual execution; use DB scope behavior here.
    built["conn"].execute("UPDATE pipeline_runtime_plans SET selection_ledger_sha256 = ?", (context.selection_ledger_sha256,))
    built["conn"].commit()
    scope = RuntimeSelectionScope.from_plan(built["conn"], context)
    assert scope.analyze_event_ids == ("1",)
    with pytest.raises(ValueError, match="BLOCKED_EVENT_OUTSIDE_RUNTIME_SCOPE"):
        scope.assert_explicit_event_ids("S2", ["outside"])
