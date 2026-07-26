"""Real integration tests for orchestrator-wired ledger state transitions (P0-3)."""
from __future__ import annotations

import json
import sqlite3
import hashlib
from pathlib import Path
from unittest.mock import patch
import pytest

from bet.pipeline.orchestrator import Orchestrator
from bet.pipeline.readiness_contracts import PipelineReadinessStatus
from bet.pipeline.agent_work_orders import build_agent_work_order, write_agent_work_order
from bet.pipeline.run_coordination import BoundedProcessResult

DAY = "2026-06-25"
RUN_ID = "run-ledger-test"


def _setup_env(tmp_path: Path):
    run_root = tmp_path / "pipeline_runs" / DAY / RUN_ID
    run_root.mkdir(parents=True, exist_ok=True)
    (run_root / "data").mkdir(parents=True, exist_ok=True)
    (run_root / "artifacts").mkdir(parents=True, exist_ok=True)
    (run_root / "logs").mkdir(parents=True, exist_ok=True)
    (run_root / "journal").mkdir(parents=True, exist_ok=True)

    # bootstrap DB
    db_file = run_root / "data" / "bet_dryrun_test.db"
    conn = sqlite3.connect(db_file)
    conn.execute("CREATE TABLE IF NOT EXISTS pipeline_state (betting_day TEXT PRIMARY KEY, current_step TEXT);")
    conn.execute("INSERT OR REPLACE INTO pipeline_state VALUES (?, 'S2');", (DAY,))
    conn.commit()
    conn.close()

    # S2 script evidence
    s2_ev = {
        "schema_version": 1,
        "artifact_type": "SCRIPT_EVIDENCE",
        "step_id": "S2",
        "status": "PASS",
        "betting_day": DAY,
        "run_id": RUN_ID,
        "payload": {},
    }
    (run_root / "artifacts" / "S2.json").write_text(json.dumps(s2_ev), encoding="utf-8")

    return run_root


def _write_agent_artifact(run_root: Path, step_id: str, status: str, payload: dict | None = None, command_request: dict | None = None):
    if payload is None:
        payload = {}

    # Add S2.3 required schema fields if PASS/COMMAND_REQUEST
    if step_id == "S2.3" and status in ("PASS", "COMMAND_REQUEST"):
        if "gaps" not in payload and "enrichment_gaps" not in payload:
            payload["gaps"] = []
        if "gaps_bounded" not in payload:
            payload["gaps_bounded"] = True

    # We must have work order sha
    wo_path = run_root / "artifacts" / f"{step_id}_work_order.json"
    wo_sha = ""
    if wo_path.exists():
        wo_sha = hashlib.sha256(wo_path.read_bytes()).hexdigest()

    art = {
        "schema_version": 1,
        "artifact_type": "AGENT_ARTIFACT",
        "step_id": step_id,
        "producer_agent_id": "bet-researcher",
        "status": status,
        "betting_day": DAY,
        "run_id": RUN_ID,
        "sport": "football",
        "point_in_time_as_of": "2026-06-25T12:00:00Z",
        "source_bound": True,
        "no_pick_edge_stake_coupon_emitted": True,
        "production_selectable": False,
        "betting_decisions_enabled": False,
        "sources": ["source"],
        "unknowns": [],
        "blocked_reasons": [] if status != "BLOCK" else ["Required data missing"],
        "evidence_refs": [],
        "work_order_id": f"WO-{RUN_ID}-{step_id}",
        "work_order_sha256": wo_sha,
        "payload": payload,
    }
    if command_request is not None:
        art["command_request"] = command_request

    art_path = run_root / "artifacts" / f"{step_id}.json"
    art_path.write_text(json.dumps(art), encoding="utf-8")
    return art_path


