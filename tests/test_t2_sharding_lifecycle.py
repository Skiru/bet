"""Checkpoint T2 tests: legal full-agentic sharding state machine and resumption."""
from __future__ import annotations

import hashlib
from pathlib import Path
import pytest

from bet.pipeline.sharding.models import WorkOrderBudgetV1, ChunkArtifactV1, ChunkWorkOrderV1
from bet.pipeline.sharding.lifecycle import (
    create_chunk_execution_plan,
    aggregate_chunks,
    get_aggregator_source_sha256,
    ChunkLifecycleError,
)


def test_t2_chunk_work_order_bindings():
    """Verify chunk work orders bind all required SHA256 and plan metadata."""
    event_ids = [f"EVT_{i:03d}" for i in range(1, 31)]
    plan = create_chunk_execution_plan(
        parent_work_order_id="WO_T2_TEST",
        parent_work_order_sha256="1" * 64,
        step_id="S2.3",
        betting_day="2026-07-27",
        run_id="RUN_T2_001",
        runtime_mode="DRY_RUN",
        source_head="910ebc820b413802a83bd95b1eba8a1e76df5657",
        source_tree="cb594728aac7819406e582ac6c3ef9840eab9f9a",
        manifest_sha256="2" * 64,
        event_ids=event_ids,
        agent_name="bet-researcher",
        allowed_tools=("bet_sqlite_query",),
        budget=WorkOrderBudgetV1(max_events_per_chunk=15),
    )

    assert len(plan.chunks) == 2
    c1 = plan.chunks[0]
    assert c1.parent_work_order_id == "WO_T2_TEST"
    assert c1.parent_work_order_sha256 == "1" * 64
    assert c1.parent_plan_sha256 == plan.plan_sha256
    assert c1.source_head == "910ebc820b413802a83bd95b1eba8a1e76df5657"
    assert c1.agent_name == "bet-researcher"


def test_t2_aggregator_source_sha256():
    """Verify aggregation receipt uses actual source file SHA256, not a label string."""
    lifecycle_file = Path(__file__).resolve().parents[1] / "src" / "bet" / "pipeline" / "sharding" / "lifecycle.py"
    expected_file_sha = hashlib.sha256(lifecycle_file.read_bytes()).hexdigest()
    actual_sha = get_aggregator_source_sha256()

    assert actual_sha == expected_file_sha
    assert actual_sha != hashlib.sha256(b"DETERMINISTIC_CHUNK_AGGREGATOR_V1").hexdigest()


def test_t2_aggregation_enforces_exact_event_union():
    """Verify aggregation fails if event set does not match parent universe exactly."""
    event_ids = ["EVT_001", "EVT_002", "EVT_003"]
    plan = create_chunk_execution_plan(
        parent_work_order_id="WO_UNION",
        step_id="S2.3",
        betting_day="2026-07-27",
        run_id="RUN_UNION",
        event_ids=event_ids,
        agent_name="bet-researcher",
        budget=WorkOrderBudgetV1(max_events_per_chunk=10),
    )

    c1 = plan.chunks[0]
    # Artifact missing EVT_003
    art_incomplete = ChunkArtifactV1(
        chunk_id=c1.chunk_id,
        parent_work_order_id=c1.parent_work_order_id,
        parent_plan_sha256=c1.parent_plan_sha256,
        chunk_index=c1.chunk_index,
        status="PASS",
        producer_agent_id="bet-researcher",
        processed_event_ids=("EVT_001", "EVT_002"),
        event_records=[
            {"canonical_event_id": "EVT_001", "terminal_status": "PASS"},
            {"canonical_event_id": "EVT_002", "terminal_status": "PASS"},
        ],
    )

    with pytest.raises(ChunkLifecycleError):
        aggregate_chunks(plan, [art_incomplete])
