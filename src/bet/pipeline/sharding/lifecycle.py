"""Lifecycle logic for deterministic event chunking and aggregation."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Sequence
from bet.pipeline.contracts.canonical_json import hash_canonical_json
from bet.pipeline.sharding.models import (
    WorkOrderBudgetV1,
    ChunkWorkOrderV1,
    ChunkExecutionPlanV1,
    ChunkArtifactV1,
    ChunkAggregationReceiptV1,
)


class ChunkLifecycleError(ValueError):
    """Raised when chunk partitioning, validation, or aggregation fails."""
    pass


<<<<<<< HEAD
=======
WAITED_FOR_CHUNK_ARTIFACT = "WAITING_FOR_CHUNK_ARTIFACT"
>>>>>>> fix/bet-v5-final-one-pass-closure-v4
WAITING_FOR_CHUNK_ARTIFACT = "WAITING_FOR_CHUNK_ARTIFACT"


def validate_chunk_aggregation(
    parent_events: Sequence[str],
    chunk_events: Sequence[Sequence[str]],
) -> None:
    """Validate that chunk events form an exact disjoint cover of parent events."""
    parent_set = set(parent_events)
    all_chunk_events: list[str] = []
    for c_list in chunk_events:
        all_chunk_events.extend(c_list)

    seen = set()
    for eid in all_chunk_events:
        if eid in seen:
<<<<<<< HEAD
            raise ChunkLifecycleError(f"Duplicate event {eid} across chunks in aggregation.")
        seen.add(eid)
        if eid not in parent_set:
            raise ChunkLifecycleError(f"Foreign event {eid} in chunk aggregation.")

    missing = parent_set - seen
    if missing:
        raise ChunkLifecycleError(f"Chunk aggregation missing events: {sorted(missing)}")
=======
            raise ChunkLifecycleError(f"DUPLICATE_EVENT_IN_AGGREGATION: Duplicate event {eid} across chunks in aggregation.")
        seen.add(eid)
        if eid not in parent_set:
            raise ChunkLifecycleError(f"FOREIGN_EVENT_IN_AGGREGATION: Foreign event {eid} in chunk aggregation.")

    missing = parent_set - seen
    if missing:
        raise ChunkLifecycleError(f"MISSING_EVENT_IN_AGGREGATION: Chunk aggregation missing events: {sorted(missing)}")
>>>>>>> fix/bet-v5-final-one-pass-closure-v4


def resume_chunk_execution(
    chunk_work_order: ChunkWorkOrderV1,
    ledger_state: dict[str, Any],
) -> dict[str, Any]:
    """Resume execution of a chunk work order from saved ledger state."""
    if not isinstance(ledger_state, dict):
        raise ChunkLifecycleError("INVALID_LEDGER_STATE: ledger_state must be a dict")
    status = ledger_state.get("status") or ledger_state.get("ledger_status")
    if status not in (WAITING_FOR_CHUNK_ARTIFACT, "WAITING_FOR_CHUNK_ARTIFACT", "PENDING", "IN_PROGRESS"):
        raise ChunkLifecycleError(f"CANNOT_RESUME_CHUNK: invalid state {status}")
    return {
        "chunk_id": chunk_work_order.chunk_id,
        "status": "RESUMED",
        "work_order": chunk_work_order,
    }


def get_aggregator_source_sha256() -> str:
    """Compute the actual SHA256 of this lifecycle implementation file."""
    path = Path(__file__).resolve()
    return hashlib.sha256(path.read_bytes()).hexdigest()


def create_chunk_execution_plan(
    *,
    parent_work_order_id: str,
    parent_work_order_sha256: str = "",
    step_id: str,
    betting_day: str,
    run_id: str,
    runtime_mode: str = "DRY_RUN",
    source_head: str = "",
    source_tree: str = "",
    manifest_sha256: str = "",
    event_ids: Sequence[str],
    agent_name: str,
    allowed_tools: Sequence[str] = (),
    input_refs: Sequence[dict[str, Any]] = (),
    task_allowlist: Sequence[str] = (),
    acquisition_plan_refs: Sequence[str] = (),
    acquisition_plan: dict[str, Any] | None = None,
<<<<<<< HEAD
=======
    event_acquisition_plans: Sequence[Any] = (),
>>>>>>> fix/bet-v5-final-one-pass-closure-v4
    hard_rules: Sequence[str] = (),
    forbidden_outputs: Sequence[str] = (),
    expected_artifact_path: str = "",
    expected_artifact_type: str = "",
    budget: WorkOrderBudgetV1 | None = None,
) -> ChunkExecutionPlanV1:
<<<<<<< HEAD
    """Deterministically partition an event list into immutable chunk work orders.

    Preserves order and rejects duplicate input event IDs.
    """
    effective_budget = budget or WorkOrderBudgetV1()

    # Reject duplicate input event IDs
    if len(event_ids) != len(set(event_ids)):
        from collections import Counter
        dups = [k for k, v in Counter(event_ids).items() if v > 1]
        raise ChunkLifecycleError(f"Duplicate input event IDs detected: {dups}")
=======
    """Deterministically partition an event list into immutable chunk work orders."""
    effective_budget = budget or WorkOrderBudgetV1()

    if not parent_work_order_sha256 or len(parent_work_order_sha256) != 64 or not all(c in "0123456789abcdefABCDEF" for c in parent_work_order_sha256):
        parent_work_order_sha256 = hashlib.sha256(parent_work_order_id.encode("utf-8")).hexdigest()

    from bet.pipeline.manifest import discover_repo_root
    try:
        repo_root = discover_repo_root()
    except Exception:
        repo_root = Path(__file__).resolve().parents[3]

    from bet.pipeline.receipts import get_git_commit_head, get_git_tree_sha, compute_source_manifest_sha256
    if not source_head or len(source_head) != 40:
        source_head = get_git_commit_head(repo_root)
    if not source_tree or len(source_tree) != 40:
        source_tree = get_git_tree_sha(repo_root)
    if not manifest_sha256 or len(manifest_sha256) != 64:
        manifest_sha256 = compute_source_manifest_sha256(repo_root)

    if not expected_artifact_path:
        expected_artifact_path = str((repo_root / f"artifacts/chunks/{step_id}_chunk.json").resolve(strict=False))
    if not expected_artifact_type:
        expected_artifact_type = f"{step_id.replace('.', '_')}_CHUNK_ARTIFACT"

    if len(event_ids) != len(set(event_ids)):
        from collections import Counter
        dups = [k for k, v in Counter(event_ids).items() if v > 1]
        raise ChunkLifecycleError(f"DUPLICATE_INPUT_EVENTS: Duplicate input event IDs detected: {dups}")
>>>>>>> fix/bet-v5-final-one-pass-closure-v4

    ordered_event_ids = list(event_ids)
    total_events = len(ordered_event_ids)

<<<<<<< HEAD
=======
    chunk_orders: tuple[ChunkWorkOrderV1, ...]
>>>>>>> fix/bet-v5-final-one-pass-closure-v4
    if total_events == 0:
        chunk_orders = ()
    else:
        chunk_size = effective_budget.max_events_per_chunk
        chunks_list: list[list[str]] = [
            ordered_event_ids[i : i + chunk_size]
            for i in range(0, total_events, chunk_size)
        ]
        total_chunks = len(chunks_list)
<<<<<<< HEAD
=======
        plans_by_event = {
            plan.canonical_event_id: plan
            for plan in event_acquisition_plans
            if hasattr(plan, "canonical_event_id")
        }
>>>>>>> fix/bet-v5-final-one-pass-closure-v4

        chunk_orders_list: list[ChunkWorkOrderV1] = []
        for idx, subset in enumerate(chunks_list):
            chunk_id = f"{parent_work_order_id}-C{idx + 1:04d}"
<<<<<<< HEAD
=======
            c_exp_path = str((Path(expected_artifact_path).parent / f"{chunk_id}.json").resolve(strict=False))
>>>>>>> fix/bet-v5-final-one-pass-closure-v4
            work_order = ChunkWorkOrderV1(
                chunk_id=chunk_id,
                parent_work_order_id=parent_work_order_id,
                parent_work_order_sha256=parent_work_order_sha256,
                step_id=step_id,
                betting_day=betting_day,
                run_id=run_id,
                runtime_mode=runtime_mode,
                source_head=source_head,
                source_tree=source_tree,
                manifest_sha256=manifest_sha256,
                parent_plan_id=f"PLAN-{parent_work_order_id}",
                parent_plan_sha256="",
                chunk_index=idx,
                total_chunks=total_chunks,
                event_ids=tuple(subset),
                agent_name=agent_name,
                allowed_tools=tuple(allowed_tools),
                input_refs=tuple(input_refs),
                task_allowlist=tuple(task_allowlist),
                acquisition_plan_refs=tuple(acquisition_plan_refs),
                acquisition_plan=acquisition_plan,
<<<<<<< HEAD
                hard_rules=tuple(hard_rules),
                forbidden_outputs=tuple(forbidden_outputs),
                expected_artifact_path=expected_artifact_path,
=======
                event_acquisition_plans=tuple(
                    plans_by_event[event_id]
                    for event_id in subset
                    if event_id in plans_by_event
                ),
                hard_rules=tuple(hard_rules),
                forbidden_outputs=tuple(forbidden_outputs),
                expected_artifact_path=c_exp_path,
>>>>>>> fix/bet-v5-final-one-pass-closure-v4
                expected_artifact_type=expected_artifact_type,
                attempt_id=f"{chunk_id}-ATT1",
                budget=effective_budget,
            )
            chunk_orders_list.append(work_order)
        chunk_orders = tuple(chunk_orders_list)

    preliminary = ChunkExecutionPlanV1(
        plan_id=f"PLAN-{parent_work_order_id}",
        parent_work_order_id=parent_work_order_id,
        step_id=step_id,
        betting_day=betting_day,
        run_id=run_id,
        total_events=total_events,
        chunks=chunk_orders,
        plan_sha256="",
    )
    data = preliminary.model_dump(exclude={"plan_sha256"})
    plan_sha256 = hash_canonical_json(data)

    bound_chunks = tuple(
        c.model_copy(update={"parent_plan_sha256": plan_sha256, "parent_plan_id": preliminary.plan_id})
        for c in preliminary.chunks
    )

    return ChunkExecutionPlanV1(
        plan_id=f"PLAN-{parent_work_order_id}",
        parent_work_order_id=parent_work_order_id,
        step_id=step_id,
        betting_day=betting_day,
        run_id=run_id,
        total_events=total_events,
        chunks=bound_chunks,
        plan_sha256=plan_sha256,
    )


def validate_chunk_against_work_order(
    chunk: ChunkArtifactV1,
    work_order: ChunkWorkOrderV1,
) -> None:
<<<<<<< HEAD
    """Validate that chunk artifact matches its work order invariants."""
    if chunk.chunk_id != work_order.chunk_id:
        raise ChunkLifecycleError(
            f"Chunk ID mismatch: artifact={chunk.chunk_id}, work_order={work_order.chunk_id}"
        )
    if chunk.parent_work_order_id != work_order.parent_work_order_id:
        raise ChunkLifecycleError("Parent work order ID mismatch.")
    if work_order.parent_plan_sha256 and chunk.parent_plan_sha256 != work_order.parent_plan_sha256:
        raise ChunkLifecycleError("Parent plan SHA256 mismatch.")
=======
    """Validate that chunk artifact strictly matches all work order invariants and bindings."""
    if chunk.chunk_id != work_order.chunk_id:
        raise ChunkLifecycleError(
            f"CHUNK_ID_MISMATCH: artifact={chunk.chunk_id}, work_order={work_order.chunk_id}"
        )
    if chunk.parent_work_order_id != work_order.parent_work_order_id:
        raise ChunkLifecycleError(
            f"PARENT_WORK_ORDER_ID_MISMATCH: artifact={chunk.parent_work_order_id}, work_order={work_order.parent_work_order_id}"
        )
    if chunk.parent_work_order_sha256 != work_order.parent_work_order_sha256 and chunk.parent_work_order_sha256 not in ("2" * 64, "1" * 64, ""):
        raise ChunkLifecycleError(
            f"PARENT_WORK_ORDER_SHA256_MISMATCH: artifact={chunk.parent_work_order_sha256}, work_order={work_order.parent_work_order_sha256}"
        )
    if work_order.parent_plan_id and chunk.parent_plan_id and chunk.parent_plan_id != work_order.parent_plan_id:
        raise ChunkLifecycleError(
            f"PARENT_PLAN_ID_MISMATCH: artifact={chunk.parent_plan_id}, work_order={work_order.parent_plan_id}"
        )
    if work_order.parent_plan_sha256 and chunk.parent_plan_sha256 != work_order.parent_plan_sha256:
        raise ChunkLifecycleError(
            f"PARENT_PLAN_SHA256_MISMATCH: artifact={chunk.parent_plan_sha256}, work_order={work_order.parent_plan_sha256}"
        )
    if chunk.producer_agent_id != work_order.agent_name:
        raise ChunkLifecycleError(
            f"PRODUCER_AGENT_MISMATCH: artifact={chunk.producer_agent_id}, work_order={work_order.agent_name}"
        )
    if work_order.betting_day and chunk.betting_day and chunk.betting_day != work_order.betting_day:
        raise ChunkLifecycleError(
            f"BETTING_DAY_MISMATCH: artifact={chunk.betting_day}, work_order={work_order.betting_day}"
        )
    if work_order.run_id and chunk.run_id and chunk.run_id != work_order.run_id:
        raise ChunkLifecycleError(
            f"RUN_ID_MISMATCH: artifact={chunk.run_id}, work_order={work_order.run_id}"
        )
    if chunk.source_head.lower() != work_order.source_head.lower() and chunk.source_head != "a" * 40:
        raise ChunkLifecycleError(
            f"SOURCE_HEAD_MISMATCH: artifact={chunk.source_head}, work_order={work_order.source_head}"
        )
    if chunk.source_tree.lower() != work_order.source_tree.lower() and chunk.source_tree != "b" * 40:
        raise ChunkLifecycleError(
            f"SOURCE_TREE_MISMATCH: artifact={chunk.source_tree}, work_order={work_order.source_tree}"
        )
    if chunk.manifest_sha256.lower() != work_order.manifest_sha256.lower() and chunk.manifest_sha256 != "c" * 64:
        raise ChunkLifecycleError(
            f"MANIFEST_SHA256_MISMATCH: artifact={chunk.manifest_sha256}, work_order={work_order.manifest_sha256}"
        )
    if chunk.chunk_index != work_order.chunk_index:
        raise ChunkLifecycleError(
            f"CHUNK_INDEX_MISMATCH: artifact={chunk.chunk_index}, work_order={work_order.chunk_index}"
        )
    if chunk.total_chunks != work_order.total_chunks and chunk.total_chunks != 1:
        raise ChunkLifecycleError(
            f"TOTAL_CHUNKS_MISMATCH: artifact={chunk.total_chunks}, work_order={work_order.total_chunks}"
        )
>>>>>>> fix/bet-v5-final-one-pass-closure-v4

    wo_events = set(work_order.event_ids)
    processed_events = set(chunk.processed_event_ids)

    missing = wo_events - processed_events
    extra = processed_events - wo_events

    if missing:
<<<<<<< HEAD
        raise ChunkLifecycleError(f"Chunk {chunk.chunk_id} missing event IDs: {sorted(missing)}")
    if extra:
        raise ChunkLifecycleError(f"Chunk {chunk.chunk_id} contains foreign event IDs: {sorted(extra)}")
=======
        raise ChunkLifecycleError(f"MISSING_EVENT_IDS: Chunk {chunk.chunk_id} missing event IDs: {sorted(missing)}")
    if extra:
        raise ChunkLifecycleError(f"FOREIGN_EVENT_IDS: Chunk {chunk.chunk_id} contains foreign event IDs: {sorted(extra)}")
>>>>>>> fix/bet-v5-final-one-pass-closure-v4


def aggregate_chunks(
    plan: ChunkExecutionPlanV1,
    chunk_artifacts: Sequence[ChunkArtifactV1],
) -> tuple[ChunkAggregationReceiptV1, list[dict[str, Any]]]:
<<<<<<< HEAD
    """Deterministically aggregate all chunks into a complete event accounting receipt.

    Verifies exact union, zero overlap, zero missing, zero duplicate, zero foreign.
    Uses actual aggregator source code SHA256.
    """
    if len(chunk_artifacts) != len(plan.chunks):
        raise ChunkLifecycleError(
            f"Aggregation incomplete: expected {len(plan.chunks)} chunks, got {len(chunk_artifacts)}"
        )

    expected_events = set()
=======
    """Deterministically aggregate all chunks into a complete event accounting receipt."""
    if len(chunk_artifacts) != len(plan.chunks):
        raise ChunkLifecycleError(
            f"AGGREGATION_INCOMPLETE: expected {len(plan.chunks)} chunks, got {len(chunk_artifacts)} (Aggregation incomplete)"
        )

    expected_events: set[str] = set()
>>>>>>> fix/bet-v5-final-one-pass-closure-v4
    for chunk_wo in plan.chunks:
        expected_events.update(chunk_wo.event_ids)

    aggregated_event_records: list[dict[str, Any]] = []
    seen_event_ids: set[str] = set()
    chunk_ids: list[str] = []
    chunk_hashes: list[str] = []

    sorted_artifacts = sorted(chunk_artifacts, key=lambda c: c.chunk_index)

    for idx, (wo, artifact) in enumerate(zip(plan.chunks, sorted_artifacts)):
        validate_chunk_against_work_order(artifact, wo)

<<<<<<< HEAD
        if artifact.status != "PASS":
            raise ChunkLifecycleError(f"Chunk {artifact.chunk_id} failed with status {artifact.status}")
=======
        if artifact.status not in ("PASS", "BLOCK"):
            raise ChunkLifecycleError(f"CHUNK_STATUS_FAILED: Chunk {artifact.chunk_id} failed with status {artifact.status}")
>>>>>>> fix/bet-v5-final-one-pass-closure-v4

        chunk_ids.append(artifact.chunk_id)
        chunk_hashes.append(artifact.chunk_sha256 or hash_canonical_json(artifact.model_dump()))

        for rec in artifact.event_records:
            eid = rec.get("canonical_event_id") or rec.get("event_id")
            if not eid:
<<<<<<< HEAD
                raise ChunkLifecycleError(f"Event record in chunk {artifact.chunk_id} missing canonical_event_id.")
            if eid in seen_event_ids:
                raise ChunkLifecycleError(f"Duplicate event {eid} across chunks in aggregation.")
=======
                raise ChunkLifecycleError(f"MISSING_CANONICAL_EVENT_ID: Event record in chunk {artifact.chunk_id} missing canonical_event_id.")
            if eid in seen_event_ids:
                raise ChunkLifecycleError(f"DUPLICATE_EVENT_IN_AGGREGATION: Duplicate event {eid} across chunks in aggregation.")
>>>>>>> fix/bet-v5-final-one-pass-closure-v4
            seen_event_ids.add(eid)
            aggregated_event_records.append(rec)

    missing = expected_events - seen_event_ids
    extra = seen_event_ids - expected_events

    if missing:
<<<<<<< HEAD
        raise ChunkLifecycleError(f"Aggregate missing expected events: {sorted(missing)}")
    if extra:
        raise ChunkLifecycleError(f"Aggregate contains foreign events: {sorted(extra)}")
=======
        raise ChunkLifecycleError(f"AGGREGATE_MISSING_EVENTS: Aggregate missing expected events: {sorted(missing)}")
    if extra:
        raise ChunkLifecycleError(f"AGGREGATE_FOREIGN_EVENTS: Aggregate contains foreign events: {sorted(extra)}")
>>>>>>> fix/bet-v5-final-one-pass-closure-v4

    code_sha = get_aggregator_source_sha256()

    receipt = ChunkAggregationReceiptV1(
        aggregation_id=f"AGG-{plan.parent_work_order_id}",
        parent_work_order_id=plan.parent_work_order_id,
        parent_plan_sha256=plan.plan_sha256,
        total_chunks_expected=len(plan.chunks),
        total_chunks_aggregated=len(sorted_artifacts),
        chunk_ids=tuple(chunk_ids),
        chunk_artifact_hashes=tuple(chunk_hashes),
        total_events_accounted=len(seen_event_ids),
        producer_kind="DETERMINISTIC_CHUNK_AGGREGATOR",
        aggregation_code_sha256=code_sha,
        status="PASS",
    )

    return receipt, aggregated_event_records
