"""Focused script evidence and domain validation tests for S6 repeats."""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from bet.pipeline.canonical_continuity import bind_candidate_identity
from bet.pipeline.portfolio_repeat_guard import (
    HistorySnapshot,
    PortfolioPolicy,
    PortfolioRepeatGuardInput,
    evaluate_portfolio_repeat_guard,
)
from bet.pipeline.run_evidence import manifest_hash, repo_head_sha, sha256_file
from scripts.check_48h_repeats import HistoryMalformedError, load_recent_losses_snapshot
from scripts.pipeline_steps import s6_repeats

ROOT = Path(__file__).resolve().parents[1]


def _runtime_environ(tmp_path: Path) -> dict[str, str]:
    run_root = tmp_path / "run_root"
    run_root.mkdir(parents=True, exist_ok=True)
    return {
        "BET_PIPELINE_RUNTIME_MODE": "DRY_RUN",
        "BET_PIPELINE_BETTING_DAY": "2026-07-14",
        "BET_PIPELINE_RUN_ID": "run-s6-evidence-test",
        "BET_PIPELINE_RUN_ROOT": str(run_root),
        "BET_PIPELINE_DATA_DIR": str(run_root / "data"),
        "BET_PIPELINE_COUPON_DIR": str(run_root / "coupons"),
        "BET_PIPELINE_ARTIFACT_DIR": str(run_root / "artifacts"),
        "BET_PIPELINE_RUN_AS_OF_UTC": "2026-07-15T12:00:00Z",
    }


def _canonical_evidence_path(environ: dict[str, str]) -> Path:
    # Single canonical evidence path at <run_root>/artifacts/S6.json
    return Path(environ["BET_PIPELINE_RUN_ROOT"]) / "artifacts" / "S6.json"


@pytest.fixture
def mock_s5_data(tmp_path):
    run_root = tmp_path / "run_root"
    artifacts_dir = run_root / "artifacts"
    data_dir = run_root / "data"
    for d in (artifacts_dir, data_dir):
        d.mkdir(parents=True, exist_ok=True)

    # 1. Write S4 Candidates JSON
    s4_path = data_dir / "2026-07-14_s4_valuation_candidates.json"
    candidates = [
        bind_candidate_identity(candidate)
        for candidate in [
            {
                "home_team": "France",
                "away_team": "Spain",
                "kickoff": "2026-07-14T20:00:00Z",
                "best_market": {"name": "Match Winner", "selection": "France"},
                "sport": "football",
                "competition": "World Cup",
                "safety_score": 0.85,
                "analytical_status": "ANALYTICAL_READY",
                "pricing_status": "PRICED",
                "odds_decimal": 1.95,
                "odds_source": "Superbet",
                "odds_as_of": "2026-07-14T12:00:00Z",
            },
            {
                "home_team": "Italy",
                "away_team": "Germany",
                "kickoff": "2026-07-14T21:00:00Z",
                "best_market": {"name": "Match Winner", "selection": "Italy"},
                "sport": "football",
                "competition": "World Cup",
                "safety_score": 0.85,
                "analytical_status": "ANALYTICAL_READY",
                "pricing_status": "PRICED",
                "odds_decimal": 1.95,
                "odds_source": "Superbet",
                "odds_as_of": "2026-07-14T12:00:00Z",
            },
        ]
    ]
    s4_content = {
        "schema_version": 2,
        "artifact_type": "S4_VALUATION_CANDIDATE_SET_V2",
        "status": "PASS",
        "betting_day": "2026-07-14",
        "run_id": "run-s6-evidence-test",
        "candidates": candidates,
    }
    s4_path.write_text(json.dumps(s4_content))

    s4_sha = sha256_file(s4_path)

    # 2. Write S4 Evidence
    s4_evidence_path = artifacts_dir / "S4.json"
    s4_evidence = {
        "artifact_type": "SCRIPT_EVIDENCE",
        "step_id": "S4",
        "status": "PASS",
        "betting_day": "2026-07-14",
        "run_id": "run-s6-evidence-test",
        "payload": {
            "s4_valuation_output_path": str(s4_path),
            "s4_valuation_output_sha256": s4_sha
        }
    }
    s4_evidence_path.write_text(json.dumps(s4_evidence))

    # 3. Write S5 Evidence (Prerequisite for S6 wrapper)
    s5_path = artifacts_dir / "S5.json"
    context = {
        name: {
            "status": "CLEAR",
            "as_of_utc": "2026-07-14T12:00:00Z",
            "source_refs": [f"source:{name}"],
        }
        for name in (
            "injuries_lineups",
            "motivation_tournament_context",
            "travel_fatigue",
            "morale_recent_form",
            "upset_volatility_risk",
        )
    }
    s5_candidates = json.loads(json.dumps(candidates))
    for candidate in s5_candidates:
        candidate["context_checks"] = context
        candidate["risk_flags"] = []
        candidate["counter_evidence"] = []
    s5_content = {
        "schema_version": 1,
        "artifact_type": "AGENT_ARTIFACT",
        "step_id": "S5",
        "status": "PASS",
        "betting_day": "2026-07-14",
        "run_id": "run-s6-evidence-test",
        "source_bound": True,
        "no_pick_edge_stake_coupon_emitted": True,
        "production_selectable": False,
        "betting_decisions_enabled": False,
        "payload": {
            "work_order_id": "WO-run-s6-evidence-test-S5",
            "agent_id": "bet-risk-gatekeeper",
            "source_git_sha": repo_head_sha(ROOT),
            "manifest_sha": manifest_hash(ROOT),
            "source_s4_path": str(s4_path),
            "source_s4_sha256": s4_sha,
            "policy_version": "S5_CONTEXT_RISK_V2",
            "input_candidate_count": 2,
            "candidates": s5_candidates,
            "rejected_candidates": [],
            "accounting": {
                "unaccounted_candidate_ids": [],
                "duplicate_candidate_ids": [],
                "overlapping_terminal_categories": [],
            },
        }
    }
    s5_path.write_text(json.dumps(s5_content))
    return s5_path


