from pathlib import Path

import pytest


def test_runtime_execution_context_is_immutable_and_hash_bound(tmp_path: Path):
    from bet.pipeline.runtime_execution import RuntimeExecutionContext

    run_root = tmp_path / "run"
    run_root.mkdir()
    context = RuntimeExecutionContext.for_test(
        run_root=run_root, run_id="run-1", plan_id="plan-1"
    )
    assert len(context.context_sha256) == 64
    with pytest.raises(Exception):
        context.run_id = "other"


def test_context_rejects_path_escape(tmp_path: Path):
    from bet.pipeline.runtime_execution import RuntimeExecutionContext

    with pytest.raises(ValueError, match="CONTEXT_PATH_OUTSIDE_RUN_ROOT"):
        RuntimeExecutionContext.for_test(
            run_root=tmp_path / "run",
            run_id="run-1",
            plan_id="plan-1",
            shadow_db_path=tmp_path / "outside.db",
        )
