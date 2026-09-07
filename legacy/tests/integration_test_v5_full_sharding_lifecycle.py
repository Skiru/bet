"""Mandatory canonical sharding integration test executing two Orchestrator instances across 31+ events."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
import pytest

from bet.pipeline.orchestrator import Orchestrator
from bet.pipeline.sharding.models import ChunkArtifactV1, ChunkWorkOrderV1
from bet.pipeline.sharding.lifecycle import WAITING_FOR_CHUNK_ARTIFACT
from bet.pipeline.contracts.canonical_json import hash_canonical_json


def test_full_sharding_lifecycle_multi_process_resume(tmp_path):
    """Test 35 events sharded across 3 chunks executed and resumed across two Orchestrator instances."""
    base_reports_dir = tmp_path / "reports"
    run_root = base_reports_dir / "pipeline_runs" / "2026-07-28" / "run_shard_test"
    art_dir = run_root / "artifacts"
    data_dir = run_root / "data"
    art_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)

    # 1. Create S2 canonical event universe with 35 events
    events = []
    for i in range(1, 36):
        events.append({
            "canonical_event_id": f"evt_{i:03d}",
            "sport": "football",
            "competition": "EPL",
            "home_team": f"HomeTeam_{i}",
            "away_team": f"AwayTeam_{i}",
            "scheduled_start_utc": "2026-07-28T18:00:00Z",
        })

    s2_artifact = {
        "schema_version": 1,
        "artifact_type": "SCRIPT_EVIDENCE",
        "step_id": "S2",
        "status": "PASS",
        "betting_day": "2026-07-28",
        "run_id": "run_shard_test",
        "event_records": events,
        "total_events": 35,
        "no_pick_edge_stake_coupon_emitted": True,
        "production_selectable": False,
        "betting_decisions_enabled": False,
        "sources": ["s2_tipsters"],
        "unknowns": [],
        "blocked_reasons": [],
        "evidence_refs": [],
        "payload": {"event_records": events},
    }

    s2_path = art_dir / "S2.json"
    s2_path.write_text(json.dumps(s2_artifact, indent=2), encoding="utf-8")

    manifest_path = Path(__file__).resolve().parents[2] / "config" / "pipeline_manifest.json"

    # 2. Process 1: Initialize Orchestrator and run S2.3
    orch1 = Orchestrator(
        betting_day="2026-07-28",
        run_id="run_shard_test",
        runtime_mode="DRY_RUN",
        manifest_path=manifest_path,
        base_run_dir=base_reports_dir,
    )

    res1 = orch1.run(start_step="S2.3", stop_after_step="S2.3")
    assert res1["status"] == "BLOCK"
    assert orch1.pending_chunk_work_order_path is not None
    assert Path(orch1.pending_chunk_work_order_path).exists()

    # Verify ledger recorded WAITING_FOR_CHUNK_ARTIFACT
    ledger_path = run_root / "resume_ledger.json"
    assert ledger_path.exists()
    ledger_data = json.loads(ledger_path.read_text(encoding="utf-8"))
    entries = ledger_data.get("entries", [])
    assert any(e.get("status") == WAITING_FOR_CHUNK_ARTIFACT for e in entries) or ledger_data.get("status") == WAITING_FOR_CHUNK_ARTIFACT

    # 3. Process 2 simulation: Generate chunk artifacts for all chunks
    plan_file = run_root / "work_orders" / "chunks" / "PLAN_WO-run_shard_test-S2.3.json"
    assert plan_file.exists()
    plan_data = json.loads(plan_file.read_text(encoding="utf-8"))

    chunks_dir = art_dir / "chunks"
    chunks_dir.mkdir(parents=True, exist_ok=True)

    head_sha = "a" * 40
    tree_sha = "b" * 40
    manifest_sha = "c" * 64

    for chunk_wo_data in plan_data["chunks"]:
        c_wo = ChunkWorkOrderV1(**chunk_wo_data)
        wo_sha = hash_canonical_json(chunk_wo_data)

        chunk_art_data = {
            "chunk_id": c_wo.chunk_id,
            "chunk_work_order_sha256": wo_sha,
            "parent_work_order_id": c_wo.parent_work_order_id,
            "parent_work_order_sha256": c_wo.parent_work_order_sha256,
            "parent_plan_id": c_wo.parent_plan_id,
            "parent_plan_sha256": c_wo.parent_plan_sha256,
            "chunk_index": c_wo.chunk_index,
            "total_chunks": c_wo.total_chunks,
            "status": "PASS",
            "producer_agent_id": "bet-researcher",
            "betting_day": "2026-07-28",
            "run_id": "run_shard_test",
            "source_head": c_wo.source_head or head_sha,
            "source_tree": c_wo.source_tree or tree_sha,
            "manifest_sha256": c_wo.manifest_sha256 or manifest_sha,
            "processed_event_ids": c_wo.event_ids,
            "event_records": [
                {"canonical_event_id": eid, "step_status": "PROCESSED", "gaps": []}
                for eid in c_wo.event_ids
            ],
            "payload": {"gaps": []},
            "receipts": [],
        }

        art_obj = ChunkArtifactV1(**chunk_art_data)
        art_file = chunks_dir / f"{c_wo.chunk_id}.json"
        art_file.write_text(json.dumps(art_obj.model_dump(), indent=2), encoding="utf-8")

    # 4. Process 2: Instantiate second Orchestrator and resume S2.3
    orch2 = Orchestrator(
        betting_day="2026-07-28",
        run_id="run_shard_test",
        runtime_mode="DRY_RUN",
        manifest_path=manifest_path,
        base_run_dir=base_reports_dir,
    )

    res2 = orch2.run(start_step="S2.3", stop_after_step="S2.3")
    assert res2["status"] == "PASS"

    # Verify aggregated artifact was written to disk
    s23_artifact_path = art_dir / "S2.3.json"
    assert s23_artifact_path.exists()
    s23_data = json.loads(s23_artifact_path.read_text(encoding="utf-8"))
    assert s23_data["total_events"] == 35
    assert len(s23_data["event_records"]) == 35
    assert s23_data["aggregation_receipt"]["status"] == "PASS"