@pytest.fixture
def mock_policy(tmp_path):
    # Ensure portfolio_policy.json is present in the workspace/test sandbox
    policy_path = ROOT / "config" / "portfolio_policy.json"
    policy_path.parent.mkdir(parents=True, exist_ok=True)
    policy_data = {
        "schema_version": 1,
        "policy_version": "1.0",
        "repeat_loss_lookback_hours": 48,
        "duplicate_signal_enabled": True,
        "same_event_conflict_enabled": True,
        "correlation_group_limit_enabled": True,
        "correlation_group_max_accepted": 3,
        "concentration_enabled": True,
        "per_event_limit": 2,
        "per_team_limit": 2,
        "per_competition_limit": 4,
        "per_sport_limit": 8
    }
    policy_path.write_text(json.dumps(policy_data, indent=2))
    return policy_path


@pytest.fixture
def mock_ledger(tmp_path):
    run_root = tmp_path / "run_root"
    run_root.mkdir(parents=True, exist_ok=True)
    ledger_path = run_root / "picks-ledger.csv"

    # Write canonical picks-ledger CSV
    header = ["betting_day", "pick_id", "event", "sport", "market", "selection", "status", "settled_at_utc"]
    rows = [
        # Loss within lookback window for France vs Spain
        ["2026-07-13", "P-001", "France vs Spain", "football", "Match Winner", "France", "loss", "2026-07-13T18:00:00Z"],
        # Win (should be ignored) for Italy vs Germany
        ["2026-07-13", "P-002", "Italy vs Germany", "football", "Match Winner", "Italy", "win", "2026-07-13T19:00:00Z"]
    ]
    import csv
    with open(ledger_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)
    return ledger_path


def test_s6_missing_input_blocks_with_correct_evidence(tmp_path: Path):
    environ = _runtime_environ(tmp_path)
    argv = [
        "s6_repeats.py",
        "--date",
        "2026-07-14",
        "--run-id",
        environ["BET_PIPELINE_RUN_ID"],
        "--runtime-mode",
        "DRY_RUN",
    ]

    with patch.dict(os.environ, environ, clear=False), patch.object(sys, "argv", argv):
        with pytest.raises(SystemExit) as exc_info:
            s6_repeats.main()

    assert exc_info.value.code == 5
    evidence_path = _canonical_evidence_path(environ)
    assert evidence_path.exists()
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert evidence["status"] == "BLOCK"
    assert "BLOCKED_REPEAT_GUARD_INPUT_MISSING" in evidence["blocked_reasons"]


def test_s6_success_workflow(tmp_path: Path, mock_s5_data, mock_policy, mock_ledger):
    """Positive test for standard S6 repeats workflow."""
    environ = _runtime_environ(tmp_path)
    environ["BET_PIPELINE_LEDGER_PATH"] = str(mock_ledger)

    argv = [
        "s6_repeats.py",
        "--date",
        "2026-07-14",
        "--run-id",
        environ["BET_PIPELINE_RUN_ID"],
        "--runtime-mode",
        "DRY_RUN",
    ]

    with patch.dict(os.environ, environ, clear=False), patch.object(sys, "argv", argv):
        with pytest.raises(SystemExit) as exc_info:
            s6_repeats.main()

    # If it executes correctly and completes
    assert exc_info.value.code == 0
    evidence_path = _canonical_evidence_path(environ)
    assert evidence_path.exists()

    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert evidence["status"] == "PASS"
    payload = evidence["payload"]
    assert payload["accepted_count"] == 1
    assert payload["repeat_rejected_count"] == 1


