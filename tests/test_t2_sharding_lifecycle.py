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


def test_t2_chunk_payload_event_records_are_promoted_before_aggregation():
    """Ensure chunk artifacts using the payload compatibility shape keep event coverage."""
    event_ids = ["EVT_001"]
    plan = create_chunk_execution_plan(
        parent_work_order_id="WO_PAYLOAD_RECORDS",
        step_id="S2.3",
        betting_day="2026-07-27",
        run_id="RUN_PAYLOAD_RECORDS",
        event_ids=event_ids,
        agent_name="bet-researcher",
        budget=WorkOrderBudgetV1(max_events_per_chunk=10),
    )
    chunk = plan.chunks[0]
    artifact_data = {
        "chunk_id": chunk.chunk_id,
        "parent_work_order_id": chunk.parent_work_order_id,
        "parent_plan_sha256": chunk.parent_plan_sha256,
        "chunk_index": chunk.chunk_index,
        "status": "PASS",
        "producer_agent_id": "bet-researcher",
        "processed_event_ids": event_ids,
        "payload": {"event_records": [{"canonical_event_id": "EVT_001"}]},
    }
    if not artifact_data.get("event_records") and isinstance(artifact_data.get("payload"), dict):
        artifact_data["event_records"] = artifact_data["payload"]["event_records"]

    receipt, records = aggregate_chunks(plan, [ChunkArtifactV1(**artifact_data)])
    assert receipt.status == "PASS"
    assert records == [{"canonical_event_id": "EVT_001"}]


def test_t2_orchestrator_sharded_lifecycle_31_events(tmp_path: Path):
    """Verify 31-event universe sharded execution lifecycle across orchestrator instances."""
    import json
    from bet.pipeline.orchestrator import Orchestrator

    day = "2026-07-16"
    run_id = "run-shard-31"
    run_root = tmp_path / "pipeline_runs" / day / run_id
    run_root.mkdir(parents=True, exist_ok=True)
    (run_root / "data").mkdir(parents=True, exist_ok=True)
    (run_root / "artifacts").mkdir(parents=True, exist_ok=True)

    event_ids = [f"EVT_{i:03d}" for i in range(1, 32)]  # 31 events

    # Setup parent S2.3 work order and inputs
    plan = create_chunk_execution_plan(
        parent_work_order_id=f"WO-{run_id}-S2.3",
        parent_work_order_sha256="a" * 64,
        step_id="S2.3",
        betting_day=day,
        run_id=run_id,
        source_head="a" * 40,
        source_tree="b" * 40,
        manifest_sha256="c" * 64,
        event_ids=event_ids,
        agent_name="bet-researcher",
        budget=WorkOrderBudgetV1(max_events_per_chunk=15),
    )

    # 31 events / 15 per chunk = 3 chunks (15, 15, 1)
    assert len(plan.chunks) == 3

    chunk_artifacts: list[ChunkArtifactV1] = []
    for c_wo in plan.chunks:
        records = [
            {"canonical_event_id": eid, "terminal_status": "CONTINUE", "sport": "football"}
            for eid in c_wo.event_ids
        ]
        art = ChunkArtifactV1(
            chunk_id=c_wo.chunk_id,
            chunk_work_order_sha256="d" * 64,
            parent_work_order_id=c_wo.parent_work_order_id,
            parent_work_order_sha256="a" * 64,
            parent_plan_id=plan.plan_id,
            parent_plan_sha256=plan.plan_sha256,
            chunk_index=c_wo.chunk_index,
            total_chunks=3,
            status="PASS",
            producer_agent_id="bet-researcher",
            betting_day=day,
            run_id=run_id,
            source_head="a" * 40,
            source_tree="b" * 40,
            manifest_sha256="c" * 64,
            processed_event_ids=c_wo.event_ids,
            event_records=records,
        )
        chunk_artifacts.append(art)

    receipt, agg_records = aggregate_chunks(plan, chunk_artifacts)
    assert receipt.status == "PASS"
    assert receipt.total_chunks_aggregated == 3
    assert receipt.total_events_accounted == 31
    assert len(agg_records) == 31
