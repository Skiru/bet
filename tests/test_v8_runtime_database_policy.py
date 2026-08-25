import sqlite3

import pytest


def test_database_policy_blocks_canonical_writes_and_allows_shadow(tmp_path):
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
    policy = RuntimeDatabaseAccessPolicy(context)
    with pytest.raises(Exception):
        policy.connect(RuntimeDbRole.CANONICAL_READ_ONLY).execute(
            "CREATE TABLE x (id INTEGER)"
        )
    shadow = policy.connect(RuntimeDbRole.SHADOW_READ_WRITE)
    shadow.execute("CREATE TABLE IF NOT EXISTS x (id INTEGER)")
    shadow.close()


def test_database_policy_rejects_unknown_role(tmp_path):
    from bet.pipeline.runtime_execution import (
        RuntimeDatabaseAccessPolicy,
        RuntimeExecutionContext,
    )

    root = tmp_path / "run"
    root.mkdir()
    context = RuntimeExecutionContext.for_test(
        run_root=root, run_id="run-1", plan_id="plan-1"
    )
    with pytest.raises(ValueError, match="UNKNOWN_RUNTIME_DB_ROLE"):
        RuntimeDatabaseAccessPolicy(context).connect("unknown")