def test_transition_waiting_to_pass_or_block(tmp_path: Path, monkeypatch):
    """Verify integration flow: WAITING -> PASS and WAITING -> AGENT_ARTIFACT_BLOCK"""
    run_root = _setup_env(tmp_path)
    db_file = run_root / "data" / "bet_dryrun_test.db"

    monkeypatch.setenv("BET_DB_PATH", str(db_file))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_file}")

    # Case 1: WAITING
    orc = Orchestrator(
        betting_day=DAY,
        run_id=RUN_ID,
        runtime_mode="DRY_RUN",
        base_run_dir=tmp_path,
    )
    res = orc.run(start_step="S2.3", stop_after_step="S2.3")
    print("\nCASE 1 BLOCKERS:", res["blockers"])
    assert res["status"] == "BLOCK"

    ledger_data = json.loads((run_root / "resume_ledger.json").read_text(encoding="utf-8"))
    assert ledger_data["entries"][-1]["status"] == "WAITING_FOR_AGENT_ARTIFACT"

    # Case 2: WAITING -> PASS
    _write_agent_artifact(run_root, "S2.3", "PASS")

    orc2 = Orchestrator(
        betting_day=DAY,
        run_id=RUN_ID,
        runtime_mode="DRY_RUN",
        base_run_dir=tmp_path,
    )
    res2 = orc2.run(start_step="S2.3", stop_after_step="S2.3")
    print("\nCASE 2 BLOCKERS:", res2["blockers"])
    assert res2["status"] == "PASS"

    ledger_data2 = json.loads((run_root / "resume_ledger.json").read_text(encoding="utf-8"))
    assert ledger_data2["entries"][-1]["status"] == "PASS"


def test_transition_waiting_to_artifact_block(tmp_path: Path, monkeypatch):
    """Verify integration flow: WAITING -> AGENT_ARTIFACT_BLOCK"""
    run_root = _setup_env(tmp_path)
    db_file = run_root / "data" / "bet_dryrun_test.db"

    monkeypatch.setenv("BET_DB_PATH", str(db_file))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_file}")

    # Start with no S2.3 artifact
    orc = Orchestrator(
        betting_day=DAY,
        run_id=RUN_ID,
        runtime_mode="DRY_RUN",
        base_run_dir=tmp_path,
    )
    orc.run(start_step="S2.3", stop_after_step="S2.3")

    # Now write a BLOCK S2.3 artifact and run again
    _write_agent_artifact(run_root, "S2.3", "BLOCK")

    orc2 = Orchestrator(
        betting_day=DAY,
        run_id=RUN_ID,
        runtime_mode="DRY_RUN",
        base_run_dir=tmp_path,
    )
    res2 = orc2.run(start_step="S2.3", stop_after_step="S2.3")
    print("\nBLOCK-ART BLOCKERS:", res2["blockers"])
    assert res2["status"] == "BLOCK"

    ledger_data2 = json.loads((run_root / "resume_ledger.json").read_text(encoding="utf-8"))
    assert ledger_data2["entries"][-1]["status"] == "AGENT_ARTIFACT_BLOCK"


def test_transition_waiting_to_command_pending_to_pass(tmp_path: Path, monkeypatch):
    """Verify integration flow: WAITING -> COMMAND_REQUEST_PENDING -> PASS"""
    run_root = _setup_env(tmp_path)
    db_file = run_root / "data" / "bet_dryrun_test.db"

    monkeypatch.setenv("BET_DB_PATH", str(db_file))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_file}")

    # Start with no S2.3 artifact
    orc = Orchestrator(
        betting_day=DAY,
        run_id=RUN_ID,
        runtime_mode="DRY_RUN",
        base_run_dir=tmp_path,
    )
    orc.run(start_step="S2.3", stop_after_step="S2.3")

    # Write S2.3 with COMMAND_REQUEST
    cmd_req = {
        "command_id": "WAIT_FOR_RATE_LIMIT",
        "parameters": {"seconds": 1},
    }
    _write_agent_artifact(run_root, "S2.3", "COMMAND_REQUEST", command_request=cmd_req)

    # Patch run_bounded_process to return code 0 (success)
    mock_pass = BoundedProcessResult(returncode=0, timed_out=False, stdout="done", stderr="")
    with patch("bet.pipeline.orchestrator.run_bounded_process", return_value=mock_pass):
        orc2 = Orchestrator(
            betting_day=DAY,
            run_id=RUN_ID,
            runtime_mode="DRY_RUN",
            base_run_dir=tmp_path,
        )
        res2 = orc2.run(start_step="S2.3", stop_after_step="S2.3")
        print("\nCMD-PASS BLOCKERS:", res2["blockers"])
        assert res2["status"] == "PASS"

    ledger_data2 = json.loads((run_root / "resume_ledger.json").read_text(encoding="utf-8"))
    statuses = [e["status"] for e in ledger_data2["entries"]]
    assert "COMMAND_REQUEST_PENDING" in statuses
    assert statuses[-1] == "PASS"


