def test_stage_planner_persists_execute_and_reuse(tmp_path):
    from tests._c6_helpers import build_plan
    from bet.pipeline.runtime_selection import RuntimeSelectionScope, RuntimeStageExecutionPlanner

    built = build_plan(tmp_path)
    built["conn"].execute("UPDATE pipeline_runtime_plans SET status = 'READY'")
    built["conn"].commit()
    scope = RuntimeSelectionScope("plan-1", "run-1", "run-1", "ledger", "s1e", ("1",), ("1",), (), {}, "")
    digest = RuntimeStageExecutionPlanner().build(built["conn"], scope, ["S2", "S3"], ["S6"], {("S2", "1"): True}, {"1": "fp"}, "chain")
    assert len(digest) == 64
    assert scope.list_event_stage_reuse(built["conn"], "S2") == ("1",)
    assert scope.list_event_stage_execution(built["conn"], "S3") == ("1",)
