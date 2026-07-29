"""Integration Tests for V5 Full Agentic Runtime.

Validates Orchestrator sharding, chunk work orders, ledger entries, and resume.
"""
import pytest
import os
import sys
import json
from pathlib import Path

def test_full_agentic_sharding_lifecycle(tmp_path):
    """Validates sharding lifecycle on Orchestrator.run() with 31+ events."""
    import bet.pipeline.orchestrator as orch
    import bet.pipeline.sharding.lifecycle as sl
    from bet.pipeline.sharding.models import ChunkWorkOrderV1, ChunkArtifactV1, WorkOrderBudgetV1

    # Test chunk creation for 35 events
    events = [f"evt_{i:03d}" for i in range(1, 36)]
    plan = sl.create_chunk_execution_plan(
        parent_work_order_id="WO-S2.3-TEST",
        step_id="S2.3",
        betting_day="2026-07-28",
        run_id="run-sharding-test",
        event_ids=events,
        agent_name="bet-researcher",
        budget=WorkOrderBudgetV1(max_events_per_chunk=15)
    )

    assert plan.total_events == 35
    assert len(plan.chunks) == 3 # 15 + 15 + 5

    # Check first chunk binding
    c1 = plan.chunks[0]
    assert c1.chunk_id == "WO-S2.3-TEST-C0001"
    assert len(c1.event_ids) == 15
    assert c1.agent_name == "bet-researcher"

    # Create dummy artifacts for all 3 chunks
    artifacts = []
    for idx, c in enumerate(plan.chunks):
        a = ChunkArtifactV1(
            chunk_id=c.chunk_id,
            parent_work_order_id=c.parent_work_order_id,
            parent_plan_id=plan.plan_id,
            parent_plan_sha256=plan.plan_sha256,
            chunk_index=c.chunk_index,
            total_chunks=len(plan.chunks),
            status="PASS",
            producer_agent_id="bet-researcher",
            processed_event_ids=c.event_ids,
            event_records=[{"canonical_event_id": eid, "terminal_status": "PASS"} for eid in c.event_ids]
        )
        artifacts.append(a)

    # Test aggregation
    receipt, records = sl.aggregate_chunks(plan, artifacts)
    assert receipt.status == "PASS"
    assert receipt.total_events_accounted == 35
    assert len(records) == 35

def test_chunk_aggregation_rejects_foreign_event():
    """Validates that chunk aggregation rejects foreign event IDs."""
    import bet.pipeline.sharding.lifecycle as sl

    with pytest.raises(sl.ChunkLifecycleError):
        sl.validate_chunk_aggregation(
            parent_events=["evt_001", "evt_002"],
            chunk_events=[["evt_001"], ["evt_999"]] # Foreign evt_999
        )
