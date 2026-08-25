import os
import sqlite3


def test_two_runtime_probes_share_shadow_identity(tmp_path):
    from bet.pipeline.runtime_execution import (
        RuntimeDatabaseAccessPolicy,
        RuntimeDbRole,
        RuntimeExecutionContext,
    )

    root = tmp_path / "run"
    root.mkdir()
    canonical = tmp_path / "canonical.db"
    sqlite3.connect(canonical).close()
    context = RuntimeExecutionContext.for_test(
        run_root=root, run_id="run-1", plan_id="plan-1", canonical_db_path=canonical
    )
    from scripts.pipeline_steps._runner import ScriptInvocation, run_scripts

    env = context.to_child_env()
    env.update(
        {
            "PATH": os.environ["PATH"],
            "BET_PIPELINE_LIVE_ACK": "I_UNDERSTAND_LIVE_PROVIDER_CALLS",
        }
    )
    old_env = dict(os.environ)
    os.environ.clear()
    os.environ.update(env)
    try:
        assert (
            run_scripts(
                [ScriptInvocation("pipeline_steps/s2_runtime_context_probe.py")],
                runtime_mode="LIVE_ANALYSIS_SHADOW",
                dry_run=False,
                allow_live_network=True,
            )
            == 0
        )
        assert (
            run_scripts(
                [ScriptInvocation("pipeline_steps/s3_runtime_context_probe.py")],
                runtime_mode="LIVE_ANALYSIS_SHADOW",
                dry_run=False,
                allow_live_network=True,
            )
            == 0
        )
    finally:
        os.environ.clear()
        os.environ.update(old_env)
    db = RuntimeDatabaseAccessPolicy(context).connect(RuntimeDbRole.SHADOW_READ_WRITE)
    assert db.execute("SELECT COUNT(*) FROM runtime_context_probe").fetchone()[0] == 2
    db.close()
    assert (root / "receipts" / "runtime_identity_S2.json").read_text().find(
        context.context_sha256
    ) >= 0
    assert (root / "receipts" / "runtime_identity_S3.json").read_text().find(
        context.context_sha256
    ) >= 0
