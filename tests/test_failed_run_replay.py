"""Deterministic failed-run replay and pipeline integration certification tests."""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bet.pipeline.manifest import load_pipeline_manifest
from bet.pipeline.integration_artifacts import resolve_manifest_step_output
from bet.pipeline.portfolio_repeat_guard import (
    PortfolioRepeatGuardInput,
    evaluate_portfolio_repeat_guard,
)

FAILED_RUN_ROOT = Path("/Users/mkoziol/projects/bet-final-recompose/reports/pipeline_runs/2026-07-14/BET_FULL_SESSION_2026_07_14_PRODUCTION_RUN")


@pytest.fixture
def run_sandbox(tmp_path) -> Path:
    """Setup a sandboxed run environment imitating the failed run structure."""
    sandbox = tmp_path / "sandbox"
    artifacts_dir = sandbox / "artifacts"
    data_dir = sandbox / "data"
    logs_dir = sandbox / "logs"
    
    for d in (artifacts_dir, data_dir, logs_dir):
        d.mkdir(parents=True, exist_ok=True)
        
    return sandbox


def test_pure_portfolio_repeat_guard_logic():
    """Verify that portfolio/repeat guard is a side-effect-free, deterministic pure function."""
    candidates = [
        {
            "candidate_id": "football|A|B|2026-07-14",
            "home_team": "Team A",
            "away_team": "Team B",
            "market_type": "Over 2.5",
            "sport": "football",
            "competition": "Liga 1",
            "best_market": {"name": "Over 2.5"}
        },
        {
            "candidate_id": "football|C|D|2026-07-14",
            "home_team": "Team C",
            "away_team": "Team D",
            "market_type": "Spain Liga",
            "sport": "football",
            "competition": "La Liga"
        }
    ]
    history = [
        {
            "event": "Team A vs Team B",
            "market": "Over 2.5",
            "status": "loss",
            "betting_day": "2026-07-13",
            "pick_id": "P-123"
        }
    ]
    
    guard_input = PortfolioRepeatGuardInput(
        candidates=candidates,
        history_snapshot=history,
        betting_day="2026-07-14",
        run_id="REPLAY_RUN",
        source_s5_hash="dummy_s5_hash"
    )
    
    res = evaluate_portfolio_repeat_guard(guard_input)
    assert len(res.repeat_rejected) == 1
    assert res.repeat_rejected[0]["candidate_id"] == "football|A|B|2026-07-14"
    assert len(res.accepted) == 1
    assert res.accepted[0]["candidate_id"] == "football|C|D|2026-07-14"
    assert res.accounting["unaccounted_candidate_ids"] == []


def test_failed_run_replay_reconstruction(run_sandbox):
    """Execute deterministic failed-run replay using real wrappers."""
    # 1. Mock manifest
    manifest_path = ROOT / "config" / "pipeline_manifest.json"
    manifest = load_pipeline_manifest(manifest_path)
    
    # Copy S4.json and data candidates from failed run into sandbox
    failed_s4_artifact_path = FAILED_RUN_ROOT / "artifacts" / "S4.json"
    failed_s4_data_path = FAILED_RUN_ROOT / "data" / "2026-07-14_s4_valuation_candidates.json"
    
    if failed_s4_artifact_path.exists() and failed_s4_data_path.exists():
        shutil.copy(failed_s4_artifact_path, run_sandbox / "artifacts" / "S4.json")
        shutil.copy(failed_s4_data_path, run_sandbox / "data" / "2026-07-14_s4_valuation_candidates.json")
        
        # Rewrite paths in S4 evidence payload to point to sandbox
        s4_evidence = json.loads((run_sandbox / "artifacts" / "S4.json").read_text())
        s4_evidence["payload"]["s4_valuation_output_path"] = str(run_sandbox / "data" / "2026-07-14_s4_valuation_candidates.json")
        s4_evidence["run_id"] = "REPLAY_RUN_ID"
        (run_sandbox / "artifacts" / "S4.json").write_text(json.dumps(s4_evidence, indent=2))
        
        # 2. Write simulated S5 Agent Artifact PASS envelope
        s5_artifact = {
            "schema_version": 1,
            "artifact_type": "AGENT_ARTIFACT",
            "step_id": "S5",
            "status": "PASS",
            "betting_day": "2026-07-14",
            "run_id": "REPLAY_RUN_ID",
            "point_in_time_as_of": "2026-07-14T12:00:00Z",
            "source_bound": True,
            "no_pick_edge_stake_coupon_emitted": True,
            "production_selectable": False,
            "betting_decisions_enabled": False,
            "sources": ["source-test"],
            "unknowns": [],
            "blocked_reasons": [],
            "evidence_refs": ["artifacts/S4.json"],
            "payload": {
                "source_s4_path": str(run_sandbox / "data" / "2026-07-14_s4_valuation_candidates.json"),
                "source_s4_sha256": "dummy_s4_sha",
                "source_git_sha": "dummy_git_sha",
                "manifest_sha": "dummy_manifest_sha",
                "work_order_id": "WO-1",
                "agent_id": "bet-risk-gatekeeper",
                "policy_version": "1.0",
                "input_candidate_count": 87,
                "candidates": [
                    {
                        "candidate_id": "football|France|Spain|2026-07-14",
                        "home_team": "France",
                        "away_team": "Spain",
                        "participants": ["France", "Spain"],
                        "competition": "International - FIFA World Cup",
                        "scheduled_time": "2026-07-14T19:00:00+00:00",
                        "sport": "football"
                    }
                ],
                "rejected_candidates": [],
                "accounting": {
                    "unaccounted_candidate_ids": [],
                    "duplicate_candidate_ids": [],
                    "overlapping_terminal_categories": []
                }
            }
        }
        (run_sandbox / "artifacts" / "S5.json").write_text(json.dumps(s5_artifact, indent=2))
        
        # 3. Resolve predecessor S5 using resolver
        s5_path, s5_data = resolve_manifest_step_output(
            manifest=manifest,
            run_root=run_sandbox,
            step_id="S5",
            betting_day="2026-07-14",
            run_id="REPLAY_RUN_ID",
            expected_artifact_type="S5_CONTEXT_RISK_CANDIDATE_SET_V2"
        )
        assert s5_path == run_sandbox / "artifacts" / "S5.json"
        assert s5_data["artifact_type"] == "AGENT_ARTIFACT"
        assert len(s5_data["payload"]["candidates"]) == 1
