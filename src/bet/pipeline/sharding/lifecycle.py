"""Lifecycle logic for deterministic event chunking and aggregation."""
from __future__ import annotations

import hashlib
from typing import Any, Sequence
from bet.pipeline.contracts.canonical_json import hash_canonical_json, dumps_canonical_json
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


def create_chunk_execution_plan(
    *,
    parent_work_order_id: str,
    step_id: str,
    betting_day: str,
    run_id: str,
    event_ids: Sequence[str],
    agent_name: str,
    allowed_tools: Sequence[str] = (),
    budget: WorkOrderBudgetV1 | None = None,
) -> ChunkExecutionPlanV1:
    """Deterministically partition an event list into immutable chunk work orders.

    Events are sorted alphabetically by canonical event ID to guarantee identical chunking.
    """
    effective_budget = budget or WorkOrderBudgetV1()
    sorted_event_ids = sorted(set(event_ids))
    total_events = len(sorted_event_ids)

    if total_events == 0:
        chunk_orders = ()
    else:
        chunk_size = effective_budget.max_events_per_chunk
        chunks_list: list[list[str]] = [
            sorted_event_ids[i : i + chunk_size]
            for i in range(0, total_events, chunk_size)
        ]
        total_chunks = len(chunks_list)

        chunk_orders_list: list[ChunkWorkOrderV1] = []
        for idx, subset in enumerate(chunks_list):
            chunk_id = f"{parent_work_order_id}-C{idx + 1:04d}"
            work_order = ChunkWorkOrderV1(
                chunk_id=chunk_id,
                parent_work_order_id=parent_work_order_id,
                parent_plan_sha256="",
                chunk_index=idx,
                total_chunks=total_chunks,
                event_ids=tuple(subset),
                agent_name=agent_name,
                allowed_tools=tuple(allowed_tools),
                budget=effective_budget,
            )
            chunk_orders_list.append(work_order)
        chunk_orders = tuple(chunk_orders_list)

    # Compute preliminary plan without plan_sha256 to bind it
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

    # Bind plan_sha256 to chunk work orders
    bound_chunks = tuple(
        c.model_copy(update={"parent_plan_sha256": plan_sha256})
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
    """Validate that chunk artifact matches its work order invariants."""
    if chunk.chunk_id != work_order.chunk_id:
        raise ChunkLifecycleError(
            f"Chunk ID mismatch: artifact={chunk.chunk_id}, work_order={work_order.chunk_id}"
        )
    if chunk.parent_work_order_id != work_order.parent_work_order_id:
        raise ChunkLifecycleError("Parent work order ID mismatch.")
    if chunk.parent_plan_sha256 != work_order.parent_plan_sha256:
        raise ChunkLifecycleError("Parent plan SHA256 mismatch.")

    wo_events = set(work_order.event_ids)
    processed_events = set(chunk.processed_event_ids)

    missing = wo_events - processed_events
    extra = processed_events - wo_events

    if missing:
        raise ChunkLifecycleError(f"Chunk {chunk.chunk_id} missing event IDs: {sorted(missing)}")
    if extra:
        raise ChunkLifecycleError(f"Chunk {chunk.chunk_id} contains foreign event IDs: {sorted(extra)}")


def aggregate_chunks(
    plan: ChunkExecutionPlanV1,
    chunk_artifacts: Sequence[ChunkArtifactV1],
) -> tuple[ChunkAggregationReceiptV1, list[dict[str, Any]]]:
    """Deterministically aggregate all chunks into a complete event accounting receipt.

    Verifies exact union, zero overlap, zero missing, zero duplicate, zero foreign.
    """
    if len(chunk_artifacts) != len(plan.chunks):
        raise ChunkLifecycleError(
            f"Aggregation incomplete: expected {len(plan.chunks)} chunks, got {len(chunk_artifacts)}"
        )

    expected_events = set()
    for chunk_wo in plan.chunks:
        expected_events.update(chunk_wo.event_ids)

    aggregated_event_records: list[dict[str, Any]] = []
    seen_event_ids: set[str] = set()
    chunk_ids: list[str] = []
    chunk_hashes: list[str] = []

    sorted_artifacts = sorted(chunk_artifacts, key=lambda c: c.chunk_index)

    for idx, (wo, artifact) in enumerate(zip(plan.chunks, sorted_artifacts)):
        validate_chunk_against_work_order(artifact, wo)

        if artifact.status != "PASS":
            raise ChunkLifecycleError(f"Chunk {artifact.chunk_id} failed with status {artifact.status}")

        chunk_ids.append(artifact.chunk_id)
        chunk_hashes.append(artifact.chunk_sha256 or hash_canonical_json(artifact.model_dump()))

        for rec in artifact.event_records:
            eid = rec.get("canonical_event_id") or rec.get("event_id")
            if not eid:
                raise ChunkLifecycleError(f"Event record in chunk {artifact.chunk_id} missing canonical_event_id.")
            if eid in seen_event_ids:
                raise ChunkLifecycleError(f"Duplicate event {eid} across chunks in aggregation.")
            seen_event_ids.add(eid)
            aggregated_event_records.append(rec)

    missing = expected_events - seen_event_ids
    extra = seen_event_ids - expected_events

    if missing:
        raise ChunkLifecycleError(f"Aggregate missing expected events: {sorted(missing)}")
    if extra:
        raise ChunkLifecycleError(f"Aggregate contains foreign events: {sorted(extra)}")

    code_bytes = b"DETERMINISTIC_CHUNK_AGGREGATOR_V1"
    code_sha = hashlib.sha256(code_bytes).hexdigest()

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
