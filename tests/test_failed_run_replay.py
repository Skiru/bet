"""Focused integration test verifying complete, real subprocess replay of S6->S8 with unpriced candidates."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from bet.pipeline.canonical_continuity import bind_candidate_identity
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
    s2_ev_data["payload"]["s2_output_path"] = str(s2_path)
    s2_ev_data["payload"]["s2_shortlist_sha256"] = s2_sha
    s2_ev_data["payload"]["s2_output_sha256"] = s2_sha
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
    canonical_s4_candidates = []
    for c in s4_content["candidates"]:
        c["kickoff"] = future_time
        c["start_time"] = future_time
        c["betting_day"] = "2026-07-14"
        c["probability_as_of"] = "2026-07-14T06:00:00Z"
        c["probability_confidence"] = "HIGH"
        c["probability_method"] = "MODEL"
        c["source_artifact_path"] = str(s4_path)
        canonical_s4_candidates.append(bind_candidate_identity(c))
    s4_content["schema_version"] = 2
    s4_content["status"] = "PASS"
    s4_content["candidates"] = canonical_s4_candidates

    s4_path.write_text(json.dumps(s4_content, indent=2), encoding="utf-8")
    s4_sha = sha256_file(s4_path)

    # 4. Write S4.json with corrected path/hash
    s4_ev_data = load_fixture_json("S4.json")
    s4_ev_data["payload"]["s4_valuation_output_path"] = str(s4_path)
    s4_ev_data["payload"]["s4_valuation_output_sha256"] = s4_sha
    (artifacts_dir / "S4.json").write_text(json.dumps(s4_ev_data, indent=2), encoding="utf-8")

    # 5. Write S5.json with corrected path/hash
    context_checks = {
        name: {
            "status": "CLEAR",
            "as_of_utc": "2026-07-14T06:00:00Z",
            "source_refs": [f"fixture:{name}"],
        }
        for name in (
            "injuries_lineups",
            "motivation_tournament_context",
            "travel_fatigue",
            "morale_recent_form",
            "upset_volatility_risk",
            "injuries/lineups",
            "motivation/tournament context",
            "travel/fatigue",
            "morale/recent form",
            "upset/volatility risk",
        )
    }
    s5_candidates = json.loads(json.dumps(canonical_s4_candidates))
    for candidate in s5_candidates:
        candidate["context_checks"] = context_checks
        candidate["risk_flags"] = []
        candidate["counter_evidence"] = []
        candidate["fixture_verification"] = {
            "status": "LIVE_FIXTURE_VERIFIED_NOT_STARTED",
            "source": "fixture:canonical-replay",
            "verified_at_utc": "2026-07-14T05:45:00Z",
            "canonical_event_id": candidate["canonical_event_id"],
        }
    s5_data = {
        "schema_version": 1,
        "artifact_type": "AGENT_ARTIFACT",
        "step_id": "S5",
        "status": "PASS",
        "betting_day": "2026-07-14",
        "run_id": "CERT_REPLAY_20260714_PRICING_DEGRADED_V6",
        "work_order_id": "WO-CERT_REPLAY_20260714_PRICING_DEGRADED_V6-S5",
        "point_in_time_as_of": "2026-07-14T06:00:00Z",
        "source_bound": True,
        "no_pick_edge_stake_coupon_emitted": True,
        "production_selectable": False,
        "betting_decisions_enabled": False,
        "sources": ["fixture:canonical-replay"],
        "unknowns": [],
        "blocked_reasons": [],
        "evidence_refs": [str(artifacts_dir / "S4.json")],
        "payload": {
            "work_order_id": "WO-CERT_REPLAY_20260714_PRICING_DEGRADED_V6-S5",
            "agent_id": "bet-risk-gatekeeper",
            "source_git_sha": repo_head_sha(Path(__file__).resolve().parents[1]),
            "manifest_sha": manifest_hash(Path(__file__).resolve().parents[1]),
            "source_s4_path": str(s4_path),
            "source_s4_sha256": s4_sha,
            "policy_version": "S5_CONTEXT_RISK_V2",
            "injuries_lineups": {"status": "CLEAR"},
            "motivation_tournament_context": {"status": "CLEAR"},
            "travel_fatigue": {"status": "CLEAR"},
            "morale_recent_form": {"status": "CLEAR"},
            "upset_volatility_risk": {"status": "CLEAR"},
            "input_candidate_count": len(s5_candidates),
            "candidates": s5_candidates,
            "rejected_candidates": [],
            "accounting": {
                "unaccounted_candidate_ids": [],
                "duplicate_candidate_ids": [],
                "overlapping_terminal_categories": [],
            },
        },
    }
    s5_wo_data = {
        "work_order_id": "WO-CERT_REPLAY_20260714_PRICING_DEGRADED_V6-S5",
        "step_id": "S5",
        "betting_day": "2026-07-14",
        "run_id": "CERT_REPLAY_20260714_PRICING_DEGRADED_V6",
        "agent": "bet-risk-gatekeeper",
        "assigned_agent": "bet-risk-gatekeeper",
        "source_head": repo_head_sha(Path(__file__).resolve().parents[1]),
        "manifest_sha256": manifest_hash(Path(__file__).resolve().parents[1]),
        "status": "COMPLETED",
    }
    s5_wo_path = artifacts_dir / "S5_work_order.json"
    s5_wo_path.write_text(json.dumps(s5_wo_data, indent=2), encoding="utf-8")

    s5_data["work_order_sha256"] = sha256_file(s5_wo_path)
    if "payload" in s5_data and isinstance(s5_data["payload"], dict):
        s5_data["payload"]["work_order_sha256"] = sha256_file(s5_wo_path)
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
    env["PYTHONPATH"] = os.pathsep.join(
        value
        for value in (f"{repo_root}/src:{repo_root}", env.get("PYTHONPATH"))
        if value
    )
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
        "--base-run-dir", str(replay_sandbox.parents[2]),
        "--verbose"
    ]

    res = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if res.returncode != 0:
        log_content = ""
        logs_dir = replay_sandbox / "logs"
        if logs_dir.exists():
            for f in logs_dir.glob("*"):
                log_content += f"\n--- LOG {f.name} ---\n{f.read_text(errors='replace')}\n"
        print(f"DEBUG STDOUT: {res.stdout}")
        print(f"DEBUG STDERR: {res.stderr}")
        print(f"DEBUG LOGS: {log_content}")
        raise AssertionError(f"Pipeline execution failed: {res.stderr}\nStdout: {res.stdout}\nLogs:\n{log_content}")
    assert res.returncode == 0

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

    # 2. Derive Candidate Continuity mechanically from the generated outputs as of REQ-V7-REPLAY-001
    import hashlib
    s5_json = json.loads((replay_sandbox / "artifacts" / "S5.json").read_text(encoding="utf-8"))
    s6_json = json.loads((replay_sandbox / "data" / "repeat_loss_handoff_2026-07-14.json").read_text(encoding="utf-8"))
    s7_json = json.loads((replay_sandbox / "data" / "2026-07-14_s7_gate_results.json").read_text(encoding="utf-8"))
    s7b_json = json.loads((replay_sandbox / "data" / "2026-07-14_s7b_superbet_manual_mapping.json").read_text(encoding="utf-8"))
    s8_json = json.loads((replay_sandbox / "data" / "2026-07-14_s8_superbet_manual_quote_pack.json").read_text(encoding="utf-8"))

    # Helper to extract IDs
    def extract_ids(obj, keys=None):
        if not obj:
            return set()
        if isinstance(obj, list):
            ids = set()
            for x in obj:
                if isinstance(x, dict):
                    if "source_candidate_id" in x:
                        ids.add(x["source_candidate_id"])
                    elif "candidate_id" in x:
                        ids.add(x["candidate_id"])
                    elif "quote_card_id" in x:
                        ids.add(x["quote_card_id"].replace("quote-card-", ""))
                    elif "id" in x:
                        ids.add(x["id"])
                elif isinstance(x, str):
                    ids.add(x)
            return ids
        if isinstance(obj, dict):
            if keys:
                res_set = set()
                for k in keys:
                    res_set.update(extract_ids(obj.get(k, [])))
                return res_set
        return set()

    # Extract sets
    s5_ids = extract_ids(s5_json.get("payload", {}).get("candidates", []))

    s6_accepted = extract_ids(s6_json.get("accepted", []))
    s6_repeat_rejected = extract_ids(s6_json.get("repeat_rejected", []))
    s6_duplicate_rejected = extract_ids(s6_json.get("duplicate_rejected", []))
    s6_conflict_rejected = extract_ids(s6_json.get("conflict_rejected", []))
    s6_correlation_rejected = extract_ids(s6_json.get("correlation_rejected", []))
    s6_portfolio_rejected = extract_ids(s6_json.get("portfolio_rejected", []))
    s6_concentration_rejected = extract_ids(s6_json.get("concentration_rejected", []))
    s6_invalid_input = extract_ids(s6_json.get("invalid_input", []))

    s6_partition_union = (s6_accepted | s6_repeat_rejected | s6_duplicate_rejected |
                          s6_conflict_rejected | s6_correlation_rejected |
                          s6_portfolio_rejected | s6_concentration_rejected | s6_invalid_input)

    s7_input_ids = extract_ids(s7_json, ["priced_approved", "analytical_approved", "review_only", "rejected"])
    s7_approved = extract_ids(s7_json, ["priced_approved", "analytical_approved"])
    s7b_card_ids = extract_ids(s7b_json.get("mapping_suggestions", []))
    s8_card_ids = extract_ids(s8_json.get("quote_cards", []))

    # Assertions
    assert s5_ids == s6_partition_union, "S5 IDs do not equal complete S6 partition"
    assert s6_accepted == s7_input_ids, "S6 accepted does not equal S7 input"
    assert s7_approved == s7b_card_ids, "S7 approved does not equal S7b card IDs"
    assert s7b_card_ids == s8_card_ids, "S7b card IDs do not equal S8 card IDs"

    # Terminal sets disjoint
    terminal_sets = [s6_accepted, s6_repeat_rejected, s6_duplicate_rejected, s6_conflict_rejected, s6_correlation_rejected, s6_portfolio_rejected, s6_concentration_rejected, s6_invalid_input]
    for i in range(len(terminal_sets)):
        for j in range(i + 1, len(terminal_sets)):
            assert terminal_sets[i].isdisjoint(terminal_sets[j]), f"Terminal S6 sets at index {i} and {j} are not disjoint"

    unaccounted = s5_ids - s6_partition_union
    assert len(unaccounted) == 0, f"Unaccounted candidate IDs must be empty: {unaccounted}"

    # Validate the actual run.  No synthetic PASS reports or snapshot-specific
    # Git identities are allowed to participate in this assertion.
    chain_report = replay_sandbox / "validation" / "s6_s8_evidence_chain.json"
    validator_cmd = [
        sys.executable,
        str(repo_root / "scripts" / "validate_run_evidence_chain.py"),
        "--run-root", str(replay_sandbox),
        "--betting-day", "2026-07-14",
        "--run-id", "CERT_REPLAY_20260714_PRICING_DEGRADED_V6",
        "--output", str(chain_report),
    ]
    validator_res = subprocess.run(validator_cmd, capture_output=True, text=True)
    assert validator_res.returncode == 0, f"Evidence chain validator failed: {validator_res.stderr}\nStdout: {validator_res.stdout}"
    validation = json.loads(chain_report.read_text(encoding="utf-8"))
    assert validation["status"] == "PASS"
    assert validation["report_payload"]["issues"] == []
    assert set(validation["report_payload"]["output_sha256"]) == {"S6", "S7", "S7b", "S8"}

    # A post-publication byte change must turn the same validator into a
    # non-zero BLOCK, not merely a report whose status callers can ignore.
    s8_output["tampered_after_publication"] = True
    s8_output_path.write_text(json.dumps(s8_output, indent=2), encoding="utf-8")
    blocked_report = replay_sandbox / "validation" / "tampered_chain.json"
    tampered_cmd = [*validator_cmd[:-1], str(blocked_report)]
    tampered_res = subprocess.run(tampered_cmd, capture_output=True, text=True)
    assert tampered_res.returncode == 1
    blocked = json.loads(blocked_report.read_text(encoding="utf-8"))
    assert blocked["status"] == "BLOCK"
    assert blocked["report_payload"]["issues"]
