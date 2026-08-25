"""Frozen C6 selection enforcement and stage-aware C8 work planning."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable

from bet.pipeline.runtime_execution import (
    RuntimeDatabaseAccessPolicy,
    RuntimeDbRole,
    RuntimeExecutionContext,
    write_runtime_identity_receipt,
)


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class RuntimeStageWorkOrder:
    plan_id: str
    run_id: str
    selection_run_id: str
    stage_id: str
    stage_scope: str
    runtime_context_sha256: str
    selection_ledger_sha256: str
    runtime_s1e_sha256: str
    stage_work_plan_sha256: str
    required_chain_digest: str
    execute_event_ids: tuple[str, ...]
    reuse_event_ids: tuple[str, ...]
    run_input_event_ids: tuple[str, ...]

    def payload(self) -> dict[str, object]:
        return {"schema_version": 1, **self.__dict__}

    @property
    def sha256(self) -> str:
        return _digest(self.payload())


@dataclass(frozen=True)
class RuntimeSelectionScope:
    plan_id: str
    run_id: str
    selection_run_id: str
    selection_ledger_sha256: str
    runtime_s1e_sha256: str
    all_plan_event_ids: tuple[str, ...]
    analyze_event_ids: tuple[str, ...]
    already_complete_event_ids: tuple[str, ...]
    excluded_event_ids_by_reason: dict[str, tuple[str, ...]]
    stage_work_plan_sha256: str

    @classmethod
    def from_plan(cls, conn: sqlite3.Connection, context: RuntimeExecutionContext) -> "RuntimeSelectionScope":
        conn.row_factory = sqlite3.Row
        plan = conn.execute("SELECT * FROM pipeline_runtime_plans WHERE plan_id = ?", (context.plan_id,)).fetchone()
        if plan is None or plan["status"] != "READY":
            raise ValueError("BLOCKED_RUNTIME_SELECTION_REQUIRED")
        if plan["run_id"] != context.run_id or plan["selection_ledger_sha256"] != context.selection_ledger_sha256:
            raise ValueError("RUNTIME_SELECTION_PLAN_BINDING_MISMATCH")
        rows = conn.execute("SELECT canonical_event_id, decision, reason FROM pipeline_runtime_event_selection WHERE run_id = ? ORDER BY canonical_event_id", (context.selection_run_id,)).fetchall()
        if not rows:
            raise ValueError("BLOCKED_RUNTIME_SELECTION_REQUIRED")
        all_ids = tuple(str(row["canonical_event_id"]) for row in rows)
        analyze = tuple(str(row["canonical_event_id"]) for row in rows if row["decision"] == "ANALYZE_FROM_S2")
        complete = tuple(str(row["canonical_event_id"]) for row in rows if row["decision"] == "ALREADY_VALID_COMPLETE")
        excluded = {str(row["canonical_event_id"]): (str(row["decision"]), str(row["reason"])) for row in rows if row["decision"] not in {"ANALYZE_FROM_S2", "ALREADY_VALID_COMPLETE"}}
        work_rows = [dict(row) for row in conn.execute("SELECT stage_id, canonical_event_id, action, stage_input_fingerprint, dependency_set_sha256 FROM pipeline_runtime_event_stage_work WHERE plan_id = ? ORDER BY stage_id, canonical_event_id", (context.plan_id,)).fetchall()]
        return cls(context.plan_id, context.run_id, context.selection_run_id, context.selection_ledger_sha256, context.runtime_s1e_sha256, all_ids, analyze, complete, excluded, _digest(work_rows))

    def assert_plan_ready(self) -> None:
        if not self.plan_id or not self.all_plan_event_ids:
            raise ValueError("BLOCKED_RUNTIME_SELECTION_REQUIRED")

    def assert_event_in_plan(self, event_id: str) -> None:
        if str(event_id) not in self.all_plan_event_ids:
            raise ValueError("BLOCKED_EVENT_OUTSIDE_RUNTIME_SCOPE")

    def assert_explicit_event_ids(self, stage_id: str, event_ids: Iterable[str]) -> None:
        ids = tuple(str(item) for item in event_ids)
        if len(ids) != len(set(ids)):
            raise ValueError("BLOCKED_EVENT_OUTSIDE_RUNTIME_SCOPE")
        for event_id in ids:
            self.assert_event_executable_for_stage(stage_id, event_id)

    def assert_event_executable_for_stage(self, stage_id: str, event_id: str) -> None:
        self.assert_event_in_plan(event_id)
        if str(event_id) not in self.analyze_event_ids:
            raise ValueError("BLOCKED_EVENT_OUTSIDE_RUNTIME_SCOPE")

    def assert_event_reusable_for_stage(self, stage_id: str, event_id: str) -> None:
        self.assert_event_in_plan(event_id)

    def list_event_stage_execution(self, conn: sqlite3.Connection, stage_id: str) -> tuple[str, ...]:
        return tuple(str(row[0]) for row in conn.execute("SELECT canonical_event_id FROM pipeline_runtime_event_stage_work WHERE plan_id = ? AND stage_id = ? AND action = 'EXECUTE' ORDER BY canonical_event_id", (self.plan_id, stage_id)).fetchall())

    def list_event_stage_reuse(self, conn: sqlite3.Connection, stage_id: str) -> tuple[str, ...]:
        return tuple(str(row[0]) for row in conn.execute("SELECT canonical_event_id FROM pipeline_runtime_event_stage_work WHERE plan_id = ? AND stage_id = ? AND action = 'REUSE' ORDER BY canonical_event_id", (self.plan_id, stage_id)).fetchall())

    def verify_database_bindings(self, conn: sqlite3.Connection) -> None:
        for row in conn.execute("SELECT canonical_event_id FROM pipeline_runtime_event_stage_work WHERE plan_id = ?", (self.plan_id,)):
            self.assert_event_in_plan(str(row[0]))


class RuntimeStageExecutionPlanner:
    """Persist exactly one EXECUTE/REUSE action per planned event stage."""
    def build(self, conn: sqlite3.Connection, scope: RuntimeSelectionScope, event_stages: Iterable[str], run_stages: Iterable[str], reusable: dict[tuple[str, str], bool], fingerprints: dict[str, str], chain_digest: str) -> str:
        now = datetime.now(UTC).isoformat()
        for stage_id in event_stages:
            for event_id in scope.analyze_event_ids:
                action = "REUSE" if reusable.get((stage_id, event_id), False) else "EXECUTE"
                conn.execute("INSERT INTO pipeline_runtime_event_stage_work VALUES (?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, ?)", (scope.plan_id, scope.run_id, scope.selection_run_id, stage_id, event_id, action, "C5_REUSABLE" if action == "REUSE" else "C5_EXECUTION_REQUIRED", fingerprints.get(event_id, ""), _digest([stage_id, event_id]), chain_digest, scope.selection_ledger_sha256, now))
            for event_id in scope.already_complete_event_ids:
                conn.execute("INSERT INTO pipeline_runtime_event_stage_work VALUES (?, ?, ?, ?, ?, NULL, 'REUSE', 'ALREADY_VALID_COMPLETE', ?, ?, ?, ?, ?)", (scope.plan_id, scope.run_id, scope.selection_run_id, stage_id, event_id, fingerprints.get(event_id, ""), _digest([stage_id, event_id]), chain_digest, scope.selection_ledger_sha256, now))
        event_inputs = tuple(sorted(set(scope.analyze_event_ids + scope.already_complete_event_ids)))
        for stage_id in run_stages:
            conn.execute("INSERT INTO pipeline_runtime_run_stage_work VALUES (?, ?, ?, 'EXECUTE', ?, ?, ?, ?)", (scope.plan_id, scope.run_id, stage_id, _digest(event_inputs), _digest(list(event_stages)), scope.selection_ledger_sha256, now))
        conn.commit()
        rows = [tuple(row) for row in conn.execute("SELECT plan_id, stage_id, canonical_event_id, action FROM pipeline_runtime_event_stage_work WHERE plan_id = ? ORDER BY stage_id, canonical_event_id", (scope.plan_id,)).fetchall()]
        return _digest(rows)


@dataclass(frozen=True)
class PreparedRuntimeStageExecution:
    context: RuntimeExecutionContext
    scope: RuntimeSelectionScope
    work_order: RuntimeStageWorkOrder
    execute_event_ids: tuple[str, ...]
    reuse_event_ids: tuple[str, ...]


def prepare_runtime_stage_execution(
    *, context: RuntimeExecutionContext, stage_id: str, work_order_path: Path,
    expected_work_order_sha256: str,
) -> PreparedRuntimeStageExecution:
    """Single fail-closed wrapper preflight for LIVE_ANALYSIS_SHADOW stages."""
    context.verify_filesystem_bindings()
    conn = RuntimeDatabaseAccessPolicy(context).connect(RuntimeDbRole.SHADOW_READ_WRITE)
    try:
        scope = RuntimeSelectionScope.from_plan(conn, context)
        raw = Path(work_order_path).read_bytes()
        if _digest(json.loads(raw)) != expected_work_order_sha256:
            raise ValueError("WORK_ORDER_SCOPE_MISMATCH")
        payload = json.loads(raw)
        if payload.get("stage_id") != stage_id or payload.get("plan_id") != context.plan_id:
            raise ValueError("WORK_ORDER_SCOPE_MISMATCH")
        order = RuntimeStageWorkOrder(**{key: tuple(value) if key.endswith("_ids") else value for key, value in payload.items() if key != "schema_version"})
        execute = scope.list_event_stage_execution(conn, stage_id)
        reuse = scope.list_event_stage_reuse(conn, stage_id)
        if tuple(order.execute_event_ids) != execute or tuple(order.reuse_event_ids) != reuse:
            raise ValueError("WORK_ORDER_SCOPE_MISMATCH")
        scope.assert_explicit_event_ids(stage_id, execute)
        write_runtime_identity_receipt(context, stage_id)
        return PreparedRuntimeStageExecution(context, scope, order, execute, reuse)
    finally:
        conn.close()


def get_scoped_fixtures_for_stage(db_path: Path | str, stage_id: str, allowed_fixture_ids: set[int]) -> list[dict[str, object]]:
    """Compatibility scoped direct-SQL gateway. Empty scope never means all."""
    if not allowed_fixture_ids:
        raise ValueError("BLOCKED_RUNTIME_SELECTION_REQUIRED")
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        placeholders = ",".join("?" for _ in allowed_fixture_ids)
        return [dict(row) for row in conn.execute(f"SELECT * FROM fixtures WHERE id IN ({placeholders}) ORDER BY id", tuple(sorted(allowed_fixture_ids))).fetchall()]
    finally:
        conn.close()
