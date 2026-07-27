"""Focused sweep tests for script-wrapper evidence contracts."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from bet.pipeline.integration_artifacts import write_script_evidence
from bet.pipeline.canonical_continuity import bind_candidate_identity
from bet.pipeline.run_evidence import manifest_hash, repo_head_sha, sha256_file
from bet.pipeline.runtime_paths import is_system_temp_path
from bet.pipeline.orchestrator import Orchestrator
from scripts.pipeline_steps import s2_tipsters
from scripts.pipeline_steps import s3_stats
from scripts.pipeline_steps import s4_valuator
from scripts.pipeline_steps import s5_gate
from scripts.pipeline_steps import s6_repeats
from scripts.pipeline_steps import s8_build_coupons


WRAPPER_CASES = (
    {
        "step_id": "S2",
        "module": s2_tipsters,
        "argv0": "s2_tipsters.py",
        "run_patch": "scripts.pipeline_steps._script_evidence.run_scripts",
        "expected_scripts": ["tipster_aggregator.py", "tipster_xref.py"],
        "block_token": "BLOCKED_NO_VALID_TIPS",
        "no_pick": True,
    },
    {
        "step_id": "S3",
        "module": s3_stats,
        "argv0": "s3_stats.py",
        "run_patch": "scripts.pipeline_steps._script_evidence.run_scripts",
        "expected_scripts": ["deep_stats_report.py"],
        "block_token": "BLOCKED_STATS_INPUT_MISSING",
        "no_pick": True,
    },
    {
        "step_id": "S6",
        "module": s6_repeats,
        "argv0": "s6_repeats.py",
        "run_patch": "scripts.pipeline_steps._script_evidence.run_scripts",
        "expected_scripts": ["check_48h_repeats.py"],
        "block_token": "BLOCKED_REPEAT_SIGNAL_CONFLICT",
        "no_pick": True,
    },
    {
        "step_id": "S7",
        "module": s5_gate,
        "argv0": "s5_gate.py",
        "run_patch": "scripts.pipeline_steps._script_evidence.run_scripts",
        "expected_scripts": [],
        "block_token": "BLOCKED_S7_S6_INPUT_MISSING",
        "no_pick": True,
    },
    {
        "step_id": "S8",
        "module": s8_build_coupons,
        "argv0": "s8_build_coupons.py",
        "run_patch": "scripts.pipeline_steps._script_evidence.run_scripts",
        "expected_scripts": ["coupon_builder.py"],
        "block_token": "BLOCKED_COUPON_INPUT_MISSING",
        "no_pick": False,
    },
)


def _runtime_environ(step_id: str, suffix: str = "") -> dict[str, str]:
    run_root = Path("/tmp") / f"bet-wrapper-sweep-{step_id.lower()}{suffix}"
    if run_root.exists():
        import shutil
        shutil.rmtree(run_root, ignore_errors=True)
    return {
        "BET_PIPELINE_RUNTIME_MODE": "DRY_RUN",
        "BET_PIPELINE_BETTING_DAY": "2026-06-25",
        "BET_PIPELINE_RUN_ID": f"run-{step_id.lower()}{suffix}",
        "BET_PIPELINE_RUN_ROOT": str(run_root),
        "BET_PIPELINE_DATA_DIR": str(run_root / "data"),
        "BET_PIPELINE_COUPON_DIR": str(run_root / "coupons"),
        "BET_PIPELINE_ARTIFACT_DIR": str(run_root / "artifacts"),
        "BET_PIPELINE_LEDGER_PATH": str(run_root / "journal" / "picks-ledger.csv"),
    }


def _canonical_evidence_path(environ: dict[str, str], step_id: str) -> Path:
    return (
        Path(environ["BET_PIPELINE_RUN_ROOT"])
        / "pipeline_runs"
        / environ["BET_PIPELINE_BETTING_DAY"]
        / environ["BET_PIPELINE_RUN_ID"]
        / "artifacts"
        / f"{step_id}.json"
    )


def _mirrored_evidence_path(environ: dict[str, str], step_id: str) -> Path:
    return Path(environ["BET_PIPELINE_ARTIFACT_DIR"]) / f"{step_id}.json"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _seed_s3_shortlist(environ: dict[str, str]) -> Path:
    run_root = Path(environ["BET_PIPELINE_RUN_ROOT"])
    (run_root / "artifacts").mkdir(parents=True, exist_ok=True)
    (run_root / "data").mkdir(parents=True, exist_ok=True)
    shortlist_path = run_root / "data" / f"{environ['BET_PIPELINE_BETTING_DAY']}_s2_shortlist.json"
    
    shortlist_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "artifact_type": "S2_SHORTLIST",
                "total_candidates": 1,
                "candidates": [
                    {
                        "sport": "football",
                        "home_team": "Alpha",
                        "away_team": "Beta",
                        "competition": "Test League",
                        "kickoff": "2026-06-25T18:00:00+00:00",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    s2_ev = {
        "schema_version": 1,
        "artifact_type": "SCRIPT_EVIDENCE",
        "step_id": "S2",
        "betting_day": environ["BET_PIPELINE_BETTING_DAY"],
        "run_id": environ["BET_PIPELINE_RUN_ID"],
        "status": "PASS",
        "payload": {
            "s2_shortlist_path": str(shortlist_path),
            "s2_output_sha256": sha256_file(shortlist_path),
        }
    }
    (run_root / "artifacts" / "S2.json").write_text(json.dumps(s2_ev), encoding="utf-8")
    return shortlist_path


def _write_s3_reports(environ: dict[str, str], *, with_data: int = 1) -> None:
    data_dir = Path(environ["BET_PIPELINE_DATA_DIR"])
    betting_day = environ["BET_PIPELINE_BETTING_DAY"]
    (data_dir / f"{betting_day}_s3_deep_stats.md").write_text("# S3\n", encoding="utf-8")
    (data_dir / f"{betting_day}_s3_deep_stats.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "artifact_type": "S3_DEEP_STATS",
                "betting_day": betting_day,
                "run_id": environ["BET_PIPELINE_RUN_ID"],
                "source_s2_path": str(data_dir / f"{betting_day}_s2_shortlist.json"),
                "source_s2_sha256": sha256_file(data_dir / f"{betting_day}_s2_shortlist.json"),
                "total_candidates": 1,
                "candidates_with_data": with_data,
                "analyses": [], "event_records": [],
            }
        ),
        encoding="utf-8",
    )


def _seed_direct_wrapper_input(environ: dict[str, str], step_id: str) -> None:
    data_dir = Path(environ["BET_PIPELINE_DATA_DIR"])
    data_dir.mkdir(parents=True, exist_ok=True)
    if step_id == "S7b":
        output = data_dir / "2026-06-25_s7_gate_results.json"
        output.write_text(
            json.dumps({"gate_results": {"approved": [{"candidate_id": "candidate-a", "market": "Home win"}]}}),
            encoding="utf-8",
        )
        evidence = _canonical_evidence_path(environ, "S7")
        artifact_type = "SCRIPT_EVIDENCE"
        payload = {"s7_json_output": str(output), "approved_count": 1}
    else:
        output = data_dir / "2026-06-25_s7b_superbet_manual_mapping.json"
        output.write_text(
            json.dumps({
                "schema_version": 1,
                "artifact_type": "S7B_SUPERBET_MANUAL_MAPPING", "event_records": [],
                "status": "READY_FOR_MANUAL_MAPPING",
                "betting_day": "2026-06-25",
                "run_id": environ["BET_PIPELINE_RUN_ID"],
                "operator_workflow": "SUPERBET_MANUAL_BET_BUILDER",
                "operator_availability_asserted": False,
                "approved_candidate_count": 1,
                "represented_candidate_count": 1,
                "mapping_suggestions": [{
                    "quote_card_id": "quote-card-a",
                    "source_candidate_id": "candidate-a",
                    "manual_operator": "SUPERBET",
                    "mapping_ambiguity": "HUMAN_CHECK_REQUIRED",
                    "visible_operator_market_name": None,
                    "visible_operator_line": None,
                    "human_entered_decimal_quote": None,
                    "quote_as_of": None,
                    "operator_availability_asserted": False,
                    "executable_coupon": False,
                    "betting_valid": False,
                    "can_place_bet_now": False,
                }],
            }),
            encoding="utf-8",
        )
        evidence = _canonical_evidence_path(environ, "S7b")
        artifact_type = "SCRIPT_EVIDENCE"
        payload = {"s7b_json_output": str(output), "s7b_output_sha256": sha256_file(output)}
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text(
        json.dumps({
            "schema_version": 1,
            "artifact_type": artifact_type,
            "step_id": "S7" if step_id == "S7b" else "S7b",
            "status": "PASS",
            "betting_day": "2026-06-25",
            "run_id": environ["BET_PIPELINE_RUN_ID"],
            "payload": payload,
        }),
        encoding="utf-8",
    )


def _seed_prior_steps(environ: dict[str, str], step_id: str):
    run_root = Path(environ["BET_PIPELINE_RUN_ROOT"])
    (run_root / "artifacts").mkdir(parents=True, exist_ok=True)
    (run_root / "data").mkdir(parents=True, exist_ok=True)
    
    s1e_path = run_root / "data" / "2026-06-25_s1e_event_universe.json"
    s1e_path.write_text(json.dumps({
        "canonical_event_ids": ["10"],
        "event_records": {
            "10": {
                "fixture_id": 10,
                "home_team": "Alpha",
                "away_team": "Beta",
                "sport": "football"
            }
        }
    }))
    
    for name in ("2026-06-25_s4_valuation_candidates.json", "2026-06-25_s7_gate_results.json", "2026-06-25_s7b_superbet_manual_mapping.json", "2026-06-25_s8_superbet_manual_quote_pack.json"):
        p = run_root / "data" / name
        if p.exists():
            try:
                p.unlink()
            except OSError:
                pass
    
    # S2
    s2_path = run_root / "data" / "2026-06-25_s2_shortlist.json"
    s2_path.write_text(json.dumps({
        "artifact_type": "S2_SHORTLIST",
        "total_candidates": 1,
        "candidates": [{"fixture_id": 10, "home_team": "Alpha", "away_team": "Beta", "sport": "football"}]
    }))
    s2_ev = {
        "schema_version": 1,
        "artifact_type": "SCRIPT_EVIDENCE",
        "step_id": "S2",
        "betting_day": "2026-06-25",
        "run_id": environ["BET_PIPELINE_RUN_ID"],
        "status": "PASS",
        "payload": {
            "s2_shortlist_path": str(s2_path),
            "s2_output_sha256": sha256_file(s2_path),
        }
    }
    (run_root / "artifacts" / "S2.json").write_text(json.dumps(s2_ev))
    
    # S3
    s3_ev = {
        "schema_version": 1,
        "artifact_type": "SCRIPT_EVIDENCE",
        "step_id": "S3",
        "betting_day": "2026-06-25",
        "run_id": environ["BET_PIPELINE_RUN_ID"],
        "status": "PASS",
        "payload": {
            "s3_output_path": str(run_root / "data" / "2026-06-25_s3_deep_stats.json")
        }
    }
    (run_root / "artifacts" / "S3.json").write_text(json.dumps(s3_ev))
    (run_root / "data" / "2026-06-25_s3_deep_stats.json").write_text(json.dumps({
        "artifact_type": "S3_DEEP_STATS", "schema_version": 2, "event_records": [], "analyses": [{"fixture_id": 10, "home_team": "Alpha", "away_team": "Beta", "sport": "football", "best_market": {"name": "Match Winner", "market_family": "RESULT"}}]
    }))
    
    # S4
    s4_ev = {
        "schema_version": 1,
        "artifact_type": "SCRIPT_EVIDENCE",
        "step_id": "S4",
        "betting_day": "2026-06-25",
        "run_id": environ["BET_PIPELINE_RUN_ID"],
        "status": "PASS",
        "payload": {
            "s4_valuation_output_path": str(run_root / "data" / "2026-06-25_s4_valuation_candidates.json")
        }
    }
    (run_root / "artifacts" / "S4.json").write_text(json.dumps(s4_ev))
    (run_root / "data" / "2026-06-25_s4_valuation_candidates.json").write_text(json.dumps({
        "artifact_type": "S4_VALUATION_CANDIDATE_SET_V2", "event_records": [],
        "candidates": [
            {
                "candidate_id": "c1",
                "sport": "football",
                "home_team": "Alpha",
                "away_team": "Beta",
                "competition": "Test League",
                "scheduled_time": "2026-06-25T18:00:00Z",
                "market_family": "RESULT",
                "market": "Match Winner",
                "selection": "Alpha",
                "pick": "Alpha",
                "model_probability": 0.55,
                "probability_confidence": "HIGH",
                "odds": {"market_best": 2.10},
                "pricing_status": "PRICED"
            }
        ]
    }))
    
    # S5
    s5_ev = {
        "schema_version": 1,
        "artifact_type": "AGENT_ARTIFACT",
        "step_id": "S5",
        "betting_day": "2026-06-25",
        "run_id": environ["BET_PIPELINE_RUN_ID"],
        "status": "PASS",
        "point_in_time_as_of": "2026-06-25T12:00:00Z",
        "source_bound": True,
        "no_pick_edge_stake_coupon_emitted": True,
        "production_selectable": False,
        "betting_decisions_enabled": False,
        "sources": ["source-test"],
        "unknowns": [],
        "blocked_reasons": [],
        "evidence_refs": ["artifacts/S4.json"],
        "payload": {
            "source_s4_path": str(run_root / "data" / "2026-06-25_s4_valuation_candidates.json"),
            "source_s4_sha256": "dummy",
            "source_git_sha": "dummy",
            "manifest_sha": "dummy",
            "work_order_id": "WO-1",
            "agent_id": "bet-risk-gatekeeper",
            "policy_version": "1.0",
            "input_candidate_count": 1,
            "candidates": [
                {
                    "candidate_id": "c1",
                    "sport": "football",
                    "home_team": "Alpha",
                    "away_team": "Beta",
                    "competition": "Test League",
                    "scheduled_time": "2026-06-25T18:00:00Z",
                    "market_family": "RESULT",
                    "market": "Match Winner",
                    "selection": "Alpha",
                    "pick": "Alpha",
                    "model_probability": 0.55,
                    "probability_confidence": "HIGH",
                    "odds": {"market_best": 2.10},
                    "pricing_status": "PRICED"
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
    (run_root / "artifacts" / "S5.json").write_text(json.dumps(s5_ev))

    # S6
    s6_ev = {
        "schema_version": 1,
        "artifact_type": "SCRIPT_EVIDENCE",
        "step_id": "S6",
        "betting_day": "2026-06-25",
        "run_id": environ["BET_PIPELINE_RUN_ID"],
        "status": "PASS",
        "payload": {
            "s6_output_path": str(run_root / "data" / "repeat_loss_handoff_2026-06-25.json")
        }
    }
    (run_root / "artifacts" / "S6.json").write_text(json.dumps(s6_ev))
    (run_root / "data" / "repeat_loss_handoff_2026-06-25.json").write_text(json.dumps({
        "schema_version": 1,
        "artifact_type": "S6_PORTFOLIO_REPEAT_GUARD_V2", "event_records": [],
        "status": "PASS",
        "betting_day": "2026-06-25",
        "run_id": environ["BET_PIPELINE_RUN_ID"],
        "accepted": [
            {
                "candidate_id": "c1",
                "decision": "ACCEPTED",
                "reason_codes": [],
                "explanation": "Passed all checks",
                "original_candidate": {
                    "candidate_id": "c1",
                    "sport": "football",
                    "home_team": "Alpha",
                    "away_team": "Beta",
                    "competition": "Test League",
                    "scheduled_time": "2026-06-25T18:00:00Z",
                    "market_family": "RESULT",
                    "market": "Match Winner",
                    "selection": "Alpha",
                    "pick": "Alpha",
                    "model_probability": 0.55,
                    "probability_confidence": "HIGH",
                    "odds": {"market_best": 2.10},
                    "pricing_status": "PRICED"
                }
            }
        ],
        "repeat_rejected": [],
        "correlation_rejected": [],
        "conflict_rejected": [],
        "portfolio_rejected": [],
        "invalid_input": [],
        "accounting": {
            "unaccounted_candidate_ids": [],
            "duplicate_candidate_ids": [],
            "overlapping_terminal_categories": []
        }
    }))
    
    # S7
    s7_ev = {
        "schema_version": 1,
        "artifact_type": "SCRIPT_EVIDENCE",
        "step_id": "S7",
        "betting_day": "2026-06-25",
        "run_id": environ["BET_PIPELINE_RUN_ID"],
        "status": "PASS",
        "payload": {
            "s7_json_output": str(run_root / "data" / "2026-06-25_s7_gate_results.json")
        }
    }
    (run_root / "artifacts" / "S7.json").write_text(json.dumps(s7_ev))
    (run_root / "data" / "2026-06-25_s7_gate_results.json").write_text(json.dumps({
        "artifact_type": "S7_ANALYTICAL_APPROVAL_SET_V2", "event_records": [],
        "outcome": "READY_FOR_PRICED_REVIEW",
        "priced_approved": [
            {
                "candidate_id": "c1",
                "sport": "football",
                "home_team": "Alpha",
                "away_team": "Beta",
                "competition": "Test League",
                "scheduled_time": "2026-06-25T18:00:00Z",
                "market_family": "RESULT",
                "market": "Match Winner",
                "selection": "Alpha",
                "pick": "Alpha",
                "model_probability": 0.55,
                "probability_confidence": "HIGH",
                "odds": {"market_best": 2.10},
                "pricing_status": "PRICED"
            }
        ],
        "analytical_approved": []
    }))
    
    # S7b
    s7b_ev = {
        "schema_version": 1,
        "artifact_type": "SCRIPT_EVIDENCE",
        "step_id": "S7b",
        "betting_day": "2026-06-25",
        "run_id": environ["BET_PIPELINE_RUN_ID"],
        "status": "PASS",
        "payload": {
            "s7b_json_output": str(run_root / "data" / "2026-06-25_s7b_superbet_manual_mapping.json")
        }
    }
    (run_root / "artifacts" / "S7b.json").write_text(json.dumps(s7b_ev))
    (run_root / "data" / "2026-06-25_s7b_superbet_manual_mapping.json").write_text(json.dumps({
        "schema_version": 1,
        "artifact_type": "S7B_SUPERBET_MANUAL_MAPPING", "event_records": [],
        "status": "READY_FOR_MANUAL_MAPPING",
        "betting_day": "2026-06-25",
        "run_id": environ["BET_PIPELINE_RUN_ID"],
        "operator_workflow": "SUPERBET_MANUAL_BET_BUILDER",
        "operator_availability_asserted": False,
        "approved_candidate_count": 1,
        "represented_candidate_count": 1,
        "mapping_suggestions": [
            {
                "quote_card_id": "quote-card-c1",
                "source_candidate_id": "c1",
                "canonical_event_id": "10",
                "event": "Alpha vs Beta",
                "competition": "Test League",
                "requested_market": "Match Winner",
                "requested_line": None,
                "manual_operator": "SUPERBET",
                "mapping_confidence": "UNVERIFIED",
                "mapping_ambiguity": "HUMAN_CHECK_REQUIRED",
                "operator_availability_asserted": False,
                "executable_coupon": False,
                "betting_valid": False,
                "can_place_bet_now": False
            }
        ]
    }))

    # Rebind the synthetic chain to the production contracts used by S4-S8.
    canonical_candidate = bind_candidate_identity(
        {
            "sport": "football",
            "competition": "Test League",
            "home_team": "Alpha",
            "away_team": "Beta",
            "kickoff": "2026-06-25T18:00:00Z",
            "market_family": "RESULT",
            "market_type": "ml",
            "market": "Match Winner",
            "selection": "Alpha",
            "model_probability": 0.55,
            "probability_confidence": "HIGH",
            "analytical_status": "ANALYTICAL_READY",
            "pricing_status": "PRICE_PENDING",
            "ev": None,
            "odds_decimal": None,
            "bettable": False,
            "risk_flags": [],
            "counter_evidence": [],
            "safety_score": 0.8,
            "context_checks": {
                name: {
                    "status": "CLEAR",
                    "as_of_utc": "2026-06-25T12:00:00Z",
                    "source_refs": ["test:bounded-fixture"],
                }
                for name in (
                    "injuries_lineups",
                    "motivation_tournament_context",
                    "travel_fatigue",
                    "morale_recent_form",
                    "upset_volatility_risk",
                )
            },
            "probability_as_of": "2026-06-25T12:00:00Z",
        }
    )

    s3_path = run_root / "data" / "2026-06-25_s3_deep_stats.json"
    s3_path.write_text(json.dumps({"artifact_type": "S3_DEEP_STATS", "analyses": [canonical_candidate]}))
    s3_ev["payload"]["s3_output_sha256"] = sha256_file(s3_path)
    (run_root / "artifacts" / "S3.json").write_text(json.dumps(s3_ev))

    s4_path = run_root / "data" / "2026-06-25_s4_valuation_candidates.json"
    s4_path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "artifact_type": "S4_VALUATION_CANDIDATE_SET_V2", "event_records": [],
                "betting_day": "2026-06-25",
                "run_id": environ["BET_PIPELINE_RUN_ID"],
                "source_s3_path": str(s3_path),
                "source_s3_sha256": sha256_file(s3_path),
                "candidate_count": 1,
                "candidates": [canonical_candidate],
            }
        )
    )
    s4_ev["payload"]["s4_valuation_output_sha256"] = sha256_file(s4_path)
    (run_root / "artifacts" / "S4.json").write_text(json.dumps(s4_ev))

    repo_root = Path(__file__).resolve().parents[1]
    s5_ev["payload"].update(
        {
            "source_s4_path": str(s4_path),
            "source_s4_sha256": sha256_file(s4_path),
            "source_git_sha": repo_head_sha(repo_root),
            "manifest_sha": manifest_hash(repo_root),
            "work_order_id": f"WO-{environ['BET_PIPELINE_RUN_ID']}-S5",
            "input_candidate_count": 1,
            "candidates": [canonical_candidate],
            "rejected_candidates": [],
        }
    )
    s5_path = run_root / "artifacts" / "S5.json"
    s5_path.write_text(json.dumps(s5_ev))

    terminal_record = {
        "candidate_id": canonical_candidate["selection_id"],
        "selection_id": canonical_candidate["selection_id"],
        "decision": "ACCEPTED",
        "reason_codes": [],
        "original_candidate": canonical_candidate,
    }
    s6_path = run_root / "data" / "repeat_loss_handoff_2026-06-25.json"
    s6_payload = {
        "schema_version": 2,
        "artifact_type": "S6_PORTFOLIO_REPEAT_GUARD_V2", "event_records": [],
        "status": "PASS",
        "concrete_status": "READY_FOR_S7",
        "betting_day": "2026-06-25",
        "run_id": environ["BET_PIPELINE_RUN_ID"],
        "source_step": "S5",
        "source_s5_path": str(s5_path),
        "source_s5_sha256": sha256_file(s5_path),
        "worker_contract_version": "1.0",
        "run_as_of_utc": "2026-06-25T12:00:00Z",
        "validated_inputs": {
            "s5_hash": sha256_file(s5_path),
            "history_hash": "a" * 64,
            "policy_hash": "b" * 64,
        },
        "input_candidate_count": 1,
        "accepted": [terminal_record],
        "repeat_rejected": [],
        "duplicate_rejected": [],
        "conflict_rejected": [],
        "correlation_rejected": [],
        "concentration_rejected": [],
        "invalid_input": [],
    }
    s6_path.write_text(json.dumps(s6_payload))
    s6_ev["payload"].update(
        {"s6_output_path": str(s6_path), "s6_output_sha256": sha256_file(s6_path)}
    )
    (run_root / "artifacts" / "S6.json").write_text(json.dumps(s6_ev))

    s7_path = run_root / "data" / "2026-06-25_s7_gate_results.json"
    s7_path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "artifact_type": "S7_ANALYTICAL_APPROVAL_SET_V2", "event_records": [],
                "status": "PASS",
                "outcome": "READY_FOR_ANALYTICAL_OPERATOR_QUOTE_REVIEW",
                "betting_day": "2026-06-25",
                "run_id": environ["BET_PIPELINE_RUN_ID"],
                "priced_approved": [],
                "analytical_approved": [canonical_candidate],
                "rejected": [],
            }
        )
    )
    s7_ev["payload"].update(
        {"s7_json_output": str(s7_path), "s7_output_sha256": sha256_file(s7_path)}
    )
    (run_root / "artifacts" / "S7.json").write_text(json.dumps(s7_ev))

    s7b_path = run_root / "data" / "2026-06-25_s7b_superbet_manual_mapping.json"
    s7b_mapping = json.loads(s7b_path.read_text())
    s7b_mapping["schema_version"] = 2
    card = s7b_mapping["mapping_suggestions"][0]
    card["source_candidate_id"] = canonical_candidate["selection_id"]
    card["selection_id"] = canonical_candidate["selection_id"]
    card["canonical_event_id"] = canonical_candidate["canonical_event_id"]
    for field in ("visible_operator_market_name", "visible_operator_line", "human_entered_decimal_quote", "quote_as_of"):
        card[field] = None
    s7b_path.write_text(json.dumps(s7b_mapping))
    s7b_ev["payload"].update(
        {"s7b_json_output": str(s7b_path), "s7b_output_sha256": sha256_file(s7b_path)}
    )
    (run_root / "artifacts" / "S7b.json").write_text(json.dumps(s7b_ev))

    ledger_path = Path(environ["BET_PIPELINE_LEDGER_PATH"])
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text(
        "betting_day,pick_id,event,sport,market,selection,status,settled_at_utc\n",
        encoding="utf-8",
    )

    if step_id == "S6":
        s6_path.unlink()
        (run_root / "artifacts" / "S6.json").unlink()
    elif step_id == "S7":
        s7_path.unlink()
        (run_root / "artifacts" / "S7.json").unlink()


@pytest.mark.parametrize("case", WRAPPER_CASES, ids=lambda case: case["step_id"])
def test_target_wrappers_write_pass_script_evidence_in_tmp_sandbox(case):
    environ = _runtime_environ(case["step_id"])
    argv = [
        case["argv0"],
        "--date", "2026-06-25",
        "--run-id", environ["BET_PIPELINE_RUN_ID"],
        "--runtime-mode", "DRY_RUN",
        "--dry-run",
    ]

    _seed_prior_steps(environ, case["step_id"])
    s3_shortlist_path = Path(environ["BET_PIPELINE_RUN_ROOT"]) / "data" / "2026-06-25_s2_shortlist.json"

    def _s3_pass(*, betting_day, shortlist_path, child_env, runtime_mode):
        assert shortlist_path.resolve() == s3_shortlist_path.resolve()
        _write_s3_reports(environ, with_data=1)
        return (0, "")

    with patch.dict(os.environ, environ, clear=False), patch.object(sys, "argv", argv):
        if case["step_id"] in {"S6", "S7b", "S8"}:
            patch_target = nullcontext()
        elif case["step_id"] == "S3":
            patch_target = patch("scripts.pipeline_steps.s3_stats._invoke_deep_stats_report", side_effect=_s3_pass)
        else:
            patch_target = patch(case["run_patch"], return_value=0)
        with patch_target:
            with pytest.raises(SystemExit) as exc_info:
                case["module"].main()

    assert exc_info.value.code == 0
    canonical_path = _canonical_evidence_path(environ, case["step_id"])
    mirrored_path = _mirrored_evidence_path(environ, case["step_id"])
    if case["step_id"] == "S6":
        # S6 deliberately publishes one immutable evidence artifact only.
        canonical_path = mirrored_path
    assert canonical_path.exists()
    assert mirrored_path.exists()
    assert is_system_temp_path(canonical_path)
    assert is_system_temp_path(mirrored_path)
    assert "/reports/" not in str(canonical_path)
    assert "/reports/" not in str(mirrored_path)

    evidence = _load(canonical_path)
    assert evidence == _load(mirrored_path)
    assert evidence["artifact_type"] == "SCRIPT_EVIDENCE"
    assert evidence["step_id"] == case["step_id"]
    assert evidence["status"] == "PASS"
    assert evidence["production_selectable"] is False
    assert evidence["betting_decisions_enabled"] is False
    expected_payload = {
        "step_id": case["step_id"],
        "wrapper_scripts": case["expected_scripts"],
        "runtime_mode": "DRY_RUN",
        "dry_run": True,
        "allow_write": False,
        "allow_live_network": False,
        "production_write": False,
        "runtime_path_source": "orchestrator_inherited_sandbox",
        "child_run_root": environ["BET_PIPELINE_RUN_ROOT"],
        "child_artifact_dir": environ["BET_PIPELINE_ARTIFACT_DIR"],
    }
    if case["step_id"] == "S3":
        payload = evidence["payload"]
        for key, value in expected_payload.items():
            assert payload[key] == value
        assert payload["wrapper_rc"] == 0
        assert payload["shortlist_resolved"] is True
        assert payload["shortlist_event_count"] == 1
        assert Path(payload["shortlist_path"]).resolve() == s3_shortlist_path.resolve()
        assert all(is_system_temp_path(path) for path in payload["s3_report_paths"])
    else:
        expected_payload["wrapper_rc"] = 0
        payload = evidence["payload"]
        if case["step_id"] == "S6":
            for key, value in expected_payload.items():
                assert payload[key] == value
        elif case["step_id"] == "S7":
            for key, value in expected_payload.items():
                assert payload[key] == value
                assert payload["s7_input_path"] is not None
                assert is_system_temp_path(payload["s7_json_output"])
                assert "s7_markdown_output" not in payload
            assert payload["total_candidates"] in (0, 1)
            assert payload["approved_count"] in (0, 1)
            assert payload["extended_count"] == 0
            assert payload["rejected_count"] in (0, 1)
            assert payload["approved_count"] + payload["rejected_count"] == payload["total_candidates"]
        elif case["step_id"] == "S7b":
            assert payload["outcome"] == "READY_FOR_MANUAL_MAPPING"
            assert payload["approved_candidate_count"] == 1
            assert payload["represented_candidate_count"] == 1
            assert payload["executable_coupon"] is False
        elif case["step_id"] == "S8":
            assert payload["outcome"] == "READY_FOR_MANUAL_SUPERBET_QUOTE_REVIEW"
            assert payload["quote_card_count"] == 1
            assert payload["executable_coupon"] is False
        elif case["step_id"] == "S2":
            for key, value in expected_payload.items():
                assert payload[key] == value
            assert "s2_output_path" in payload
            assert "s2_output_sha256" in payload
            assert "event_records" in payload
        else:
            assert payload == expected_payload
    if case["no_pick"]:
        assert evidence["no_pick_edge_stake_coupon_emitted"] is True
        assert "production_coupon_write" not in evidence
    elif case["step_id"] not in {"S7b", "S8"}:
        assert evidence["no_pick_edge_stake_coupon_emitted"] is False
        assert evidence["production_coupon_write"] is False
    else:
        assert evidence["no_pick_edge_stake_coupon_emitted"] is True


@pytest.mark.parametrize("case", WRAPPER_CASES, ids=lambda case: case["step_id"])
def test_target_wrappers_write_block_evidence_for_controlled_output(case, capsys: pytest.CaptureFixture[str]):
    environ = _runtime_environ(case["step_id"], "-block")
    argv = [
        case["argv0"],
        "--date", "2026-06-25",
        "--run-id", environ["BET_PIPELINE_RUN_ID"],
        "--runtime-mode", "DRY_RUN",
        "--dry-run",
    ]

    if case["step_id"] == "S3":
        _seed_s3_shortlist(environ)
    elif case["step_id"] in {"S6", "S7"}:
        _seed_prior_steps(environ, case["step_id"])
        if case["step_id"] == "S7":
            (Path(environ["BET_PIPELINE_ARTIFACT_DIR"]) / "S6.json").unlink()
            (Path(environ["BET_PIPELINE_DATA_DIR"]) / "repeat_loss_handoff_2026-06-25.json").unlink()

    def _controlled(*args, **kwargs):
        print(case["block_token"])
        return 9

    def _s3_controlled(*args, **kwargs):
        return (9, f"{case['block_token']}\n")

    with patch.dict(os.environ, environ, clear=False), patch.object(sys, "argv", argv):
        if case["step_id"] in {"S7", "S7b", "S8"}:
            patch_target = nullcontext()
        elif case["step_id"] == "S3":
            patch_target = patch("scripts.pipeline_steps.s3_stats._invoke_deep_stats_report", side_effect=_s3_controlled)
        else:
            patch_target = patch(case["run_patch"], side_effect=_controlled)
        with patch_target:
            with pytest.raises(SystemExit) as exc_info:
                case["module"].main()

    assert exc_info.value.code == (5 if case["step_id"] in {"S7", "S7b", "S8"} else 9)
    captured = capsys.readouterr()
    if case["step_id"] not in {"S3", "S7b", "S8"}:
        assert case["block_token"] in captured.out
    evidence_path = (
        _mirrored_evidence_path(environ, "S6")
        if case["step_id"] == "S6"
        else _canonical_evidence_path(environ, case["step_id"])
    )
    evidence = _load(evidence_path)
    assert evidence["status"] == "BLOCK"
    if case["step_id"] == "S7b":
        assert evidence["blocked_reasons"] == ["BLOCKED_S7B_CANONICAL_S7_MISSING"]
    elif case["step_id"] == "S8":
        assert evidence["blocked_reasons"] == ["BLOCKED_S8_CANONICAL_S7B_INVALID"]
    else:
        assert evidence["blocked_reasons"] == [case["block_token"]]


@pytest.mark.parametrize("case", WRAPPER_CASES, ids=lambda case: case["step_id"])
def test_target_wrappers_write_failed_evidence_for_unexpected_non_zero(case):
    environ = _runtime_environ(case["step_id"], "-failed")
    argv = [
        case["argv0"],
        "--date", "2026-06-25",
        "--run-id", environ["BET_PIPELINE_RUN_ID"],
        "--runtime-mode", "DRY_RUN",
        "--dry-run",
    ]

    if case["step_id"] == "S3":
        _seed_s3_shortlist(environ)
    elif case["step_id"] in {"S6", "S7"}:
        _seed_prior_steps(environ, case["step_id"])
        if case["step_id"] == "S7":
            (Path(environ["BET_PIPELINE_ARTIFACT_DIR"]) / "S6.json").unlink()
            (Path(environ["BET_PIPELINE_DATA_DIR"]) / "repeat_loss_handoff_2026-06-25.json").unlink()

    with patch.dict(os.environ, environ, clear=False), patch.object(sys, "argv", argv):
        if case["step_id"] in {"S7", "S7b", "S8"}:
            patch_target = nullcontext()
        elif case["step_id"] == "S3":
            patch_target = patch("scripts.pipeline_steps.s3_stats._invoke_deep_stats_report", return_value=(42, "unexpected crash"))
        else:
            patch_target = patch(case["run_patch"], return_value=42)
        with patch_target:
            with pytest.raises(SystemExit) as exc_info:
                case["module"].main()

    assert exc_info.value.code == (5 if case["step_id"] in {"S7", "S7b", "S8"} else 42)
    evidence_path = (
        _mirrored_evidence_path(environ, "S6")
        if case["step_id"] == "S6"
        else _canonical_evidence_path(environ, case["step_id"])
    )
    evidence = _load(evidence_path)
    if case["step_id"] == "S7":
        assert evidence["status"] == "BLOCK"
        assert evidence["blocked_reasons"] == ["BLOCKED_S7_S6_INPUT_MISSING"]
    elif case["step_id"] == "S7b":
        assert evidence["status"] == "BLOCK"
        assert evidence["blocked_reasons"] == ["BLOCKED_S7B_CANONICAL_S7_MISSING"]
    elif case["step_id"] == "S8":
        assert evidence["status"] == "BLOCK"
        assert evidence["blocked_reasons"] == ["BLOCKED_S8_CANONICAL_S7B_INVALID"]
    else:
        assert evidence["status"] == "FAILED"
        assert evidence["blocked_reasons"] == ["FAILED_UNEXPECTED_SUBPROCESS_ERROR"]


def test_s4_wrapper_contract_pass_block_failed_and_tmp_paths():
    environ = _runtime_environ("S4")
    argv = [
        "s4_valuator.py",
        "--date", "2026-06-25",
        "--run-id", environ["BET_PIPELINE_RUN_ID"],
        "--runtime-mode", "DRY_RUN",
        "--dry-run",
    ]
    canonical_path = _canonical_evidence_path(environ, "S4")
    mirrored_path = _mirrored_evidence_path(environ, "S4")

    _seed_prior_steps(environ, "S4")
    data_dir = Path(environ["BET_PIPELINE_DATA_DIR"])
    data_dir.mkdir(parents=True, exist_ok=True)
    input_path = data_dir / "2026-06-25_s3_deep_stats.json"
    input_path.write_text(json.dumps({"artifact_type": "S3_DEEP_STATS", "schema_version": 2, "event_records": [], "analyses": [{"fixture_id": 10, "home_team": "Alpha", "away_team": "Beta", "best_market": {"name": "Over 2.5", "safety_score": 0.82}, "markets_evaluated": 4}]}), encoding="utf-8")
    data_alias = Path(environ["BET_PIPELINE_RUN_ROOT"]) / "data-alias"
    data_alias.symlink_to(data_dir, target_is_directory=True)
    aliased_input_path = data_alias / input_path.name
    s3_evidence_path = Path(environ["BET_PIPELINE_ARTIFACT_DIR"]) / "S3.json"
    s3_evidence = _load(s3_evidence_path)
    s3_evidence["payload"]["s3_output_sha256"] = sha256_file(input_path)
    s3_evidence_path.write_text(json.dumps(s3_evidence), encoding="utf-8")

    def _fake_run_scripts(scripts, **_kwargs):
        for invocation in scripts:
            if getattr(invocation, "script", invocation) != "odds_evaluator.py":
                continue
            cmd = invocation.argv
            output_path = Path(cmd[cmd.index("--output") + 1])
            output_path.write_text(json.dumps({
                "schema_version": 2,
                "artifact_type": "S4_VALUATION_CANDIDATE_SET_V2", "event_records": [],
                "betting_day": "2026-06-25",
                "run_id": environ["BET_PIPELINE_RUN_ID"],
                "created_at_utc": "2026-06-25T00:00:00+00:00",
                "runtime_mode": "DRY_RUN",
                "source_s3_path": str(aliased_input_path),
                "source_s3_sha256": sha256_file(input_path),
                "odds_snapshot_paths": [],
                "candidate_count": 1,
                "contains_odds": True,
                "contains_ev": True,
                "contains_safety": True,
                "contains_market_count": True,
                "production_selectable": False,
                "betting_decisions_enabled": False,
                "no_pick_edge_stake_coupon_emitted": True,
                "candidates": [{"fixture_id": 10, "home_team": "Alpha", "away_team": "Beta", "best_market": {"name": "Over 2.5", "safety_score": 0.82}, "market_count": 4, "markets_evaluated": 4, "odds": {"market_best": 1.91}, "ev": 0.11, "safety_score": 0.82, "safety_markets": [], "valuation_warnings": [], "valuation_status": "VALUED"}],
            }), encoding="utf-8")
        return 0

    with patch.dict(os.environ, environ, clear=False), \
         patch.object(sys, "argv", argv), \
         patch.object(s4_valuator, "run_scripts", side_effect=_fake_run_scripts):
        with pytest.raises(SystemExit) as exc_info:
            s4_valuator.main()

    assert exc_info.value.code == 0
    evidence = _load(canonical_path)
    assert evidence == _load(mirrored_path)
    assert evidence["status"] == "PASS"
    assert evidence["no_pick_edge_stake_coupon_emitted"] is True
    assert evidence["production_selectable"] is False
    assert evidence["betting_decisions_enabled"] is False
    assert evidence["payload"]["runtime_path_source"] == "orchestrator_inherited_sandbox"
    assert evidence["payload"]["child_artifact_dir"] == environ["BET_PIPELINE_ARTIFACT_DIR"]
    assert is_system_temp_path(canonical_path)
    assert "/reports/" not in str(canonical_path)

    output_path = data_dir / "2026-06-25_s4_valuation_candidates.json"
    if output_path.exists():
        output_path.unlink()

    with patch.dict(os.environ, environ, clear=False), \
         patch.object(sys, "argv", argv), \
         patch.object(s4_valuator, "run_scripts", return_value=0):
        with pytest.raises(SystemExit) as exc_info:
            s4_valuator.main()

    assert exc_info.value.code == 1
    evidence = _load(canonical_path)
    assert evidence["status"] == "BLOCK"
    assert evidence["blocked_reasons"] == ["BLOCKED_S4_VALUATION_OUTPUT_MISSING"]

    with patch.dict(os.environ, environ, clear=False), \
         patch.object(sys, "argv", argv), \
         patch("scripts.pipeline_steps.s4_valuator.run_scripts", return_value=77):
        with pytest.raises(SystemExit) as exc_info:
            s4_valuator.main()

    assert exc_info.value.code == 77
    evidence = _load(canonical_path)
    assert evidence["status"] == "FAILED"
    assert evidence["blocked_reasons"] == ["FAILED_UNEXPECTED_SUBPROCESS_ERROR"]


def test_orchestrator_links_wrapper_block_evidence_without_missing_marker(tmp_path):
    reports_root = tmp_path / "sandbox"
    orch = Orchestrator(
        betting_day="2026-06-25",
        run_id="run-s4-block-link",
        runtime_mode="DRY_RUN",
        base_run_dir=reports_root,
    )

    write_script_evidence(
        "S2.9",
        status="PASS",
        payload={"test": True},
        sources=(),
        evidence_refs=(),
        environ=orch.env,
        no_pick_edge_stake_coupon_emitted=True,
        production_selectable=False,
        betting_decisions_enabled=False,
    )
    write_script_evidence(
        "S3",
        status="PASS",
        payload={"test": True},
        sources=(),
        evidence_refs=(),
        environ=orch.env,
        no_pick_edge_stake_coupon_emitted=True,
        production_selectable=False,
        betting_decisions_enabled=False,
    )

    with patch("bet.pipeline.orchestrator.run_bounded_process") as mock_run:
        def side_effect(*args, **kwargs):
            write_script_evidence(
                "S4",
                status="BLOCK",
                payload={"test": True},
                sources=(),
                evidence_refs=(),
                environ=orch.env,
                no_pick_edge_stake_coupon_emitted=True,
                production_selectable=False,
                betting_decisions_enabled=False,
                blocked_reasons=("BLOCKED_UPSTREAM_DATA_MISSING",),
            )
            result = MagicMock()
            result.returncode = 1
            return result

        mock_run.side_effect = side_effect
        summary = orch.run(start_step="S4", stop_after_step="S4")

    assert summary["status"] == "BLOCK"
    assert summary["blocked_at_step"] == "S4"
    step = next(item for item in summary["steps"] if item["step_id"] == "S4")
    assert step["evidence_path"]
    assert not any("BLOCKED_SCRIPT_EVIDENCE_MISSING" in str(blocker) for blocker in summary["blockers"])
    summary_path = orch.run_root / "run_summary.json"
    summary_data = json.loads(summary_path.read_text(encoding="utf-8"))
    s4_step = next(item for item in summary_data["steps"] if item["step_id"] == "S4")
    assert s4_step["evidence_path"] == step["evidence_path"]
