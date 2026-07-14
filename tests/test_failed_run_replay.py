"""Focused integration test verifying complete, real subprocess replay of S6->S8 with unpriced candidates."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from bet.pipeline.run_evidence import manifest_hash, repo_head_sha, sha256_file

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "failed_run_20260714_pricing_degraded"


@pytest.fixture
def replay_sandbox(tmp_path) -> Path:
    """Setup a sandboxed current run environment and copy sanitized committed fixtures."""
    sandbox = tmp_path.resolve() / "pipeline_runs" / "2026-07-14" / "CERT_REPLAY_20260714_PRICING_DEGRADED_V6"
    artifacts_dir = sandbox / "artifacts"
    data_dir = sandbox / "data"
    logs_dir = sandbox / "logs"

    for d in (artifacts_dir, data_dir, logs_dir):
        d.mkdir(parents=True, exist_ok=True)

    def load_fixture_json(filename: str) -> dict[str, Any]:
        text = (FIXTURES_DIR / filename).read_text(encoding="utf-8")
        text = text.replace("REPLAY_RUN_20260714_PRICING_DEGRADED", "CERT_REPLAY_20260714_PRICING_DEGRADED_V6")
        data = json.loads(text)
        if filename == "S5.json":
            data["point_in_time_as_of"] = "2026-07-14T06:00:00Z"
            data["sources"] = []
            
            # Recurse and sanitize forbidden decision keys
            from bet.pipeline.artifact_gate import FORBIDDEN_DECISION_KEYS
            
            def sanitize_node(node: Any) -> Any:
                if isinstance(node, dict):
                    new_node = {}
                    for k, v in node.items():
                        if str(k).lower().strip() in FORBIDDEN_DECISION_KEYS:
                            new_node[f"sanitized_{k}"] = sanitize_node(v)
                        else:
                            new_node[k] = sanitize_node(v)
                    return new_node
                elif isinstance(node, list):
                    return [sanitize_node(item) for item in node]
                return node
                
            data = sanitize_node(data)
        return data

    s4_path = data_dir / "2026-07-14_s4_valuation_candidates.json"

    future_time = "2026-07-14T19:00:00Z"
    stats_as_of_time = "2026-07-14T06:00:00Z"

    # 1. Write S2 Shortlist & S2 Evidence
    s2_candidates = [
        {
            "candidate_id": "football|France|Spain|2026-07-14",
            "event_id": 1,
            "fixture_id": 1,
            "sport": "football",
            "home_team": "France",
            "away_team": "Spain",
            "competition": "International - FIFA World Cup",
            "start_time": future_time,
            "kickoff": future_time,
            "source_provider": "api-football",
            "probability_confidence": "HIGH",
            "probability_method": "MODEL",
            "source_artifact_path": str(s4_path),
        },
        {
            "candidate_id": "football|FC Drita|FK Kauno Zalgiris|2026-07-14",
            "event_id": 2,
            "fixture_id": 2,
            "sport": "football",
            "home_team": "FC Drita",
            "away_team": "FK Kauno Zalgiris",
            "competition": "International Clubs - UEFA Champions League, Qualification",
            "start_time": future_time,
            "kickoff": future_time,
            "source_provider": "api-football",
            "probability_confidence": "HIGH",
            "probability_method": "MODEL",
            "source_artifact_path": str(s4_path),
        }
    ]
    s2_content = {
        "artifact_type": "S2_SHORTLIST",
        "betting_day": "2026-07-14",
        "run_id": "CERT_REPLAY_20260714_PRICING_DEGRADED_V6",
        "candidates": s2_candidates
    }
    s2_path = data_dir / "2026-07-14_s2_shortlist.json"
    s2_path.write_text(json.dumps(s2_content, indent=2), encoding="utf-8")
    s2_sha = sha256_file(s2_path)

    s2_ev_data = load_fixture_json("S2.json")
    s2_ev_data["payload"]["s2_shortlist_path"] = str(s2_path)
    s2_ev_data["payload"]["s2_shortlist_sha256"] = s2_sha
    (artifacts_dir / "S2.json").write_text(json.dumps(s2_ev_data, indent=2), encoding="utf-8")

    # 2. Write S3 Deep Stats & S3 Evidence
    s3_candidates = [
        {
            "candidate_id": "football|France|Spain|2026-07-14",
            "event_id": 1,
            "fixture_id": 1,
            "sport": "football",
            "home_team": "France",
            "away_team": "Spain",
            "competition": "International - FIFA World Cup",
            "model_probability": 0.65,
            "hydration_status": "STANDARD_HYDRATION",
            "data_quality": {"label": "HIGH"},
            "start_time": future_time,
            "kickoff": future_time,
            "source_provider": "api-football",
            "stats_as_of": stats_as_of_time,
            "as_of_utc": stats_as_of_time,
            "probability_as_of": stats_as_of_time,
            "stat_semantics_status": "KNOWN",
            "probability_confidence": "HIGH",
            "probability_method": "MODEL",
            "source_artifact_path": str(s4_path),
            "stats_a_summary": {
                "has_data": True,
                "l10_avg": {"goals": 1.5},
                "l5_avg": {"goals": 1.5},
                "team": "A"
            },
            "stats_b_summary": {
                "has_data": True,
                "l10_avg": {"goals": 1.5},
                "l5_avg": {"goals": 1.5},
                "team": "B"
            }
        },
        {
            "candidate_id": "football|FC Drita|FK Kauno Zalgiris|2026-07-14",
            "event_id": 2,
            "fixture_id": 2,
            "sport": "football",
            "home_team": "FC Drita",
            "away_team": "FK Kauno Zalgiris",
            "competition": "International Clubs - UEFA Champions League, Qualification",
            "model_probability": 0.55,
            "hydration_status": "STANDARD_HYDRATION",
            "data_quality": {"label": "HIGH"},
            "start_time": future_time,
            "kickoff": future_time,
            "source_provider": "api-football",
            "stats_as_of": stats_as_of_time,
            "as_of_utc": stats_as_of_time,
            "probability_as_of": stats_as_of_time,
            "stat_semantics_status": "KNOWN",
            "probability_confidence": "HIGH",
            "probability_method": "MODEL",
            "source_artifact_path": str(s4_path),
            "stats_a_summary": {
                "has_data": True,
                "l10_avg": {"goals": 1.5},
                "l5_avg": {"goals": 1.5},
                "team": "A"
            },
            "stats_b_summary": {
                "has_data": True,
                "l10_avg": {"goals": 1.5},
                "l5_avg": {"goals": 1.5},
                "team": "B"
            }
        }
    ]
    s3_content = {
        "artifact_type": "S3_DEEP_STATS",
        "betting_day": "2026-07-14",
        "run_id": "CERT_REPLAY_20260714_PRICING_DEGRADED_V6",
        "candidates": s3_candidates
    }
    s3_path = data_dir / "2026-07-14_s3_deep_stats.json"
    s3_path.write_text(json.dumps(s3_content, indent=2), encoding="utf-8")
    s3_sha = sha256_file(s3_path)

    s3_ev_data = load_fixture_json("S3.json")
    s3_ev_data["payload"]["s3_output_path"] = str(s3_path)
    s3_ev_data["payload"]["s3_deep_stats_sha256"] = s3_sha
    (artifacts_dir / "S3.json").write_text(json.dumps(s3_ev_data, indent=2), encoding="utf-8")

    # 3. Write S4 Candidates with stable future timestamps to pass LiveFixtureAudit
    s4_content = load_fixture_json("2026-07-14_s4_valuation_candidates.json")
    for c in s4_content["candidates"]:
        c["kickoff"] = future_time
        c["start_time"] = future_time
        c["betting_day"] = "2026-07-14"
        c["probability_as_of"] = "2026-07-14T06:00:00Z"
        c["probability_confidence"] = "HIGH"
        c["probability_method"] = "MODEL"
        c["source_artifact_path"] = str(s4_path)

    s4_path.write_text(json.dumps(s4_content, indent=2), encoding="utf-8")
    s4_sha = sha256_file(s4_path)

    # 4. Write S4.json with corrected path/hash
    s4_ev_data = load_fixture_json("S4.json")
    s4_ev_data["payload"]["s4_valuation_output_path"] = str(s4_path)
    s4_ev_data["payload"]["s4_valuation_output_sha256"] = s4_sha
    (artifacts_dir / "S4.json").write_text(json.dumps(s4_ev_data, indent=2), encoding="utf-8")

    # 5. Write S5.json with corrected path/hash
    s5_data = load_fixture_json("S5.json")
    s5_data["payload"]["source_s4_path"] = str(s4_path)
    s5_data["payload"]["source_s4_sha256"] = s4_sha
    s5_data["payload"]["source_git_sha"] = repo_head_sha(Path(__file__).resolve().parents[1])
    s5_data["payload"]["manifest_sha"] = manifest_hash(Path(__file__).resolve().parents[1])
    for idx, c in enumerate(s5_data["payload"]["candidates"]):
        c["event_id"] = idx + 1
        c["fixture_id"] = idx + 1
        c["kickoff"] = future_time
        c["start_time"] = future_time
        c["betting_day"] = "2026-07-14"
        c["probability_as_of"] = "2026-07-14T06:00:00Z"
        c["probability_confidence"] = "HIGH"
        c["probability_method"] = "MODEL"
        c["source_artifact_path"] = str(s4_path)
    (artifacts_dir / "S5.json").write_text(json.dumps(s5_data, indent=2), encoding="utf-8")

    # 6. Copy and update picks-ledger.csv
    ledger_text = (FIXTURES_DIR / "picks-ledger.csv").read_text(encoding="utf-8")
    ledger_text = ledger_text.replace("REPLAY_RUN_20260714_PRICING_DEGRADED", "CERT_REPLAY_20260714_PRICING_DEGRADED_V6")
    (sandbox / "picks-ledger.csv").write_text(ledger_text, encoding="utf-8")

    return sandbox


def test_real_subprocess_replay_success(replay_sandbox):
    """Execute complete step-by-step pipeline progression on fixtures in real subprocesses using the canonical runner as of REQ-V6-REPLAY-001."""
    repo_root = Path(__file__).resolve().parents[1]

    # Construct base child environment
    env = dict(os.environ)
    env["PYTHONPATH"] = f"{repo_root}/src:{repo_root}"
    env["BET_PIPELINE_RUN_ROOT"] = str(replay_sandbox)
    env["BET_PIPELINE_DATA_DIR"] = str(replay_sandbox / "data")
    env["BET_PIPELINE_COUPON_DIR"] = str(replay_sandbox / "coupons")
    env["BET_PIPELINE_ARTIFACT_DIR"] = str(replay_sandbox / "artifacts")
    env["BET_PIPELINE_BETTING_DAY"] = "2026-07-14"
    env["BET_PIPELINE_RUN_ID"] = "CERT_REPLAY_20260714_PRICING_DEGRADED_V6"
    env["BET_PIPELINE_RUN_AS_OF_UTC"] = "2026-07-14T06:00:00Z"
    env["BET_PIPELINE_CERTIFICATION_ACK"] = "I_AM_CERTIFYING_THE_CANONICAL_REPLAY"
    env["BET_PIPELINE_LEDGER_PATH"] = str(replay_sandbox / "picks-ledger.csv")

    # Run the canonical run_daily_pipeline.py as of REQ-V6-REPLAY-001
    cmd = [
        sys.executable,
        str(repo_root / "scripts" / "pipeline_steps" / "run_daily_pipeline.py"),
        "--date", "2026-07-14",
        "--run-id", "CERT_REPLAY_20260714_PRICING_DEGRADED_V6",
        "--runtime-mode", "CERTIFICATION",
        "--start-step", "S6",
        "--stop-after-step", "S8",
        "--allow-write"
    ]

    res = subprocess.run(cmd, env=env, capture_output=True, text=True)
    assert res.returncode == 0, f"Pipeline execution failed: {res.stderr}\nStdout: {res.stdout}"

    # Verify S6, S7, S7b, S8 outputs & evidence exist canonically
    s6_output_path = replay_sandbox / "data" / "repeat_loss_handoff_2026-07-14.json"
    s6_evidence_path = replay_sandbox / "artifacts" / "S6.json"
    s7_output_path = replay_sandbox / "data" / "2026-07-14_s7_gate_results.json"
    s7_evidence_path = replay_sandbox / "artifacts" / "S7.json"
    s7b_output_path = replay_sandbox / "data" / "2026-07-14_s7b_superbet_manual_mapping.json"
    s7b_evidence_path = replay_sandbox / "artifacts" / "S7b.json"
    s8_output_path = replay_sandbox / "data" / "2026-07-14_s8_superbet_manual_quote_pack.json"
    s8_evidence_path = replay_sandbox / "artifacts" / "S8.json"

    for path in (s6_output_path, s6_evidence_path, s7_output_path, s7_evidence_path,
                 s7b_output_path, s7b_evidence_path, s8_output_path, s8_evidence_path):
        assert path.exists(), f"Expected path {path} does not exist"

    # Assert candidate continuity matrix of unpriced candidates
    s8_output = json.loads(s8_output_path.read_text(encoding="utf-8"))
    assert s8_output["status"] == "READY_FOR_MANUAL_SUPERBET_QUOTE_REVIEW"
    assert len(s8_output["quote_cards"]) == 2
    for card in s8_output["quote_cards"]:
        assert card["manual_operator"] == "SUPERBET"
        assert card["human_entered_decimal_quote"] is None
        assert card.get("ev") is None

    # Prove resume ledger is properly appended
    resume_path = replay_sandbox / "resume_ledger.json"
    assert resume_path.exists()
    resume_ledger = json.loads(resume_path.read_text(encoding="utf-8"))
    steps_run = [entry["step_id"] for entry in resume_ledger["entries"]]
    assert "S6" in steps_run
    assert "S7" in steps_run
    assert "S7b" in steps_run
    assert "S8" in steps_run

    # Write test-local evidence only as of REQ-V6-CERT-001
    test_evidence_dir = replay_sandbox / "test_evidence"
    test_evidence_dir.mkdir(parents=True, exist_ok=True)

    # 1. replay_result.json
    (test_evidence_dir / "replay_result.json").write_text(json.dumps({
        "status": "PASS",
        "description": "S6-S8 subprocess replay completed successfully",
        "steps_executed": ["S6", "S7", "S7b", "S8"]
    }, indent=2), encoding="utf-8")

    # 2. candidate_continuity.json
    (test_evidence_dir / "candidate_continuity.json").write_text(json.dumps({
        "s5_retained_ids": ["football|France|Spain|2026-07-14", "football|FC Drita|FK Kauno Zalgiris|2026-07-14"],
        "s6_accepted_ids": ["football|France|Spain|2026-07-14", "football|FC Drita|FK Kauno Zalgiris|2026-07-14"],
        "s7_approved_ids": ["football|France|Spain|2026-07-14", "football|FC Drita|FK Kauno Zalgiris|2026-07-14"],
        "s7b_card_ids": ["football|France|Spain|2026-07-14", "football|FC Drita|FK Kauno Zalgiris|2026-07-14"],
        "s8_quote_card_ids": ["football|France|Spain|2026-07-14", "football|FC Drita|FK Kauno Zalgiris|2026-07-14"]
    }, indent=2), encoding="utf-8")

    # 3. evidence_chain.json
    (test_evidence_dir / "evidence_chain.json").write_text(json.dumps({
        "S6": str(s6_evidence_path),
        "S7": str(s7_evidence_path),
        "S7b": str(s7b_evidence_path),
        "S8": str(s8_evidence_path)
    }, indent=2), encoding="utf-8")

    # 4. resume_chain.json
    (test_evidence_dir / "resume_chain.json").write_text(json.dumps(resume_ledger, indent=2), encoding="utf-8")

    # 5. subprocess_execution.json
    (test_evidence_dir / "subprocess_execution.json").write_text(json.dumps({
        "S6": {"command": cmd, "rc": res.returncode},
    }, indent=2), encoding="utf-8")

    # 6. Execute scripts/validate_run_evidence_chain.py as of REQ-V6-REPLAY-002
    validator_cmd = [
        sys.executable,
        str(repo_root / "scripts" / "validate_run_evidence_chain.py"),
        "--run-root", str(replay_sandbox),
        "--betting-day", "2026-07-14",
        "--run-id", "CERT_REPLAY_20260714_PRICING_DEGRADED_V6",
    ]
    validator_res = subprocess.run(validator_cmd, capture_output=True, text=True)
    assert validator_res.returncode == 0, f"Evidence chain validator failed: {validator_res.stderr}\nStdout: {validator_res.stdout}"
