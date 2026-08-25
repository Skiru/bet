def test_live_shadow_write_is_not_generic_allow_write(tmp_path):
    from bet.pipeline.runtime_execution import (
        RuntimeExecutionContext,
        require_stage_capability,
    )

    root = tmp_path / "run"
    root.mkdir()
    context = RuntimeExecutionContext.for_test(
        run_root=root, run_id="run-1", plan_id="plan-1"
    )
    require_stage_capability(context, "S2")


def test_s9_and_bookmaker_are_hard_blocked(tmp_path):
    import pytest
    from bet.pipeline.runtime_execution import (
        RuntimeExecutionContext,
        require_stage_capability,
    )

    root = tmp_path / "run"
    root.mkdir()
    context = RuntimeExecutionContext.for_test(
        run_root=root, run_id="run-1", plan_id="plan-1"
    )
    with pytest.raises(PermissionError, match="BLOCKED_S9_HUMAN_ONLY"):
        require_stage_capability(context, "S9")
    with pytest.raises(PermissionError, match="BLOCKED_BOOKMAKER_INTERACTION"):
        require_stage_capability(context, "BOOKMAKER_LOGIN")
