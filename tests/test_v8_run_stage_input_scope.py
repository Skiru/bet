def test_run_stage_executes_once_and_inputs_are_plan_bound(tmp_path):
    from tests._c6_helpers import build_plan
    from bet.pipeline.runtime_selection import RuntimeSelectionScope, RuntimeStageExecutionPlanner
    built = build_plan(tmp_path)
    scope = RuntimeSelectionScope("plan-1", "run-1", "run-1", "x" * 64, "y" * 64, ("1",), ("1",), (), {}, "")
    RuntimeStageExecutionPlanner().build(built["conn"], scope, ["S2"], ["S6"], {}, {"1": "fp"}, "chain")
    assert built["conn"].execute("SELECT COUNT(*) FROM pipeline_runtime_run_stage_work").fetchone()[0] == 1