def test_temporal_half_open_limits(mock_ledger):
    """Verify standard lookback bounds and half-open inclusive start: [as_of - 48h, as_of)."""
    # 1. 47:59:59 lookback (inclusive loss)
    as_of = datetime.fromisoformat("2026-07-15T17:59:59Z")
    snapshot = load_recent_losses_snapshot(mock_ledger, hours=48, as_of=as_of)
    assert snapshot["row_count"] == 1
    assert snapshot["records"][0]["pick_id"] == "P-001"

    # 2. Exact 48:00:00 lookback is the inclusive start of [start, as_of).
    as_of_exact = datetime.fromisoformat("2026-07-15T18:00:00Z")
    snapshot_exact = load_recent_losses_snapshot(mock_ledger, hours=48, as_of=as_of_exact)
    assert snapshot_exact["row_count"] == 1


def test_missing_timestamp_blocks(tmp_path):
    """Negative test: missing timestamp in history row blocks S6."""
    ledger_path = tmp_path / "broken-ledger.csv"
    header = ["betting_day", "pick_id", "event", "sport", "market", "selection", "status", "settled_at_utc"]
    rows = [
        ["2026-07-13", "P-001", "France vs Spain", "football", "Match Winner", "France", "loss", ""]
    ]
    import csv
    with open(ledger_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)

    with pytest.raises(HistoryMalformedError, match="HISTORY_TIMESTAMP_MISSING"):
        load_recent_losses_snapshot(
            ledger_path,
            hours=48,
            as_of=datetime.fromisoformat("2026-07-14T12:00:00Z"),
        )


def test_invalid_timestamp_blocks(tmp_path):
    """Negative test: invalid/malformed timestamp in history row blocks S6."""
    ledger_path = tmp_path / "broken-ledger.csv"
    header = ["betting_day", "pick_id", "event", "sport", "market", "selection", "status", "settled_at_utc"]
    rows = [
        ["2026-07-13", "P-001", "France vs Spain", "football", "Match Winner", "France", "loss", "not-a-timestamp"]
    ]
    import csv
    with open(ledger_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)

    with pytest.raises(HistoryMalformedError, match="HISTORY_TIMESTAMP_INVALID"):
        load_recent_losses_snapshot(
            ledger_path,
            hours=48,
            as_of=datetime.fromisoformat("2026-07-14T12:00:00Z"),
        )


def test_complete_disjoint_partition_contract():
    """Verify that portfolio repeat guard partitions candidates completely and pairwise-disjointly."""
    candidates = [
        {
            "candidate_id": "football|A|B|2026-07-14",
            "home_team": "Team A",
            "away_team": "Team B",
            "best_market": {"name": "Match Winner", "selection": "1"},
            "sport": "football",
            "competition": "Liga 1",
            "safety_score": 0.85
        },
        {
            "candidate_id": "football|C|D|2026-07-14",
            "home_team": "Team C",
            "away_team": "Team D",
            "best_market": {"name": "Match Winner", "selection": "1"},
            "sport": "football",
            "competition": "La Liga",
            "safety_score": 0.85
        }
    ]

    policy = PortfolioPolicy(
        schema_version=1,
        policy_version="1.0",
        repeat_loss_lookback_hours=48,
        duplicate_signal_enabled=True,
        same_event_conflict_enabled=True,
        correlation_group_limit_enabled=True,
        correlation_group_max_accepted=3,
        concentration_enabled=True,
        per_event_limit=2,
        per_team_limit=2,
        per_competition_limit=4,
        per_sport_limit=8,
        policy_sha256="dummy_policy_sha"
    )

    history = HistorySnapshot(
        schema_version=1,
        artifact_type="S6_HISTORY_SNAPSHOT_V1",
        as_of_utc="2026-07-14T12:00:00Z",
        lookback_start_utc="2026-07-12T12:00:00Z",
        boundary_policy="half_open",
        source_identity="picks-ledger.csv",
        opened_read_only=True,
        query_version="1.0",
        policy_version="1.0",
        records=[],
        row_count=0,
        snapshot_sha256="dummy_history_sha"
    )

    guard_input = PortfolioRepeatGuardInput(
        candidates=candidates,
        history_snapshot=history,
        policy=policy,
        betting_day="2026-07-14",
        run_id="REPLAY_RUN",
        source_s5_hash="dummy_s5_hash"
    )

    res = evaluate_portfolio_repeat_guard(guard_input)

    # 1. Verification of disjoint categories:
    all_categories = [
        res.accepted,
        res.repeat_rejected,
        res.duplicate_rejected,
        res.conflict_rejected,
        res.correlation_rejected,
        res.concentration_rejected,
        res.invalid_input
    ]

    category_id_sets = []
    for cat in all_categories:
        cids = [item["candidate_id"] for item in cat]
        category_id_sets.append(set(cids))

    # Pairwise disjoint: intersection between any two is empty
    for i in range(len(category_id_sets)):
        for j in range(i + 1, len(category_id_sets)):
            assert category_id_sets[i] & category_id_sets[j] == set()

    # Union is equal to input
    all_assigned_ids = set()
    for s in category_id_sets:
        all_assigned_ids |= s

    input_ids = {c["candidate_id"] for c in candidates}
    assert all_assigned_ids == input_ids
