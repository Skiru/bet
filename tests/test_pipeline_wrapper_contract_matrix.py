"""Contract matrix for normalized wrapper block classification."""
from __future__ import annotations

import json
import os
import sys
import hashlib
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.pipeline_steps import s2_tipsters
from scripts.pipeline_steps import s3_stats
from scripts.pipeline_steps import s5_gate
from scripts.pipeline_steps import s6_repeats
from scripts.pipeline_steps import s7_validate
from scripts.pipeline_steps import s8_build_coupons
from bet.pipeline.canonical_continuity import bind_candidate_identity
from bet.pipeline.run_evidence import sha256_file, repo_head_sha, manifest_hash

ROOT = Path(__file__).resolve().parents[1]

def _seed_s6_predecessors(environ: dict[str, str]) -> None:
    import csv
    run_root = Path(environ["BET_PIPELINE_RUN_ROOT"])
    (run_root / "artifacts").mkdir(parents=True, exist_ok=True)
    (run_root / "data").mkdir(parents=True, exist_ok=True)

    # Empty, schema-valid settled-loss ledger setup.
    ledger_path = run_root / "picks-ledger.csv"
    with open(ledger_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["betting_day", "pick_id", "event", "sport", "market", "selection", "status", "settled_at_utc"])
    os.environ["BET_PIPELINE_LEDGER_PATH"] = str(ledger_path)
    environ["BET_PIPELINE_LEDGER_PATH"] = str(ledger_path)

    # S4
    s4_path = run_root / "data" / "2026-06-25_s4_valuation_candidates.json"
    cand_data = bind_candidate_identity({
        "home_team": "Alpha",
        "away_team": "Beta",
        "sport": "tennis",
        "competition": "Wimbledon",
        "kickoff": "2026-06-25T18:00:00Z",
        "market": "Match Winner",
        "market_family": "RESULT",
        "market_type": "ml",
        "selection": "Alpha",
        "odds_decimal": None,
        "ev": None,
        "model_probability": 0.58,
        "probability_confidence": "HIGH",
        "probability_as_of": "2026-06-25T12:00:00Z",
        "analytical_status": "ANALYTICAL_READY",
        "pricing_status": "PRICE_PENDING",
        "bettable": False,
        "risk_flags": [],
        "counter_evidence": [],
        "safety_score": 0.85,
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
    })
    s3_path = run_root / "data" / "2026-06-25_s3_deep_stats.json"
    s3_path.write_text(json.dumps({"artifact_type": "S3_DEEP_STATS", "analyses": [cand_data]}), encoding="utf-8")
    s4_path.write_text(json.dumps({
        "schema_version": 2,
        "artifact_type": "S4_VALUATION_CANDIDATE_SET_V2", "event_records": [],
        "betting_day": "2026-06-25",
        "run_id": environ["BET_PIPELINE_RUN_ID"],
        "source_s3_path": str(s3_path),
        "source_s3_sha256": sha256_file(s3_path),
        "candidate_count": 1,
        "candidates": [cand_data]
    }), encoding="utf-8")
    s4_ev = {
        "schema_version": 2,
        "artifact_type": "SCRIPT_EVIDENCE",
        "step_id": "S4",
        "betting_day": "2026-06-25",
        "run_id": environ["BET_PIPELINE_RUN_ID"],
        "status": "PASS",
        "payload": {
            "s4_valuation_output_path": str(s4_path),
            "s4_valuation_output_sha256": sha256_file(s4_path)
        }
    }
    (run_root / "artifacts" / "S4.json").write_text(json.dumps(s4_ev), encoding="utf-8")

    # S5
    s5_data = {
        "schema_version": 1,
        "artifact_type": "AGENT_ARTIFACT",
        "step_id": "S5",
        "status": "PASS",
        "betting_day": "2026-06-25",
        "run_id": environ["BET_PIPELINE_RUN_ID"],
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
            "source_s4_path": str(s4_path),
            "source_s4_sha256": sha256_file(s4_path),
            "source_git_sha": repo_head_sha(ROOT),
            "manifest_sha": manifest_hash(ROOT),
            "work_order_id": f"WO-{environ['BET_PIPELINE_RUN_ID']}-S5",
            "agent_id": "bet-risk-gatekeeper",
            "policy_version": "1.0",
            "input_candidate_count": 1,
            "candidates": [cand_data],
            "rejected_candidates": [],
            "accounting": {
                "unaccounted_candidate_ids": [],
                "duplicate_candidate_ids": [],
                "overlapping_terminal_categories": []
            }
        }
    }
    (run_root / "artifacts" / "S5.json").write_text(json.dumps(s5_data), encoding="utf-8")


