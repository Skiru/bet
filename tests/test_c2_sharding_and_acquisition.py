"""C2 acceptance tests for specialist sharding, chunking, and evidence acquisition."""
from __future__ import annotations

import pytest
from bet.pipeline.sharding.models import (
    WorkOrderBudgetV1,
    ChunkWorkOrderV1,
    ChunkExecutionPlanV1,
    ChunkArtifactV1,
    RetrievalReceiptV1,
    DatabaseQueryReceiptV1,
    EvidenceBundleV1,
)
from bet.pipeline.sharding.lifecycle import (
    ChunkLifecycleError,
    create_chunk_execution_plan,
    validate_chunk_against_work_order,
    aggregate_chunks,
)


def test_547_events_chunking_accounting():
    """Verify a 547-event universe is deterministically chunked and aggregated with 100% accounting."""
    event_ids = [f"EVT_{i:04d}" for i in range(1, 548)]  # 547 events
    budget = WorkOrderBudgetV1(max_events_per_chunk=15)

    plan = create_chunk_execution_plan(
        parent_work_order_id="WO_547_EVENTS",
        step_id="S2.3",
        betting_day="2026-07-27",
        run_id="RUN_SHARD_547",
        event_ids=event_ids,
        agent_name="bet-researcher",
        budget=budget,
    )

    # 547 / 15 = 36 full chunks of 15 + 1 remainder chunk of 7 = 37 total chunks
    assert len(plan.chunks) == 37
    assert plan.total_events == 547

    # Simulate chunk artifacts execution
    chunk_artifacts: list[ChunkArtifactV1] = []
    for chunk_wo in plan.chunks:
        records = [
            {
                "canonical_event_id": eid,
                "terminal_status": "CONTINUE",
                "sport": "football",
            }
            for eid in chunk_wo.event_ids
        ]
        art = ChunkArtifactV1(
            chunk_id=chunk_wo.chunk_id,
            parent_work_order_id=chunk_wo.parent_work_order_id,
            parent_plan_sha256=chunk_wo.parent_plan_sha256,
            chunk_index=chunk_wo.chunk_index,
            status="PASS",
            producer_agent_id="bet-researcher",
            processed_event_ids=chunk_wo.event_ids,
            event_records=records,
        )
        chunk_artifacts.append(art)

    # Aggregate
    receipt, aggregated_records = aggregate_chunks(plan, chunk_artifacts)

    assert receipt.status == "PASS"
    assert receipt.total_chunks_aggregated == 37
    assert receipt.total_events_accounted == 547
    assert len(aggregated_records) == 547


def test_missing_chunk_blocks_aggregation():
    """Verify aggregation fails if any chunk artifact is missing."""
    event_ids = [f"EVT_{i:03d}" for i in range(1, 31)]  # 30 events -> 2 chunks of 15
    plan = create_chunk_execution_plan(
        parent_work_order_id="WO_MISSING_CHUNK",
        step_id="S2.3",
        betting_day="2026-07-27",
        run_id="RUN_SHARD_MISSING",
        event_ids=event_ids,
        agent_name="bet-researcher",
    )

    # Create only chunk 1 artifact, omitting chunk 2
    c1 = plan.chunks[0]
    art1 = ChunkArtifactV1(
        chunk_id=c1.chunk_id,
        parent_work_order_id=c1.parent_work_order_id,
        parent_plan_sha256=c1.parent_plan_sha256,
        chunk_index=c1.chunk_index,
        status="PASS",
        producer_agent_id="bet-researcher",
        processed_event_ids=c1.event_ids,
        event_records=[{"canonical_event_id": eid, "terminal_status": "CONTINUE"} for eid in c1.event_ids],
    )

    with pytest.raises(ChunkLifecycleError, match="Aggregation incomplete"):
        aggregate_chunks(plan, [art1])


<<<<<<< HEAD
=======
def test_complete_blocked_chunks_are_accounted():
    """Verify complete fail-closed chunk artifacts can be aggregated."""
    event_ids = [f"EVT_{i:03d}" for i in range(1, 31)]
    plan = create_chunk_execution_plan(
        parent_work_order_id="WO_BLOCKED_CHUNKS",
        step_id="S2.3",
        betting_day="2026-07-27",
        run_id="RUN_SHARD_BLOCKED",
        event_ids=event_ids,
        agent_name="bet-researcher",
    )

    artifacts = []
    for chunk_wo in plan.chunks:
        artifacts.append(
            ChunkArtifactV1(
                chunk_id=chunk_wo.chunk_id,
                parent_work_order_id=chunk_wo.parent_work_order_id,
                parent_plan_sha256=chunk_wo.parent_plan_sha256,
                chunk_index=chunk_wo.chunk_index,
                status="BLOCK",
                producer_agent_id="bet-researcher",
                processed_event_ids=chunk_wo.event_ids,
                event_records=[
                    {"canonical_event_id": eid, "terminal_status": "BLOCK"}
                    for eid in chunk_wo.event_ids
                ],
            )
        )

    receipt, records = aggregate_chunks(plan, artifacts)

    assert receipt.total_chunks_aggregated == 2
    assert receipt.total_events_accounted == 30
    assert len(records) == 30




>>>>>>> fix/bet-v5-final-one-pass-closure-v4
def test_foreign_event_in_chunk_rejected():
    """Verify a chunk artifact containing an unassigned foreign event is rejected."""
    event_ids = ["EVT_001", "EVT_002"]
    plan = create_chunk_execution_plan(
        parent_work_order_id="WO_FOREIGN",
        step_id="S2.3",
        betting_day="2026-07-27",
        run_id="RUN_SHARD_FOREIGN",
        event_ids=event_ids,
        agent_name="bet-researcher",
    )

    c1 = plan.chunks[0]
    art_foreign = ChunkArtifactV1(
        chunk_id=c1.chunk_id,
        parent_work_order_id=c1.parent_work_order_id,
        parent_plan_sha256=c1.parent_plan_sha256,
        chunk_index=c1.chunk_index,
        status="PASS",
        producer_agent_id="bet-researcher",
        processed_event_ids=("EVT_001", "EVT_002", "EVT_FOREIGN_999"),
        event_records=[],
    )

    with pytest.raises(ChunkLifecycleError, match="foreign event IDs"):
        validate_chunk_against_work_order(art_foreign, c1)


def test_provenance_honesty_classification():
    """Verify receipts correctly distinguish system-verified vs agent-attested provenance."""
    rec = RetrievalReceiptV1(
        receipt_id="REC_001",
        tool="webfetch",
        query_or_url="https://example.com/lineups",
        retrieved_at="2026-07-27T10:00:00Z",
        normalized_excerpt="Confirmed lineup: Team A vs Team B",
        content_sha256="abc123hash",
        provenance_level="AGENT_ATTESTED_TOOL_RESULT",
    )
    assert rec.provenance_level == "AGENT_ATTESTED_TOOL_RESULT"

    db_rec = DatabaseQueryReceiptV1(
        query_id="QRY_001",
        query_purpose="Check team injuries",
        query_sql="SELECT * FROM team_injuries WHERE team_id = 'ENG_ARS'",
        row_count=2,
        executed_at="2026-07-27T10:00:00Z",
        result_sha256="dbres123hash",
        provenance_level="AGENT_ATTESTED_TOOL_RESULT",
    )
    assert db_rec.provenance_level == "AGENT_ATTESTED_TOOL_RESULT"
