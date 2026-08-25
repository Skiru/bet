import os


def test_child_environment_preserves_os_and_runtime_identity(tmp_path):
    from bet.pipeline.runtime_execution import (
        RuntimeExecutionContext,
        build_runtime_child_environment,
    )

    root = tmp_path / "run"
    root.mkdir()
    context = RuntimeExecutionContext.for_test(
        run_root=root, run_id="run-1", plan_id="plan-1"
    )
    env = build_runtime_child_environment(
        parent_environment={
            "PATH": os.environ["PATH"],
            "HOME": "/tmp/home",
            "BET_DB_PATH": "/wrong",
            "BET_PIPELINE_LIVE_ACK": "I_UNDERSTAND_LIVE_PROVIDER_CALLS",
        },
        runtime_context=context,
        provider_secret_allowlist=(),
    )
    assert env["BET_PIPELINE_RUN_ID"] == "run-1"
    assert env["BET_DB_PATH"] == str(context.shadow_db_path)
    assert env["BET_PIPELINE_SHADOW_WRITE_ALLOWED"] == "1"
    assert env.get("DRY_RUN") != "1"
    assert env["PATH"]


def test_child_environment_drops_bookmaker_and_generic_write_flags(tmp_path):
    from bet.pipeline.runtime_execution import (
        RuntimeExecutionContext,
        build_runtime_child_environment,
    )

    root = tmp_path / "run"
    root.mkdir()
    context = RuntimeExecutionContext.for_test(
        run_root=root, run_id="run-1", plan_id="plan-1"
    )
    env = build_runtime_child_environment(
        parent_environment={
            "PATH": "/bin",
            "BETCLIC_PASSWORD": "secret",
            "FORCE_ALLOW_WRITE": "1",
            "BET_PIPELINE_LIVE_ACK": "I_UNDERSTAND_LIVE_PROVIDER_CALLS",
        },
        runtime_context=context,
        provider_secret_allowlist=(),
    )
    assert "BETCLIC_PASSWORD" not in env
    assert "FORCE_ALLOW_WRITE" not in env