def _seed_s7_predecessors(environ: dict[str, str]) -> None:
    run_root = Path(environ["BET_PIPELINE_RUN_ROOT"])
    (run_root / "artifacts").mkdir(parents=True, exist_ok=True)
    (run_root / "data").mkdir(parents=True, exist_ok=True)
    _seed_s6_predecessors(environ)

    s5_path = run_root / "artifacts" / "S5.json"
    s6_output_path = run_root / "data" / "repeat_loss_handoff_2026-06-25.json"
    s6_output_data = {
        "schema_version": 1,
        "artifact_type": "S6_PORTFOLIO_REPEAT_GUARD_V2", "event_records": [],
        "status": "PASS",
        "concrete_status": "READY_FOR_S7",
        "betting_day": "2026-06-25",
        "run_id": environ["BET_PIPELINE_RUN_ID"],
        "created_at_utc": "2026-06-25T12:00:00Z",
        "source_step": "S5",
        "source_s5_path": str(s5_path),
        "source_s5_hash": sha256_file(s5_path),
        "source_git_sha": repo_head_sha(ROOT),
        "manifest_sha": manifest_hash(ROOT),
        "policy_version": "1.0",
        "history_snapshot_metadata": {
            "as_of_utc": "2026-06-25T12:00:00Z",
            "snapshot_size": 0,
            "snapshot_sha256": "dummy_history_sha"
        },
        "input_candidate_count": 1,
        "accepted": [
            {
                "candidate_id": "tennis|Alpha|Beta|2026-06-25",
                "decision": "ACCEPTED",
                "reason_codes": [],
                "explanation": "Passed all constraints",
                "original_candidate": {
                    "candidate_id": "tennis|Alpha|Beta|2026-06-25",
                    "home_team": "Alpha",
                    "away_team": "Beta",
                    "sport": "tennis",
                    "competition": "Wimbledon",
                    "best_market": {"name": "Match Winner", "market_family": "RESULT"},
                    "market_count": 4,
                    "odds": {},
                    "odds_decimal": None,
                    "ev": None,
                    "model_probability": 0.58,
                    "probability_confidence": "HIGH",
                    "source_provider": "api-football",
                    "source_artifact_path": "dummy",
                    "probability_as_of": "2026-06-25T12:00:00Z",
                    "market_family": "RESULT",
                    "market_type": "ml",
                    "selection": "Alpha",
                    "pick": "Alpha",
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
    }
    s6_output_path.write_text(json.dumps(s6_output_data), encoding="utf-8")

    s6_ev = {
        "schema_version": 1,
        "artifact_type": "SCRIPT_EVIDENCE",
        "step_id": "S6",
        "betting_day": "2026-06-25",
        "run_id": environ["BET_PIPELINE_RUN_ID"],
        "status": "PASS",
        "payload": {
            "s6_input_path": str(s5_path),
            "s6_output_path": str(s6_output_path),
            "s5_hash": sha256_file(s5_path),
            "output_sha256": sha256_file(s6_output_path),
            "history_snapshot_sha256": "dummy_history_sha",
            "git_sha": repo_head_sha(ROOT),
            "manifest_sha": manifest_hash(ROOT),
            "policy_version": "1.0",
            "as_of_timestamp": "2026-06-25T12:00:00Z",
            "input_candidate_count": 1,
            "accepted_count": 1,
            "repeat_rejected_count": 0,
            "duplicate_rejected_count": 0,
            "conflict_rejected_count": 0,
            "correlation_rejected_count": 0,
            "concentration_rejected_count": 0,
            "invalid_input_count": 0,
            "accounting_summary": {
                "unaccounted_candidate_ids": [],
                "duplicate_candidate_ids": [],
                "overlapping_terminal_categories": []
            },
            "wrapper_child_identity": "s6_repeats.py/check_48h_repeats.py",
            "output_artifact_type": "S6_PORTFOLIO_REPEAT_GUARD_V2"
        }
    }
    (run_root / "artifacts" / "S6.json").write_text(json.dumps(s6_ev), encoding="utf-8")


def _seed_s3_predecessors(environ: dict[str, str]) -> None:
    run_root = Path(environ["BET_PIPELINE_RUN_ROOT"])
    (run_root / "artifacts").mkdir(parents=True, exist_ok=True)
    (run_root / "data").mkdir(parents=True, exist_ok=True)
    _seed_s3_shortlist(environ)
    shortlist_path = run_root / "data" / "2026-06-25_s2_shortlist.json"
    import hashlib
    s2_sha = hashlib.sha256(shortlist_path.read_bytes()).hexdigest()
    s2_ev = {
        "schema_version": 1,
        "artifact_type": "SCRIPT_EVIDENCE",
        "step_id": "S2",
        "betting_day": "2026-06-25",
        "run_id": environ["BET_PIPELINE_RUN_ID"],
        "status": "PASS",
        "payload": {
            "s2_shortlist_path": str(shortlist_path),
            "s2_output_path": str(shortlist_path),
            "s2_output_sha256": s2_sha
        }
    }
    (run_root / "artifacts" / "S2.json").write_text(json.dumps(s2_ev), encoding="utf-8")


NORMALIZATION_CASES = (
    ("S2", s2_tipsters, "s2_tipsters.py", ["tipster_aggregator.py", "tipster_xref.py"], "no valid tips after dedupe", "BLOCKED_NO_VALID_TIPS"),
    ("S3", s3_stats, "s3_stats.py", ["deep_stats_report.py"], "insufficient data for stats generation", "BLOCKED_STATS_GENERATION_INSUFFICIENT_DATA"),
    ("S6", s6_repeats, "s6_repeats.py", ["check_48h_repeats.py"], "repeat signal conflict detected", "BLOCKED_REPEAT_SIGNAL_CONFLICT"),
    ("S8", s8_build_coupons, "s8_build_coupons.py", ["coupon_builder.py"], "coupon blocked by construction guard", "BLOCKED_COUPON_CONSTRUCTION_GUARD"),
)


def _runtime_environ(step_id: str) -> dict[str, str]:
    run_root = Path("/tmp") / f"bet-wrapper-matrix-{step_id.lower()}"
    shutil.rmtree(run_root, ignore_errors=True)
    return {
        "BET_PIPELINE_RUNTIME_MODE": "DRY_RUN",
        "BET_PIPELINE_BETTING_DAY": "2026-06-25",
        "BET_PIPELINE_RUN_ID": f"run-{step_id.lower()}-matrix",
        "BET_PIPELINE_RUN_ROOT": str(run_root),
        "BET_PIPELINE_DATA_DIR": str(run_root / "data"),
        "BET_PIPELINE_COUPON_DIR": str(run_root / "coupons"),
        "BET_PIPELINE_ARTIFACT_DIR": str(run_root / "artifacts"),
    }


def _canonical_evidence_path(environ: dict[str, str], step_id: str) -> Path:
    if step_id == "S6":
        return Path(environ["BET_PIPELINE_ARTIFACT_DIR"]) / "S6.json"
    return (
        Path(environ["BET_PIPELINE_RUN_ROOT"])
        / "pipeline_runs"
        / environ["BET_PIPELINE_BETTING_DAY"]
        / environ["BET_PIPELINE_RUN_ID"]
        / "artifacts"
        / f"{step_id}.json"
    )


def _seed_s3_shortlist(environ: dict[str, str]) -> None:
    data_dir = Path(environ["BET_PIPELINE_DATA_DIR"])
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / f"{environ['BET_PIPELINE_BETTING_DAY']}_s2_shortlist.json").write_text(
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


@pytest.mark.parametrize("step_id,module,argv0,expected_scripts,message,expected_reason", NORMALIZATION_CASES)
def test_wrapper_contract_matrix_normalizes_controlled_block_outputs(
    step_id: str,
    module,
    argv0: str,
    expected_scripts: list[str],
    message: str,
    expected_reason: str,
):
    environ = _runtime_environ(step_id)
    argv = [argv0, "--date", "2026-06-25", "--run-id", environ["BET_PIPELINE_RUN_ID"], "--runtime-mode", "DRY_RUN", "--dry-run"]

    if step_id == "S3":
        _seed_s3_predecessors(environ)
    elif step_id == "S6":
        _seed_s6_predecessors(environ)

    def _controlled(*args, **kwargs):
        print(message)
        return 5

    def _s3_controlled(*args, **kwargs):
        return (5, f"{message}\n")

    with patch.dict(os.environ, environ, clear=False), patch.object(sys, "argv", argv):
        if step_id in {"S7b", "S8"}:
            patch_target = patch("builtins.print")
        elif step_id == "S3":
            patch_target = patch("scripts.pipeline_steps.s3_stats._invoke_deep_stats_report", side_effect=_s3_controlled)
        else:
            patch_target = patch("scripts.pipeline_steps._script_evidence.run_scripts", side_effect=_controlled)
        with patch_target:
            with pytest.raises(SystemExit) as exc_info:
                module.main()

    assert exc_info.value.code == 5
    evidence = json.loads(_canonical_evidence_path(environ, step_id).read_text(encoding="utf-8"))
    assert evidence["status"] == "BLOCK"
    if step_id == "S7b":
        assert evidence["blocked_reasons"] == ["BLOCKED_S7B_CANONICAL_S7_MISSING"]
    elif step_id == "S8":
        assert evidence["blocked_reasons"] == ["BLOCKED_S8_CANONICAL_S7B_INVALID"]
    else:
        assert evidence["blocked_reasons"] == [expected_reason]
        assert evidence["payload"]["wrapper_scripts"] == expected_scripts


@pytest.mark.parametrize(
    "step_id,module,argv0,message,expected_reason",
    (
        ("S2", s2_tipsters, "s2_tipsters.py", "missing upstream shortlist input", "BLOCKED_TIPSTER_DATA_MISSING"),
        ("S3", s3_stats, "s3_stats.py", "snapshot missing for stats stage", "BLOCKED_STATS_INPUT_MISSING"),
        ("S6", s6_repeats, "s6_repeats.py", "repeat guard input missing", "BLOCKED_REPEAT_GUARD_INPUT_MISSING"),
        ("S7b", s7_validate, "s7_validate.py", "market unavailable for validation snapshot", "BLOCKED_MARKET_AVAILABILITY_MISSING"),
        ("S8", s8_build_coupons, "s8_build_coupons.py", "missing approved picks for coupon build", "BLOCKED_COUPON_INPUT_MISSING"),
    ),
)
def test_wrapper_contract_matrix_generic_controlled_phrases_map_to_expected_reason(
    step_id: str,
    module,
    argv0: str,
    message: str,
    expected_reason: str,
):
    environ = _runtime_environ(step_id)
    argv = [argv0, "--date", "2026-06-25", "--run-id", environ["BET_PIPELINE_RUN_ID"], "--runtime-mode", "DRY_RUN", "--dry-run"]

    if step_id == "S3":
        _seed_s3_predecessors(environ)
    elif step_id == "S6":
        _seed_s6_predecessors(environ)

    def _controlled(*args, **kwargs):
        print(message)
        return 6

    def _s3_controlled(*args, **kwargs):
        return (6, f"{message}\n")

    with patch.dict(os.environ, environ, clear=False), patch.object(sys, "argv", argv):
        if step_id in {"S7b", "S8"}:
            patch_target = patch("builtins.print")
        elif step_id == "S3":
            patch_target = patch("scripts.pipeline_steps.s3_stats._invoke_deep_stats_report", side_effect=_s3_controlled)
        else:
            patch_target = patch("scripts.pipeline_steps._script_evidence.run_scripts", side_effect=_controlled)
        with patch_target:
            with pytest.raises(SystemExit) as exc_info:
                module.main()

    assert exc_info.value.code == (5 if step_id in {"S7b", "S8"} else 6)
    evidence = json.loads(_canonical_evidence_path(environ, step_id).read_text(encoding="utf-8"))
    assert evidence["status"] == "BLOCK"
    if step_id == "S7b":
        assert evidence["blocked_reasons"] == ["BLOCKED_S7B_CANONICAL_S7_MISSING"]
    elif step_id == "S8":
        assert evidence["blocked_reasons"] == ["BLOCKED_S8_CANONICAL_S7B_INVALID"]
    else:
        assert evidence["blocked_reasons"] == [expected_reason]
