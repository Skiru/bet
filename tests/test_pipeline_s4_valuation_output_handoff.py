"""Focused S4 valuation output handoff tests."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest

from bet.pipeline.canonical_continuity import bind_candidate_identity
from bet.pipeline.run_evidence import sha256_file
from bet.pipeline.runtime_paths import is_system_temp_path
from scripts import odds_evaluator
from scripts.pipeline_steps import s4_valuator, s5_gate, s8_build_coupons


def _runtime_environ() -> dict[str, str]:
    run_root = Path("/tmp") / f"bet-s4-valuation-{uuid.uuid4().hex}"
    return {
        "BET_PIPELINE_RUNTIME_MODE": "DRY_RUN",
        "BET_PIPELINE_BETTING_DAY": "2026-06-25",
        "BET_PIPELINE_RUN_ID": "run-s4-valuation",
        "BET_PIPELINE_RUN_ROOT": str(run_root),
        "BET_PIPELINE_DATA_DIR": str(run_root / "data"),
        "BET_PIPELINE_COUPON_DIR": str(run_root / "coupons"),
        "BET_PIPELINE_ARTIFACT_DIR": str(run_root / "artifacts"),
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


def _input_payload() -> dict:
    return {
        "analyses": [
            {
                "fixture_id": 10,
                "sport": "football",
                "home_team": "Alpha",
                "away_team": "Beta",
                "competition": "Test League",
                "kickoff": "2026-06-25T18:00:00+00:00",
                "best_market": {
                    "name": "Over 2.5",
                    "direction": "OVER",
                    "probability": 0.62,
                    "safety_score": 0.82,
                },
                "markets_evaluated": 4,
                "hit_rate_l10": 0.6,
                "hit_rate_l5": 0.8,
                "warnings": [],
            }
        ]
    }


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _write_s4_pass_evidence(environ: dict[str, str], valuation_path: Path) -> None:
    payload = {
        "schema_version": 1,
        "artifact_type": "SCRIPT_EVIDENCE",
        "step_id": "S4",
        "betting_day": environ["BET_PIPELINE_BETTING_DAY"],
        "run_id": environ["BET_PIPELINE_RUN_ID"],
        "status": "PASS",
        "payload": {
            "step_id": "S4",
            "s4_valuation_output_path": str(valuation_path),
            "s4_valuation_output_sha256": sha256_file(valuation_path),
        },
    }
    for path in (
        Path(environ["BET_PIPELINE_ARTIFACT_DIR"]) / "S4.json",
        _canonical_evidence_path(environ, "S4"),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")


def test_odds_evaluator_explicit_input_output_writes_s4_contract(tmp_path, monkeypatch):
    input_path = _write_json(tmp_path / "input.json", _input_payload())
    output_path = tmp_path / "2026-06-25_s4_valuation_candidates.json"

    def _inject(candidates, _date):
        for candidate in candidates:
            candidate["odds"] = {"market_best": 1.91}
            candidate["odds_source"] = "test"
            candidate["ev"] = 0.11
            candidate["ev_source"] = "test"

    monkeypatch.setattr(odds_evaluator, "_inject_ev_from_odds", _inject)
    ok, msg = odds_evaluator.run_odds_eval(
        "2026-06-25",
        {},
        input_path=input_path,
        output_path=output_path,
        runtime_mode="DRY_RUN",
    )

    assert ok is True
    assert "with EV data" in msg
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["artifact_type"] in ("S4_VALUATION_CANDIDATE_SET_V2", "S4_VALUATION_CANDIDATES")
    assert payload["candidate_count"] > 0
    assert payload["contains_odds"] is True
    assert payload["contains_ev"] is True
    assert payload["contains_safety"] is True
    assert payload["contains_market_count"] is True
    assert payload["production_selectable"] is False
    assert payload["betting_decisions_enabled"] is False
    assert payload["no_pick_edge_stake_coupon_emitted"] is True


def test_market_semantics_preserved_market_matrix_to_shortlist_to_s4(monkeypatch):
    candidates = [
        {
            "candidate_id": "football|Alpha|Beta|2026-06-25",
            "fixture_id": 10,
            "sport": "football",
            "home_team": "Alpha",
            "away_team": "Beta",
            "competition": "Test League",
            "kickoff": "2026-06-25T18:00:00+00:00",
            "best_market": {},
            "probability_confidence": "HIGH",
        }
    ]
    shortlist_payload = {
        "candidates": [
            {
                "sport": "football",
                "home_team": "Alpha",
                "away_team": "Beta",
                "kickoff": "2026-06-25T18:00:00+00:00",
                "source_artifact_path": "/tmp/2026-06-25_s2_shortlist.json",
                "odds_markets": [
                    {
                        "market": "ml:away",
                        "market_type": "ml",
                        "outcome": "away",
                        "point": None,
                        "best_odds": 2.1,
                        "best_bookmaker": "bet365",
                        "source": "odds-api",
                    }
                ],
            }
        ]
    }

    candidates[0]["odds"] = {"market_best": 2.1}
    odds_evaluator._enrich_candidate_market_semantics(
        candidates,
        shortlist_payload,
        "/tmp/2026-06-25_s3_deep_stats.json",
    )
    valuation_candidate = odds_evaluator._build_valuation_candidate(candidates[0])

    assert valuation_candidate["market_family"] == "RESULT"
    assert valuation_candidate["market_type"] == "ml"
    assert valuation_candidate["market"] == "ml:away"
    assert valuation_candidate["selection"] == "Beta"


def test_raw_probability_not_counted_as_model_probability_ready(tmp_path, monkeypatch):
    candidates = [
        {
            "candidate_id": "football|Alpha|Beta|2026-06-25",
            "fixture_id": 10,
            "sport": "football",
            "home_team": "Alpha",
            "away_team": "Beta",
            "competition": "Test League",
            "scheduled_time": "2026-06-25T18:00:00+00:00",
            "best_market": {"name": "Goals Total O/U", "direction": "OVER", "line": 2.5, "probability": 0.58},
            "probability_confidence": "MINIMAL",
            "odds": {"market_best": 1.91},
        }
    ]

    monkeypatch.setattr(odds_evaluator, "DATA_DIR", tmp_path)

    odds_evaluator._inject_ev_from_odds(candidates, "2026-06-25")

    assert candidates[0]["model_probability"] is None
    assert candidates[0]["reference_model_probability"] == 0.58
    assert candidates[0]["probability_missing_reason"] == "LOW_CONFIDENCE_MODEL_PROBABILITY"


def test_model_probability_ready_cannot_exceed_market_probability_input_ready():
    from bet.pipeline.market_probability_inputs import build_market_probability_input, validate_market_probability_input

    stats_seed = {
        "best_market": None,
        "source_provider": "api-football",
        "source_artifact_path": "/tmp/s4.json",
        "probability_as_of": "2026-06-25T12:00:00Z",
        "stats_a_summary": {"has_data": True, "l10_avg": {"goals": 2.0}, "sources": ["db"]},
        "stats_b_summary": {"has_data": True, "l10_avg": {"goals": 1.0}, "sources": ["db"]},
        "h2h_summary": {"has_data": False, "meetings_count": 0, "averages": {}},
        "raw_data": {},
    }
    candidates = [
        {
            "candidate_id": "supported",
            "sport": "football",
            "market_family": "RESULT",
            "market_type": "ml",
            "market": "ml:away",
            "selection": "Beta",
            "pick": "Beta",
                "home_team": "Alpha",
                "away_team": "Beta",
                "probability_confidence": "HIGH",
                "source_provider": "api-football",
                "source_artifact_path": "/tmp/s4.json",
                "reference_model_probability": 0.58,
                "model_probability": None,
            },
        {
            "candidate_id": "unsupported",
            "sport": "football",
            "market_family": "UNSUPPORTED_PROP_MATCH",
            "market_type": "player_tackles",
            "selection": "OVER",
            "direction": "OVER",
            "line": 2.5,
            "home_team": "Alpha",
            "away_team": "Beta",
            "probability_confidence": "MINIMAL",
            "reference_model_probability": 0.52,
            "model_probability": None,
        },
    ]

    ready_inputs = 0
    ready_probabilities = 0
    for candidate in candidates:
        inp = build_market_probability_input(candidate, stats_seed)
        valid, _ = validate_market_probability_input(inp)
        if valid:
            ready_inputs += 1
        if candidate.get("model_probability") is not None:
            ready_probabilities += 1

    assert ready_inputs == 1
    assert ready_probabilities == 0
    assert ready_probabilities <= ready_inputs


def test_odds_evaluator_rejects_protected_repo_output_in_non_production(tmp_path):
    input_path = _write_json(tmp_path / "input.json", _input_payload())
    output_path = Path(__file__).resolve().parents[1] / "betting" / "data" / "forbidden_s4.json"

    ok, msg = odds_evaluator.run_odds_eval(
        "2026-06-25",
        {},
        input_path=input_path,
        output_path=output_path,
        runtime_mode="DRY_RUN",
    )

    assert ok is False
    assert "Protected non-production valuation path rejected" in msg


def _seed_prior_evidence_for_s4(environ: dict[str, str]):
    run_root = Path(environ["BET_PIPELINE_RUN_ROOT"])
    (run_root / "artifacts").mkdir(parents=True, exist_ok=True)
    (run_root / "data").mkdir(parents=True, exist_ok=True)
    s3_output = run_root / "data" / "2026-06-25_s3_deep_stats.json"
    if not s3_output.exists():
        s3_output.write_text(json.dumps(_input_payload()), encoding="utf-8")
    s3_ev = {
        "schema_version": 1,
        "artifact_type": "SCRIPT_EVIDENCE",
        "step_id": "S3",
        "betting_day": "2026-06-25",
        "run_id": environ["BET_PIPELINE_RUN_ID"],
        "status": "PASS",
        "payload": {
            "s3_output_path": str(s3_output),
            "s3_output_sha256": sha256_file(s3_output),
        }
    }
    (run_root / "artifacts" / "S3.json").write_text(json.dumps(s3_ev), encoding="utf-8")


def test_s4_wrapper_passes_explicit_input_output_and_writes_evidence():
    environ = _runtime_environ()
    _seed_prior_evidence_for_s4(environ)
    data_dir = Path(environ["BET_PIPELINE_DATA_DIR"])
    input_path = _write_json(data_dir / "2026-06-25_s3_deep_stats.json", _input_payload())
    recorded: dict[str, object] = {}

    def fake_run_scripts(scripts, **_kwargs):
        for invocation in scripts:
            if getattr(invocation, "script", invocation) != "odds_evaluator.py":
                continue
            cmd = invocation.argv
            recorded["eval_cmd"] = list(cmd)
            output_path = Path(cmd[cmd.index("--output") + 1])
            output_payload = {
                "schema_version": 2,
                "artifact_type": "S4_VALUATION_CANDIDATE_SET_V2",
                "betting_day": "2026-06-25",
                "run_id": environ["BET_PIPELINE_RUN_ID"],
                "created_at_utc": "2026-06-25T00:00:00+00:00",
                "runtime_mode": "DRY_RUN",
                "source_s3_path": cmd[cmd.index("--input") + 1],
                "source_s3_sha256": sha256_file(Path(cmd[cmd.index("--input") + 1])),
                "odds_snapshot_paths": [str(data_dir / "odds_api_snapshot.json")],
                "candidate_count": 1,
                "contains_odds": True,
                "contains_ev": True,
                "contains_safety": True,
                "contains_market_count": True,
                "production_selectable": False,
                "betting_decisions_enabled": False,
                "no_pick_edge_stake_coupon_emitted": True,
                "candidates": [
                    {
                        "fixture_key": "alpha|beta",
                        "fixture_id": 10,
                        "home_team": "Alpha",
                        "away_team": "Beta",
                        "competition": "Test League",
                        "scheduled_time": "2026-06-25T18:00:00+00:00",
                        "source_steps": ["S3", "S4"],
                        "probability": 0.62,
                        "hit_rate_l10": 0.6,
                        "hit_rate_l5": 0.8,
                        "best_market": {"name": "Over 2.5", "safety_score": 0.82},
                        "market_count": 4,
                        "markets_evaluated": 4,
                        "odds": {"market_best": 1.91},
                        "odds_source": "test",
                        "ev": 0.11,
                        "ev_source": "test",
                        "safety_score": 0.82,
                        "safety_markets": [],
                        "valuation_warnings": [],
                        "valuation_status": "VALUED",
                    }
                ],
            }
            output_path.write_text(json.dumps(output_payload), encoding="utf-8")
        return 0

    _write_json(data_dir / "odds_api_snapshot.json", {"events": []})
    argv = ["s4_valuator.py", "--date", "2026-06-25", "--run-id", environ["BET_PIPELINE_RUN_ID"], "--runtime-mode", "DRY_RUN", "--dry-run"]
    with patch.dict(os.environ, environ, clear=False), patch.object(sys, "argv", argv), patch.object(
        s4_valuator, "run_scripts", side_effect=fake_run_scripts
    ):
        with pytest.raises(SystemExit) as exc_info:
            s4_valuator.main()

    assert exc_info.value.code == 0
    eval_cmd = recorded["eval_cmd"]
    assert "--input" in eval_cmd
    assert Path(eval_cmd[eval_cmd.index("--input") + 1]).resolve() == input_path.resolve()
    assert "--output" in eval_cmd
    evidence = json.loads(_canonical_evidence_path(environ, "S4").read_text(encoding="utf-8"))
    assert evidence["status"] == "PASS"
    assert is_system_temp_path(evidence["payload"]["s4_valuation_output_path"])
    assert evidence["payload"]["s4_candidate_count"] == 1
    assert evidence["payload"]["s4_contains_odds"] is True
    assert evidence["payload"]["s4_contains_ev"] is True
    assert evidence["payload"]["s4_contains_safety"] is True
    assert evidence["payload"]["s4_contains_market_count"] is True


def test_s4_wrapper_blocks_when_input_missing():
    environ = _runtime_environ()
    argv = ["s4_valuator.py", "--date", "2026-06-25", "--run-id", environ["BET_PIPELINE_RUN_ID"], "--runtime-mode", "DRY_RUN", "--dry-run"]

    with patch.dict(os.environ, environ, clear=False), patch.object(sys, "argv", argv):
        with pytest.raises(SystemExit) as exc_info:
            s4_valuator.main()

    assert exc_info.value.code == 1
    evidence = json.loads(_canonical_evidence_path(environ, "S4").read_text(encoding="utf-8"))
    assert evidence["status"] == "BLOCK"
    assert evidence["blocked_reasons"] == ["BLOCKED_S4_VALUATION_INPUT_MISSING"]


def test_s4_wrapper_blocks_when_evaluator_does_not_write_output():
    environ = _runtime_environ()
    _seed_prior_evidence_for_s4(environ)
    data_dir = Path(environ["BET_PIPELINE_DATA_DIR"])
    _write_json(data_dir / "2026-06-25_s3_deep_stats.json", _input_payload())

    def fake_run_scripts(_scripts, **_kwargs):
        return 0

    argv = ["s4_valuator.py", "--date", "2026-06-25", "--run-id", environ["BET_PIPELINE_RUN_ID"], "--runtime-mode", "DRY_RUN", "--dry-run"]
    with patch.dict(os.environ, environ, clear=False), patch.object(sys, "argv", argv), patch.object(
        s4_valuator, "run_scripts", side_effect=fake_run_scripts
    ):
        with pytest.raises(SystemExit) as exc_info:
            s4_valuator.main()

    assert exc_info.value.code == 1
    evidence = json.loads(_canonical_evidence_path(environ, "S4").read_text(encoding="utf-8"))
    assert evidence["status"] == "BLOCK"
    assert evidence["blocked_reasons"] == ["BLOCKED_S4_VALUATION_OUTPUT_MISSING"]


def _seed_prior_steps_for_s7(environ: dict[str, str], valuation_path: Path):
    run_root = Path(environ["BET_PIPELINE_RUN_ROOT"])
    (run_root / "artifacts").mkdir(parents=True, exist_ok=True)
    (run_root / "data").mkdir(parents=True, exist_ok=True)
    s2_ev = {
        "schema_version": 1,
        "artifact_type": "SCRIPT_EVIDENCE",
        "step_id": "S2",
        "betting_day": "2026-06-25",
        "run_id": environ["BET_PIPELINE_RUN_ID"],
        "status": "PASS",
        "payload": {
            "s2_shortlist_path": str(run_root / "data" / "2026-06-25_s2_shortlist.json")
        }
    }
    (run_root / "artifacts" / "S2.json").write_text(json.dumps(s2_ev), encoding="utf-8")
    (run_root / "data" / "2026-06-25_s2_shortlist.json").write_text(json.dumps({
        "total_candidates": 1,
        "candidates": [{"fixture_id": 10, "home_team": "Alpha", "away_team": "Beta", "sport": "tennis"}]
    }), encoding="utf-8")
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
    (run_root / "artifacts" / "S3.json").write_text(json.dumps(s3_ev), encoding="utf-8")
    (run_root / "data" / "2026-06-25_s3_deep_stats.json").write_text(json.dumps({
        "analyses": [
            {
                "candidate_id": "tennis|Alpha|Beta|2026-06-25",
                "fixture_id": 10,
                "sport": "tennis",
                "home_team": "Alpha",
                "away_team": "Beta",
                "competition": "Wimbledon",
                "kickoff": "2026-06-25T18:00:00Z",
                "model_probability": 0.58,
                "probability_confidence": "HIGH",
                "source_provider": "api-football",
                "source_artifact_path": str(valuation_path),
                "probability_as_of": "2026-06-25T12:00:00Z",
                "stats_a_summary": {"has_data": True, "l10_avg": {"games_won": 12.0}, "sources": ["db"]},
                "stats_b_summary": {"has_data": True, "l10_avg": {"games_won": 10.0}, "sources": ["db"]},
                "best_market": {"name": "Match Winner", "market_family": "RESULT"}
            }
        ]
    }), encoding="utf-8")


def _seed_s5_and_s6_for_s7(environ: dict[str, str], s4_path: Path, s4_candidates: list[dict]):
    from bet.pipeline.run_evidence import sha256_file, repo_head_sha, manifest_hash
    run_root = Path(environ["BET_PIPELINE_RUN_ROOT"])
    (run_root / "artifacts").mkdir(parents=True, exist_ok=True)
    (run_root / "data").mkdir(parents=True, exist_ok=True)
    
    repo_root = Path(__file__).resolve().parents[1]
    bound_candidates = []
    for candidate in s4_candidates:
        prepared = {
            "kickoff": "2026-06-25T18:00:00Z",
            "analytical_status": "ANALYTICAL_READY",
            **candidate,
        }
        bound_candidates.append(bind_candidate_identity(prepared))
    s4_candidates[:] = bound_candidates

    # S5
    s5_output_data = {
        "schema_version": 2,
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
            "source_s4_sha256": sha256_file(s4_path) if s4_path.exists() else "dummy",
            "source_git_sha": repo_head_sha(repo_root),
            "manifest_sha": manifest_hash(repo_root),
            "work_order_id": f"WO-{environ['BET_PIPELINE_RUN_ID']}-S5",
            "agent_id": "bet-risk-gatekeeper",
            "policy_version": "1.0",
            "input_candidate_count": len(bound_candidates),
            "candidates": bound_candidates,
            "rejected_candidates": [],
            "accounting": {
                "unaccounted_candidate_ids": [],
                "duplicate_candidate_ids": [],
                "overlapping_terminal_categories": []
            }
        }
    }
    s5_path = run_root / "artifacts" / "S5.json"
    s5_path.write_text(json.dumps(s5_output_data, indent=2), encoding="utf-8")
    
    # S6
    s6_output_path = run_root / "data" / "repeat_loss_handoff_2026-06-25.json"
    s6_output_data = {
        "schema_version": 2,
        "artifact_type": "S6_PORTFOLIO_REPEAT_GUARD_V2",
        "status": "PASS",
        "concrete_status": "READY_FOR_S7",
        "betting_day": "2026-06-25",
        "run_id": environ["BET_PIPELINE_RUN_ID"],
        "created_at_utc": "2026-06-25T12:00:00Z",
        "source_step": "S5",
        "source_s5_path": str(s5_path),
        "source_s5_sha256": sha256_file(s5_path),
        "source_git_sha": repo_head_sha(repo_root),
        "manifest_sha": manifest_hash(repo_root),
        "policy_version": "1.0",
        "history_snapshot_metadata": {
            "as_of_utc": "2026-06-25T12:00:00Z",
            "snapshot_size": 0,
            "snapshot_sha256": "dummy_history_sha"
        },
        "worker_contract_version": "1.0",
        "run_as_of_utc": "2026-06-25T12:00:00Z",
        "validated_inputs": {
            "s5_hash": sha256_file(s5_path),
            "history_hash": "a" * 64,
            "policy_hash": "b" * 64,
        },
        "input_candidate_count": len(bound_candidates),
        "accepted": [
            {
                "candidate_id": c["selection_id"],
                "selection_id": c["selection_id"],
                "decision": "ACCEPTED",
                "reason_codes": [],
                "explanation": "Passed all constraints",
                "original_candidate": c
            }
            for c in bound_candidates
        ],
        "repeat_rejected": [],
        "duplicate_rejected": [],
        "correlation_rejected": [],
        "conflict_rejected": [],
        "concentration_rejected": [],
        "invalid_input": [],
        "accounting": {
            "input_count": len(bound_candidates),
            "terminal_count": len(bound_candidates),
            "category_counts": {"accepted": len(bound_candidates)},
            "unaccounted_candidate_ids": [],
            "unexpected_candidate_ids": [],
            "duplicate_candidate_ids": [],
            "overlapping_terminal_categories": []
        }
    }
    s6_output_path.write_text(json.dumps(s6_output_data, indent=2), encoding="utf-8")
    
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
            "git_sha": repo_head_sha(repo_root),
            "manifest_sha": manifest_hash(repo_root),
            "policy_version": "1.0",
            "as_of_timestamp": "2026-06-25T12:00:00Z",
            "input_candidate_count": len(bound_candidates),
            "accepted_count": len(bound_candidates),
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
    (run_root / "artifacts" / "S6.json").write_text(json.dumps(s6_ev, indent=2), encoding="utf-8")


def test_s7_prefers_s4_valuation_output_and_no_missing_block():
    environ = _runtime_environ()
    data_dir = Path(environ["BET_PIPELINE_DATA_DIR"])
    valuation_path = data_dir / "2026-06-25_s4_valuation_candidates.json"
    _seed_prior_steps_for_s7(environ, valuation_path)
    s4_candidates = [
        {
            "candidate_id": "tennis|Alpha|Beta|2026-06-25",
            "fixture_id": 10,
            "sport": "tennis",
            "home_team": "Alpha",
            "away_team": "Beta",
            "competition": "Wimbledon",
            "best_market": {"name": "Match Winner", "market_family": "RESULT", "safety_score": 0.82},
            "market_count": 4,
            "odds": {},
            "odds_decimal": None,
            "ev": None,
            "model_probability": 0.58,
            "probability_confidence": "HIGH",
            "source_provider": "api-football",
            "source_artifact_path": str(valuation_path),
            "probability_as_of": "2026-06-25T12:00:00Z",
            "market_family": "RESULT",
            "market_type": "ml",
            "selection": "Alpha",
            "pick": "Alpha",
            "supporting_stats": [{"metric": "team_a_form", "value": {"goals": 1.5}}]
        }
    ]
    _write_json(
        valuation_path,
        {
            "artifact_type": "S4_VALUATION_CANDIDATE_SET_V2",
            "candidate_count": 1,
            "contains_odds": True,
            "contains_ev": True,
            "contains_safety": True,
            "contains_market_count": True,
            "source_input_path": str(data_dir / "2026-06-25_s3_deep_stats.json"),
            "candidates": s4_candidates,
        },
    )
    _write_s4_pass_evidence(environ, valuation_path)
    _seed_s5_and_s6_for_s7(environ, valuation_path, s4_candidates)

    recorded: dict[str, object] = {}

    def fake_run(cmd, env=None, capture_output=None, text=None):
        recorded["cmd"] = list(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    argv = ["s5_gate.py", "--date", "2026-06-25", "--run-id", environ["BET_PIPELINE_RUN_ID"], "--runtime-mode", "DRY_RUN", "--dry-run"]
    with patch.dict(os.environ, environ, clear=False), \
         patch.object(sys, "argv", argv), \
         patch("subprocess.run", side_effect=fake_run), \
         patch("bet.pipeline.hard_approval_gate.LiveFixtureAudit") as mock_class:
        mock_class.return_value.audit_candidate.return_value = ("LIVE_FIXTURE_VERIFIED_NOT_STARTED", "PASS")
        with pytest.raises(SystemExit) as exc_info:
            s5_gate.main()

    evidence_path = _canonical_evidence_path(environ, "S7")
    if evidence_path.exists():
        print("S7 EVIDENCE CONTENTS:", evidence_path.read_text())
    assert exc_info.value.code == 0
    evidence = json.loads(_canonical_evidence_path(environ, "S7").read_text(encoding="utf-8"))
    assert evidence["payload"]["s7_input_source_step"] == "S6"
    assert "BLOCKED_S7_S6_INPUT_MISSING" not in evidence.get("blocked_reasons", [])


def test_s8_reads_analytical_handoff_without_s7_approved_picks():
    environ = _runtime_environ()
    data_dir = Path(environ["BET_PIPELINE_DATA_DIR"])
    handoff_path = _write_json(
        data_dir / "analytical_candidate_handoff.json",
        {
            "artifact_type": "ANALYTICAL_CANDIDATE_HANDOFF",
            "analytical_ready": [],
            "blocked_probability_missing": [{"candidate_id": "fixture:10", "analytical_status": "INSUFFICIENT_MODEL_PROBABILITY"}],
            "blocked_stats_missing": [],
            "blocked_identity_missing": [],
            "priced_candidates": [],
            "counts": {"analytical_ready": 0, "blocked_probability_missing": 1, "blocked_stats_missing": 0, "blocked_identity_missing": 0, "priced_candidates": 0},
        },
    )

    argv = ["s8_build_coupons.py", "--date", "2026-06-25", "--run-id", environ["BET_PIPELINE_RUN_ID"], "--runtime-mode", "DRY_RUN", "--dry-run"]
    with patch.dict(os.environ, environ, clear=False), patch.object(sys, "argv", argv):
        with pytest.raises(SystemExit) as exc_info:
            s8_build_coupons.main()

    assert exc_info.value.code == 5
    evidence = json.loads(_canonical_evidence_path(environ, "S8").read_text(encoding="utf-8"))
    assert evidence["status"] == "BLOCK"
    assert evidence["blocked_reasons"] == ["BLOCKED_S8_CANONICAL_S7B_INVALID"]
    assert evidence["payload"]["ready_for_human_gate"] is False
    assert not (data_dir / "2026-06-25_s8_coupon_drafts.json").exists()


def test_s8_review_only_package_not_quote_ready():
    environ = _runtime_environ()
    data_dir = Path(environ["BET_PIPELINE_DATA_DIR"])
    _write_json(
        data_dir / "analytical_candidate_handoff.json",
        {
            "artifact_type": "ANALYTICAL_CANDIDATE_HANDOFF",
            "analytical_ready": [],
            "blocked_probability_missing": [],
            "blocked_stats_missing": [],
            "blocked_identity_missing": [],
            "review_only_partial_data": [
                {
                    "candidate_id": "fixture:11",
                    "hydration_status": "PARTIAL_HYDRATION",
                    "promotion_status": "REVIEW_ONLY_PARTIAL_DATA",
                    "promotion_safe_model_probability": False,
                    "ready_for_manual_operator_quote_review": False,
                }
            ],
            "research_gap_minimal_hydration": [],
            "priced_candidates": [],
            "counts": {
                "analytical_ready": 0,
                "blocked_probability_missing": 0,
                "blocked_stats_missing": 0,
                "blocked_identity_missing": 0,
                "review_only_partial_data": 1,
                "research_gap_minimal_hydration": 0,
                "priced_candidates": 0,
            },
        },
    )

    argv = ["s8_build_coupons.py", "--date", "2026-06-25", "--run-id", environ["BET_PIPELINE_RUN_ID"], "--runtime-mode", "DRY_RUN", "--dry-run"]
    with patch.dict(os.environ, environ, clear=False), patch.object(sys, "argv", argv):
        with pytest.raises(SystemExit) as exc_info:
            s8_build_coupons.main()

    assert exc_info.value.code == 5
    evidence = json.loads(_canonical_evidence_path(environ, "S8").read_text(encoding="utf-8"))
    assert evidence["status"] == "BLOCK"
    assert evidence["payload"]["ready_for_human_gate"] is False


def test_s7_resolution_prefers_s6_output_and_no_production_fallback():
    environ = _runtime_environ()
    environ["BET_PIPELINE_RUN_ROOT"] = str(Path("/tmp") / "analytical_candidate_bridge_resolution_case")
    environ["BET_PIPELINE_DATA_DIR"] = str(Path(environ["BET_PIPELINE_RUN_ROOT"]) / "data")
    environ["BET_PIPELINE_ARTIFACT_DIR"] = str(Path(environ["BET_PIPELINE_RUN_ROOT"]) / "artifacts")
    data_dir = Path(environ["BET_PIPELINE_DATA_DIR"])
    s3_path = _write_json(data_dir / "2026-06-25_s3_deep_stats.json", _input_payload())
    s4_path = _write_json(
        data_dir / "2026-06-25_s4_valuation_candidates.json",
        {
            "artifact_type": "S4_VALUATION_CANDIDATE_SET_V2",
            "source_input_path": str(s3_path),
            "candidates": [
                {
                    "candidate_id": "football|Alpha|Beta|2026-06-25",
                    "fixture_id": 10,
                    "sport": "football",
                    "home_team": "Alpha",
                    "away_team": "Beta",
                    "competition": "Test League",
                    "best_market": {"name": "Over 2.5", "safety_score": 0.82},
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
            ],
        },
    )
    _write_s4_pass_evidence(environ, s4_path)
    
    # We must seed S5 and S6 for S7 to resolve S6 path!
    _seed_s5_and_s6_for_s7(environ, s4_path, [
        {
            "candidate_id": "football|Alpha|Beta|2026-06-25",
            "fixture_id": 10,
            "sport": "football",
            "home_team": "Alpha",
            "away_team": "Beta",
            "competition": "Test League",
            "best_market": {"name": "Over 2.5", "safety_score": 0.82},
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
    ])

    resolution = s5_gate.resolve_s7_input(environ, "2026-06-25", environ["BET_PIPELINE_RUN_ID"])

    assert Path(resolution["path"]).resolve() == (Path(environ["BET_PIPELINE_RUN_ROOT"]) / "data" / "repeat_loss_handoff_2026-06-25.json").resolve()
    assert resolution["source_step"] == "S6"
