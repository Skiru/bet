def test_already_complete_event_is_reuse_not_execute(tmp_path):
    from tests._c6_helpers import build_plan
    from bet.pipeline.runtime_selection import RuntimeSelectionScope, RuntimeStageExecutionPlanner
    built = build_plan(tmp_path)
    scope = RuntimeSelectionScope("plan-1", "run-1", "run-1", "x" * 64, "y" * 64, ("1",), (), ("1",), {}, "")
    RuntimeStageExecutionPlanner().build(built["conn"], scope, ["S2"], [], {}, {"1": "fp"}, "chain")
    assert scope.list_event_stage_execution(built["conn"], "S2") == ()
    assert scope.list_event_stage_reuse(built["conn"], "S2") == ("1",)
