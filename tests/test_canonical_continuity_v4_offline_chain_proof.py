from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
import pytest

from bet.pipeline.orchestrator import Orchestrator
from bet.pipeline.artifact_gate import PipelineReadinessStatus
from bet.pipeline.event_accounting import canonical_event_id
from bet.pipeline.artifact_io import publish_run_artifact
from bet.pipeline.agent_work_orders import build_agent_work_order, write_agent_work_order

DAY = "2026-07-15"
RUN_ID = "run-v4-integration-proof"

def _bootstrap_test_db(db_path: Path) -> Path:
    repo_root = Path(__file__).resolve().parents[1]
    schema_path = repo_root / "src" / "bet" / "db" / "schema.sql"
    schema = schema_path.read_text(encoding="utf-8")
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(schema)
    conn.close()
    return db_path

def test_v4_offline_chain_proof(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("BET_PIPELINE_OFFLINE_TEST_MODE", "1")

    run_root = tmp_path / "pipeline_runs" / DAY / RUN_ID
    run_root.mkdir(parents=True, exist_ok=True)
    
    # 1. Setup DB
    db_file = run_root / "data" / "bet_dryrun_test.db"
    db_file.parent.mkdir(parents=True, exist_ok=True)
    _bootstrap_test_db(db_file)
    monkeypatch.setenv("BET_DB_PATH", str(db_file))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_file}")

    # Set run-root and directories
    monkeypatch.setenv("BET_PIPELINE_RUN_ROOT", str(run_root))
    monkeypatch.setenv("BET_PIPELINE_DATA_DIR", str(run_root / "data"))
    monkeypatch.setenv("BET_PIPELINE_ARTIFACT_DIR", str(run_root / "artifacts"))
    monkeypatch.setenv("BET_PIPELINE_COUPON_DIR", str(run_root / "coupons"))

    # Create directories
    (run_root / "data").mkdir(parents=True, exist_ok=True)
    (run_root / "artifacts").mkdir(parents=True, exist_ok=True)
    (run_root / "coupons").mkdir(parents=True, exist_ok=True)

    # 2. Seed S1 discover shortlist & evidence to initiate flow
    matrix_path = run_root / "data" / "market_matrix.json"
    event_data = [
        {
            "fixture_id": "football-unicode",
            "sport": "football",
            "competition": "Integration League",
            "home_team": "ŁKS Łódź",
            "away_team": "KS D",
            "kickoff": "2026-07-15T12:00:00Z",
        }
    ]
    matrix_path.write_text(json.dumps({"events": event_data}), encoding="utf-8")

    # Seed S2 shortlist as well!
    s2_shortlist_path = run_root / "data" / f"{DAY}_s2_shortlist.json"
    s2_shortlist_path.write_text(json.dumps({"total_candidates": len(event_data), "candidates": event_data}), encoding="utf-8")
    
    s1_ev_path = run_root / "artifacts" / "S1.json"
    s1_ev = {
        "schema_version": 1,
        "artifact_type": "SCRIPT_EVIDENCE",
        "step_id": "S1",
        "status": "PASS",
        "betting_day": DAY,
        "run_id": RUN_ID,
        "payload": {"market_matrix_path": str(matrix_path)},
    }
    s1_ev_path.write_text(json.dumps(s1_ev), encoding="utf-8")

    # Bypass tipster aggregator and run tipster_xref directly
    import scripts.pipeline_steps.s2_tipsters as s2_tipsters
    monkeypatch.setattr(s2_tipsters, "SCRIPTS", ["tipster_xref.py"])

    # Initialize the Orchestrator starting at S1e
    orchestrator = Orchestrator(
        betting_day=DAY,
        run_id=RUN_ID,
        runtime_mode="DRY_RUN",
        base_run_dir=tmp_path,
    )

    # Execute step-by-step
    steps = ["S1e", "S2", "S2.3", "S2.5", "S2.7", "S2.9", "S3", "S4", "S5", "S6", "S7", "S7b", "S8"]
    
    current_idx = 0
    while current_idx < len(steps):
        step_id = steps[current_idx]
        
        # If the step is an agent_artifact step, proactively generate work order and PASS artifact dynamically on-the-fly!
        if step_id in ("S2.3", "S2.5", "S2.7", "S2.9", "S5"):
            # Build and write work order
            wo = build_agent_work_order(
                betting_day=DAY,
                run_id=RUN_ID,
                step_id=step_id,
                runtime_mode="DRY_RUN",
                base_dir=tmp_path,
            )
            write_agent_work_order(wo, tmp_path)
            
            # Load written work order data
            wo_path = run_root / "artifacts" / f"{step_id}_work_order.json"
            assert wo_path.exists(), f"Work order {step_id} missing!"
            wo_data = json.loads(wo_path.read_text(encoding="utf-8"))
            
            # Read input refs and calculate predecessor hashes to bind them dynamically
            input_refs = wo_data.get("input_refs", [])
            for ref in input_refs:
                p = Path(ref["path"])
                assert p.exists(), f"Input path {p} does not exist!"
                ref["sha256"] = hashlib.sha256(p.read_bytes()).hexdigest()
            
            # Compute SHA-256 of work order file
            wo_sha = hashlib.sha256(wo_path.read_bytes()).hexdigest()
            evt_id = canonical_event_id(event_data[0])
            
            payload = {
                "event_records": [
                    {
                        "canonical_event_id": evt_id,
                        "terminal_status": "DEGRADED_CONTINUE",
                        "reason_codes": ["DEGRADED_NO_TIPSTER_PICKS"],
                        "candidate_ids": []
                    }
                ]
            }
            evidence_refs = ["mock_ref"]
            if step_id == "S2.3":
                payload["enrichment_gaps"] = []
                payload["gaps_status"] = "none"
            elif step_id == "S2.5":
                payload["providers"] = ["source"]
            elif step_id == "S2.7":
                payload["disputed_facts"] = []
                payload["reconciliation"] = {"unknown_facts": [], "decision_basis": "basis"}
                evidence_refs = ["S2.5_ref"]
            elif step_id == "S2.9":
                payload["readiness"] = "PASS"
                payload["s3_may_proceed"] = True
                payload["predecessor_bindings"] = []
                for ref in input_refs:
                    ref_step_id = ref["step_id"]
                    if ref_step_id in ("S2.3", "S2.5", "S2.7"):
                        payload["predecessor_bindings"].append({
                            "step_id": ref_step_id,
                            "path": ref["path"],
                            "sha256": ref["sha256"],
                            "artifact_type": "AGENT_ARTIFACT",
                            "betting_day": DAY,
                            "run_id": RUN_ID,
                            "status": "PASS"
                        })
                evidence_refs = ["S2.3_ref", "S2.5_ref", "S2.7_ref"]
            elif step_id == "S5":
                payload["injuries_context_available"] = True
                payload["motivation_level"] = "HIGH"
                payload["morale_reconciled"] = "GOOD"
                payload["morale_and_recent_results_context"] = {}
                payload["volatility_risk_checked"] = True
                payload["weather_conditions"] = {"forecast": "CLEAR"}
                payload["travel_fatigue_checked"] = True
                payload["morale_context_checked"] = True
                payload["tipster_sentiment"] = {}
                payload["bet_builder_precheck"] = {}
                payload["tournament_context"] = {}
                evidence_refs = ["S4_ref"]

            artifact = {
                "schema_version": 1 if step_id != "S2.9" else 2,
                "artifact_type": "AGENT_ARTIFACT",
                "step_id": step_id,
                "status": "PASS",
                "betting_day": DAY,
                "run_id": RUN_ID,
                "sport": "football",
                "point_in_time_as_of": "2026-07-15T12:00:00Z",
                "source_bound": True,
                "no_pick_edge_stake_coupon_emitted": True,
                "production_selectable": False,
                "betting_decisions_enabled": False,
                "sources": ["source"],
                "unknowns": [],
                "blocked_reasons": [],
                "evidence_refs": evidence_refs,
                "work_order_id": wo_data["work_order_id"],
                "work_order_sha256": wo_sha,
                "payload": payload,
            }
            
            # Publish agent artifact using official publish_run_artifact interface!
            publish_run_artifact(
                run_root=run_root,
                target=run_root / "artifacts" / f"{step_id}.json",
                payload=artifact,
                betting_day=DAY,
                run_id=RUN_ID,
                artifact_type="AGENT_ARTIFACT",
                immutable=True,
            )
        
        # Run orchestrator for the single step
        res = orchestrator.run(start_step=step_id, stop_after_step=step_id)
        assert (res.get("overall_status") or res.get("status")) == PipelineReadinessStatus.PASS, f"Step {step_id} failed: {orchestrator.blockers}"
        current_idx += 1

    # Verify S8 completed successfully and produced manual quote review only
    s8_ev_file = run_root / "artifacts" / "S8.json"
    assert s8_ev_file.exists()
    s8_ev = json.loads(s8_ev_file.read_text(encoding="utf-8"))
    assert s8_ev["status"] == "PASS"
    
    quote_pack_path = Path(s8_ev["payload"]["s8_quote_pack_path"])
    assert quote_pack_path.exists()
    quote_pack = json.loads(quote_pack_path.read_text(encoding="utf-8"))
    
    # Assert manual quote review and operator SUPERBET only or legal NO_ACTION_TERMINAL
    assert quote_pack["status"] in ("READY_FOR_MANUAL_SUPERBET_QUOTE_REVIEW", "NO_ACTION_TERMINAL")
    for card in quote_pack.get("quote_cards", []):
        assert card["manual_operator"] == "SUPERBET"
        assert card["executable_coupon"] is False
        assert card["betting_valid"] is False
        assert card["can_place_bet_now"] is False

    # Prove S9 (human-only gate) is never executed or synthesized
    s9_ev_file = run_root / "artifacts" / "S9.json"
    assert not s9_ev_file.exists()
