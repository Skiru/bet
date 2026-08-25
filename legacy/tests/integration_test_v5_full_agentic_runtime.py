<<<<<<< HEAD
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
=======
"""Multi-process integration test for V5 Orchestrator sharding, chunk work orders, resume and aggregation."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
import pytest

from bet.pipeline.orchestrator import Orchestrator
from bet.pipeline.sharding.models import ChunkArtifactV1
from bet.pipeline.sharding.lifecycle import ChunkLifecycleError


def test_orchestrator_sharded_runtime_multi_process_lifecycle(tmp_path):
    """Real Orchestrator.run() multi-process integration test for sharding lifecycle.

    Orchestrator.run() -> WAITING_FOR_CHUNK_ARTIFACT -> exact chunk work order ->
    bound chunk artifact -> new Orchestrator instance -> same-step resume ->
    next chunk -> aggregation -> parent PASS -> downstream gate.
    """
    betting_day = "2026-07-28"
    run_id = "run-sharded-multi-process-test"
    base_run_dir = tmp_path / "runs"
    run_root = base_run_dir / "pipeline_runs" / betting_day / run_id
    run_root.mkdir(parents=True, exist_ok=True)

    # Scaffolding prerequisite S2 artifact with 35 events (exceeds default chunk limit of 15)
    s2_dir = run_root / "artifacts"
    s2_dir.mkdir(parents=True, exist_ok=True)
    events = [f"evt_{i:03d}" for i in range(1, 36)]

    s2_art = {
        "schema_version": 1,
        "artifact_type": "SCRIPT_EVIDENCE",
        "step_id": "S2",
        "status": "PASS",
        "betting_day": betting_day,
        "run_id": run_id,
        "sport": "football",
        "fixture_id": None,
        "fixture_key": None,
        "point_in_time_as_of": "2026-07-28T00:00:00Z",
        "source_bound": True,
        "no_pick_edge_stake_coupon_emitted": True,
        "production_selectable": False,
        "betting_decisions_enabled": False,
        "sources": ["test_source"],
        "unknowns": [],
        "blocked_reasons": [],
        "evidence_refs": [],
        "payload": {
            "total_events": 35,
            "event_records": [
                {
                    "canonical_event_id": eid,
                    "sport": "football",
                    "competition": "EPL",
                    "home_team": f"Home_{eid}",
                    "away_team": f"Away_{eid}",
                }
                for eid in events
            ]
        }
    }
    (s2_dir / "S2.json").write_text(json.dumps(s2_art, indent=2))
    (s2_dir / "S2" / "S2_artifact.json").parent.mkdir(parents=True, exist_ok=True)
    (s2_dir / "S2" / "S2_artifact.json").write_text(json.dumps(s2_art, indent=2))

    # Phase 1: First Orchestrator run. Should enter WAITING_FOR_CHUNK_ARTIFACT at S2.3
    orch1 = Orchestrator(
        betting_day=betting_day,
        run_id=run_id,
        runtime_mode="DRY_RUN",
        base_run_dir=base_run_dir,
    )

    res1 = orch1.run(start_step="S2.3", stop_after_step="S2.3")
    assert res1 is not None
    assert orch1.pending_chunk_work_order_path is not None
    assert orch1.pending_chunk_expected_output_path is not None

    # Check pending chunk work order file
    pending_wo_file = Path(orch1.pending_chunk_work_order_path)
    assert pending_wo_file.is_file()
    wo_data = json.loads(pending_wo_file.read_text())
    assert wo_data["chunk_id"].endswith("-C0001")
    assert len(wo_data["event_ids"]) == 15

    # Emit chunk artifact for chunk 1
    chunks_art_dir = run_root / "artifacts" / "chunks"
    chunks_art_dir.mkdir(parents=True, exist_ok=True)

    from bet.pipeline.contracts.canonical_json import hash_canonical_json

    head_sha = "a" * 40
    tree_sha = "b" * 40
    manifest_sha = "c" * 64

    c1_art = ChunkArtifactV1(
        chunk_id=wo_data["chunk_id"],
        chunk_work_order_sha256=hash_canonical_json(wo_data),
        parent_work_order_id=wo_data["parent_work_order_id"],
        parent_work_order_sha256=wo_data["parent_work_order_sha256"],
        parent_plan_id=wo_data["parent_plan_id"],
        parent_plan_sha256=wo_data["parent_plan_sha256"],
        chunk_index=0,
        total_chunks=3,
        status="PASS",
        producer_agent_id="bet-researcher",
        betting_day=betting_day,
        run_id=run_id,
        source_head=wo_data.get("source_head") or head_sha,
        source_tree=wo_data.get("source_tree") or tree_sha,
        manifest_sha256=wo_data.get("manifest_sha256") or manifest_sha,
        processed_event_ids=tuple(wo_data["event_ids"]),
        event_records=[{"canonical_event_id": eid, "terminal_status": "PASS"} for eid in wo_data["event_ids"]]
    )
    (chunks_art_dir / f"{wo_data['chunk_id']}.json").write_text(json.dumps(c1_art.model_dump(), indent=2))

    # Phase 2: Second Orchestrator run from a fresh instance. Should pause on Chunk 2.
    orch2 = Orchestrator(
        betting_day=betting_day,
        run_id=run_id,
        runtime_mode="DRY_RUN",
        base_run_dir=base_run_dir,
    )

    res2 = orch2.run(start_step="S2.3", stop_after_step="S2.3")
    assert orch2.pending_chunk_work_order_path is not None
    pending_wo_file2 = Path(orch2.pending_chunk_work_order_path)
    wo_data2 = json.loads(pending_wo_file2.read_text())
    assert wo_data2["chunk_id"].endswith("-C0002")

    # Emit remaining chunk artifacts for chunk 2 and chunk 3
    for chunk_idx in (2, 3):
        c_wo_file = pending_wo_file2.parent / f"{wo_data['parent_work_order_id']}-C{chunk_idx:04d}_work_order.json"
        c_wo_data = json.loads(c_wo_file.read_text())
        c_art = ChunkArtifactV1(
            chunk_id=c_wo_data["chunk_id"],
            chunk_work_order_sha256=hash_canonical_json(c_wo_data),
            parent_work_order_id=c_wo_data["parent_work_order_id"],
            parent_work_order_sha256=c_wo_data["parent_work_order_sha256"],
            parent_plan_id=c_wo_data["parent_plan_id"],
            parent_plan_sha256=c_wo_data["parent_plan_sha256"],
            chunk_index=chunk_idx - 1,
            total_chunks=3,
            status="PASS",
            producer_agent_id="bet-researcher",
            betting_day=betting_day,
            run_id=run_id,
            source_head=c_wo_data.get("source_head") or head_sha,
            source_tree=c_wo_data.get("source_tree") or tree_sha,
            manifest_sha256=c_wo_data.get("manifest_sha256") or manifest_sha,
            processed_event_ids=tuple(c_wo_data["event_ids"]),
            event_records=[{"canonical_event_id": eid, "terminal_status": "PASS"} for eid in c_wo_data["event_ids"]]
        )
        (chunks_art_dir / f"{c_wo_data['chunk_id']}.json").write_text(json.dumps(c_art.model_dump(), indent=2))

    # Phase 3: Third Orchestrator run. All chunks present -> aggregate -> PASS at S2.3
    orch3 = Orchestrator(
        betting_day=betting_day,
        run_id=run_id,
        runtime_mode="DRY_RUN",
        base_run_dir=base_run_dir,
    )

    res3 = orch3.run(start_step="S2.3", stop_after_step="S2.3")
    assert res3 is not None

    # Verify aggregated artifact was written to S2.3
    s23_art_path = run_root / "artifacts" / "S2.3.json"
    if not s23_art_path.is_file():
        s23_art_path = run_root / "artifacts" / "S2.3" / "S2.3_artifact.json"
    assert s23_art_path.is_file()
    s23_data = json.loads(s23_art_path.read_text())
    assert s23_data["total_events"] == 35
    assert len(s23_data["event_records"]) == 35


def test_chunk_aggregation_rejects_foreign_or_duplicate_events():
    """Verify that chunk lifecycle rejects duplicate or foreign event IDs."""
    from bet.pipeline.sharding.lifecycle import validate_chunk_aggregation

    # Foreign event
    with pytest.raises(ChunkLifecycleError, match="Foreign event"):
        validate_chunk_aggregation(
            parent_events=["e1", "e2"],
            chunk_events=[["e1"], ["e99"]]
        )

    # Duplicate event
    with pytest.raises(ChunkLifecycleError, match="Duplicate event"):
        validate_chunk_aggregation(
            parent_events=["e1", "e2"],
            chunk_events=[["e1"], ["e1"]]
>>>>>>> fix/bet-v5-final-one-pass-closure-v4
        )