def test_transition_waiting_to_command_pending_to_unresolved_to_corrected(tmp_path: Path, monkeypatch):
    """Verify integration flow: WAITING -> COMMAND_REQUEST_PENDING -> COMMAND_REQUEST_UNRESOLVED -> corrected PASS/BLOCK"""
    run_root = _setup_env(tmp_path)
    db_file = run_root / "data" / "bet_dryrun_test.db"

    monkeypatch.setenv("BET_DB_PATH", str(db_file))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_file}")

    # Start with no S2.3 artifact
    orc = Orchestrator(
        betting_day=DAY,
        run_id=RUN_ID,
        runtime_mode="DRY_RUN",
        base_run_dir=tmp_path,
    )
    orc.run(start_step="S2.3", stop_after_step="S2.3")

    # Write S2.3 with COMMAND_REQUEST
    cmd_req = {
        "command_id": "WAIT_FOR_RATE_LIMIT",
        "parameters": {"seconds": 1},
    }
    _write_agent_artifact(run_root, "S2.3", "COMMAND_REQUEST", command_request=cmd_req)

    # Patch run_bounded_process to return code 1 (failure)
    mock_fail = BoundedProcessResult(returncode=1, timed_out=False, stdout="fail", stderr="err")
    with patch("bet.pipeline.orchestrator.run_bounded_process", return_value=mock_fail):
        orc2 = Orchestrator(
            betting_day=DAY,
            run_id=RUN_ID,
            runtime_mode="DRY_RUN",
            base_run_dir=tmp_path,
        )
        res2 = orc2.run(start_step="S2.3", stop_after_step="S2.3")
        assert res2["status"] == "BLOCK"

    ledger_data2 = json.loads((run_root / "resume_ledger.json").read_text(encoding="utf-8"))
    statuses2 = [e["status"] for e in ledger_data2["entries"]]
    assert "COMMAND_REQUEST_PENDING" in statuses2
    assert statuses2[-1] == "COMMAND_REQUEST_UNRESOLVED"

    # Now verify UNRESOLVED -> corrected PASS transition!
    _write_agent_artifact(run_root, "S2.3", "PASS")
    orc3 = Orchestrator(
        betting_day=DAY,
        run_id=RUN_ID,
        runtime_mode="DRY_RUN",
        base_run_dir=tmp_path,
    )
    res3 = orc3.run(start_step="S2.3", stop_after_step="S2.3")
    assert res3["status"] == "PASS"

    ledger_data3 = json.loads((run_root / "resume_ledger.json").read_text(encoding="utf-8"))
    assert ledger_data3["entries"][-1]["status"] == "PASS"


def test_transition_unresolved_to_artifact_block(tmp_path: Path, monkeypatch):
    """Verify integration flow: UNRESOLVED -> AGENT_ARTIFACT_BLOCK"""
    run_root = _setup_env(tmp_path)
    db_file = run_root / "data" / "bet_dryrun_test.db"

    monkeypatch.setenv("BET_DB_PATH", str(db_file))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_file}")

    # Start with no S2.3 artifact
    orc = Orchestrator(
        betting_day=DAY,
        run_id=RUN_ID,
        runtime_mode="DRY_RUN",
        base_run_dir=tmp_path,
    )
    orc.run(start_step="S2.3", stop_after_step="S2.3")

    # Write S2.3 with COMMAND_REQUEST
    cmd_req = {
        "command_id": "WAIT_FOR_RATE_LIMIT",
        "parameters": {"seconds": 1},
    }
    _write_agent_artifact(run_root, "S2.3", "COMMAND_REQUEST", command_request=cmd_req)

    # Patch run_bounded_process to return code 1 (failure)
    mock_fail = BoundedProcessResult(returncode=1, timed_out=False, stdout="fail", stderr="err")
    with patch("bet.pipeline.orchestrator.run_bounded_process", return_value=mock_fail):
        orc2 = Orchestrator(
            betting_day=DAY,
            run_id=RUN_ID,
            runtime_mode="DRY_RUN",
            base_run_dir=tmp_path,
        )
        orc2.run(start_step="S2.3", stop_after_step="S2.3")

    # Now write a BLOCK artifact
    _write_agent_artifact(run_root, "S2.3", "BLOCK")

    orc3 = Orchestrator(
        betting_day=DAY,
        run_id=RUN_ID,
        runtime_mode="DRY_RUN",
        base_run_dir=tmp_path,
    )
    res3 = orc3.run(start_step="S2.3", stop_after_step="S2.3")
    assert res3["status"] == "BLOCK"

    ledger_data3 = json.loads((run_root / "resume_ledger.json").read_text(encoding="utf-8"))
    assert ledger_data3["entries"][-1]["status"] == "AGENT_ARTIFACT_BLOCK"
