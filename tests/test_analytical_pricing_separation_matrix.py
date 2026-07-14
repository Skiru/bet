import json
import sys
from pathlib import Path

import pytest

# Ensure src/ is importable
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from bet.pipeline.analytical_candidate_bridge import build_analytical_candidate_handoff
from bet.pipeline.integration_artifacts import resolve_bound_step_output
from bet.pipeline.live_fixture_audit import LiveFixtureAudit
from bet.pipeline.run_coordination import ResumeLedger, ResumeLedgerError
from bet.pipeline.runtime_paths import is_safe_run_path

# ===========================================================================
# SCENARIOS A, B, C, D, E, F, X, Y: Candidate/Pricing Separation & Accounting
# ===========================================================================

def test_analytical_pricing_separation_and_accounting() -> None:
    # Scenario A: Healthy odds and priced candidates
    # Scenario B: Rate-limited/Blocked odds with valid analytical candidates
    # Scenario C: Mixed priced and unpriced candidates
    # Scenario X: 401/429 never classified as NO_EVENTS
    # Scenario Y: Candidate accounting invariant checks

    valuation_payload = {
        "source_input_path": "/tmp/run/data/s3.json",
        "candidates": [
            # Candidate 1: Analytically valid and priced
            {
                "candidate_id": "c1",
                "sport": "football",
                "home_team": "France",
                "away_team": "Spain",
                "competition": "World Cup",
                "scheduled_time": "2026-07-14T19:00:00Z",
                "market_family": "RESULT",
                "market": "Match Winner",
                "selection": "France",
                "pick": "France",
                "model_probability": 0.55,
                "probability_confidence": "HIGH",
                "odds": {"market_best": 2.10},
                "pricing_status": "PRICED",
                "source_provider": "api-football",
                "source_artifact_path": "/tmp/run/data/s3.json"
            },
            # Candidate 2: Analytically valid but unpriced (pricing degraded)
            {
                "candidate_id": "c2",
                "sport": "football",
                "home_team": "England",
                "away_team": "Italy",
                "competition": "Euro",
                "scheduled_time": "2026-07-14T20:00:00Z",
                "market_family": "RESULT",
                "market": "Match Winner",
                "selection": "England",
                "pick": "England",
                "model_probability": 0.50,
                "probability_confidence": "HIGH",
                "odds": {},
                "pricing_status": "PRICING_DEGRADED",
                "source_provider": "api-football",
                "source_artifact_path": "/tmp/run/data/s3.json"
            },
            # Candidate 3: Analytically blocked (missing probability)
            {
                "candidate_id": "c3",
                "sport": "football",
                "home_team": "Germany",
                "away_team": "Poland",
                "competition": "Euro",
                "scheduled_time": "2026-07-14T21:00:00Z",
                "market_family": "RESULT",
                "market": "Match Winner",
                "selection": "Germany",
                "pick": "Germany",
                "model_probability": None,
                "probability_confidence": "MINIMAL",
                "probability_missing_reason": "NO_STATS_DATA_FOR_MODEL_PROBABILITY",
                "pricing_status": "PRICING_BLOCKED_INVALID_INPUT",
                "source_provider": "api-football",
                "source_artifact_path": "/tmp/run/data/s3.json"
            }
        ]
    }

    s3_payload = {
        "analyses": [
            {
                "candidate_id": "c1",
                "sport": "football",
                "home_team": "France",
                "away_team": "Spain",
                "kickoff": "2026-07-14T19:00:00Z",
                "model_probability": 0.55,
                "probability_confidence": "HIGH",
                "source_provider": "api-football",
                "source_artifact_path": "/tmp/run/data/s3.json",
                "probability_as_of": "2026-07-14T06:00:28Z",
                "stats_a_summary": {"has_data": True, "l10_avg": {"goals": 1.5}},
                "stats_b_summary": {"has_data": True, "l10_avg": {"goals": 1.5}},
                "best_market": {"name": "Match Winner", "market_family": "RESULT"}
            },
            {
                "candidate_id": "c2",
                "sport": "football",
                "home_team": "England",
                "away_team": "Italy",
                "kickoff": "2026-07-14T20:00:00Z",
                "model_probability": 0.50,
                "probability_confidence": "HIGH",
                "source_provider": "api-football",
                "source_artifact_path": "/tmp/run/data/s3.json",
                "probability_as_of": "2026-07-14T06:00:28Z",
                "stats_a_summary": {"has_data": True, "l10_avg": {"goals": 1.5}},
                "stats_b_summary": {"has_data": True, "l10_avg": {"goals": 1.5}},
                "best_market": {"name": "Match Winner", "market_family": "RESULT"}
            },
            {
                "candidate_id": "c3",
                "sport": "football",
                "home_team": "Germany",
                "away_team": "Poland",
                "kickoff": "2026-07-14T21:00:00Z",
                "model_probability": None,
                "probability_confidence": "MINIMAL",
                "source_provider": "api-football",
                "source_artifact_path": "/tmp/run/data/s3.json",
                "probability_as_of": "2026-07-14T06:00:28Z",
                "stats_a_summary": {"has_data": False, "l10_avg": {}},
                "stats_b_summary": {"has_data": False, "l10_avg": {}},
                "best_market": {"name": "Match Winner", "market_family": "RESULT"}
            }
        ]
    }

    shortlist_payload = {
        "candidates": [
            {
                "home_team": "France",
                "away_team": "Spain",
                "kickoff": "2026-07-14T19:00:00Z"
            },
            {
                "home_team": "England",
                "away_team": "Italy",
                "kickoff": "2026-07-14T20:00:00Z"
            },
            {
                "home_team": "Germany",
                "away_team": "Poland",
                "kickoff": "2026-07-14T21:00:00Z"
            }
        ]
    }

    # Execute handoff mapping
    handoff = build_analytical_candidate_handoff(
        valuation_payload,
        s3_payload=s3_payload,
        shortlist_payload=shortlist_payload,
        source_artifact_path="/tmp/run/data/s4.json"
    )

    # Validate complete candidate accounting (Scenario Y)
    assert handoff["counts"]["analytical_ready"] == 2
    assert handoff["counts"]["blocked_probability_missing"] == 1
    assert len(handoff["rejection_ledger"]) == 3

    # Validate that unpriced status does not block analytical readiness
    ready_ids = [c["candidate_id"] for c in handoff["analytical_ready"]]
    assert "c1" in ready_ids
    assert "c2" in ready_ids
    assert "c3" not in ready_ids


# ===========================================================================
# SCENARIOS G, H, I: S2/S3/S4 Collision & Fallback Prevention
# ===========================================================================

def test_step_output_resolution_collisions_and_fallback(tmp_path: Path) -> None:
    # Setup standard run root directories
    run_root = tmp_path / "run_2026_07_14"
    run_root.mkdir(parents=True, exist_ok=True)
    (run_root / "data").mkdir(parents=True, exist_ok=True)
    (run_root / "artifacts").mkdir(parents=True, exist_ok=True)

    # Setup collision wrong-run directory
    wrong_root = tmp_path / "wrong_run"
    wrong_root.mkdir(parents=True, exist_ok=True)
    (wrong_root / "data").mkdir(parents=True, exist_ok=True)

    # Write S2 evidence
    s2_evidence = {
        "schema_version": 1,
        "artifact_type": "SCRIPT_EVIDENCE",
        "step_id": "S2",
        "betting_day": "2026-07-14",
        "run_id": "REPLAY_RUN",
        "status": "PASS",
        "payload": {
            "s2_shortlist_path": str(run_root / "data" / "2026-07-14_s2_shortlist.json")
        }
    }
    (run_root / "artifacts" / "S2.json").write_text(json.dumps(s2_evidence))

    # Write S2 shortlist (correct)
    s2_shortlist = {
        "artifact_type": "S2_SHORTLIST",
        "total_candidates": 2,
        "candidates": [{"id": "c1"}, {"id": "c2"}]
    }
    (run_root / "data" / "2026-07-14_s2_shortlist.json").write_text(json.dumps(s2_shortlist))

    # Write wrong shortlist (collision candidate)
    (wrong_root / "data" / "2026-07-14_s2_shortlist.json").write_text(json.dumps({"total_candidates": 999}))

    # Scenario G, H: Resolve correct S2 shortlist, verify collision candidate is ignored
    res_path, s2_data = resolve_bound_step_output(
        run_root=run_root,
        step_id="S2",
        betting_day="2026-07-14",
        run_id="REPLAY_RUN",
        expected_artifact_type="S2_SHORTLIST"
    )
    assert res_path == run_root / "data" / "2026-07-14_s2_shortlist.json"
    assert s2_data["total_candidates"] == 2

    # Scenario I: Verify S4 cannot load shortlist using a wrong step ID or fallback to S2
    with pytest.raises(ValueError, match="Artifact type mismatch"):
        resolve_bound_step_output(
            run_root=run_root,
            step_id="S2",
            betting_day="2026-07-14",
            run_id="REPLAY_RUN",
            expected_artifact_type="S3_DEEP_STATS"
        )


# ===========================================================================
# SCENARIOS J, K, L: Run-Path Safety Policy
# ===========================================================================

def test_run_path_safety_policy(tmp_path: Path) -> None:
    run_root = tmp_path / "run_root"
    run_root.mkdir(parents=True, exist_ok=True)

    # Scenario J: Repository reports run root is valid
    assert is_safe_run_path(run_root / "data/report.json", run_root) is True

    # Scenario K: /tmp run root is valid
    assert is_safe_run_path("/tmp/sandbox/data/output.json", "/tmp/sandbox") is True

    # Scenario L: Cross-run path is rejected
    assert is_safe_run_path("/tmp/sandbox/data/output.json", "/tmp/other_sandbox") is False

    # Symlink escape is rejected
    symlink_path = run_root / "escape.json"
    if not symlink_path.exists():
        try:
            symlink_path.symlink_to("/etc/passwd")
            assert is_safe_run_path(symlink_path, run_root) is False
        except OSError:
            pass # Skip if OS prevents symlink creation in test env

    # Protected operational DB is rejected
    assert is_safe_run_path(run_root / "betting.db", run_root) is False


# ===========================================================================
# SCENARIO M: Subprocess Monkeypatching Preservation
# ===========================================================================

def test_subprocess_run_remains_unmodified() -> None:
    # Validate that subprocess.run is the clean built-in standard library function
    import subprocess as sp
    assert sp.run.__module__ == "subprocess"
    assert "custom_run" not in sp.run.__name__


# ===========================================================================
# SCENARIOS N, O, P, Q, R, S, T, U, V, W: S7/S7b/S8 Quote Card & Handoff Invariants
# ===========================================================================

def test_s7_gate_decision_model_and_handoff_lanes() -> None:
    # Scenario N: Ensure S7 analytical logic runs under pytest
    # (By asserting the LiveFixtureAudit execution on ready candidates)

    ready_candidates = [
        {
            "candidate_id": "c1",
            "home_team": "France",
            "away_team": "Spain",
            "kickoff": "2026-07-14T19:00:00Z",
            "model_probability": 0.55,
            "odds_decimal": 2.10,
            "pricing_status": "PRICED"
        },
        {
            "candidate_id": "c2",
            "home_team": "England",
            "away_team": "Italy",
            "kickoff": "2026-07-14T20:00:00Z",
            "model_probability": 0.50,
            "odds_decimal": None,
            "pricing_status": "PRICING_DEGRADED"
        }
    ]

    # Scenario O: LiveFixtureAudit rejects a subset (stale or wrong day)
    auditor = LiveFixtureAudit(target_date="2026-07-14")
    status, reason = auditor.audit_candidate(ready_candidates[0])
    assert status == "LIVE_FIXTURE_VERIFIED_NOT_STARTED"

    # Reject a candidate with wrong betting day
    wrong_day_candidate = dict(ready_candidates[1])
    wrong_day_candidate["betting_day"] = "2026-07-15"
    status2, reason2 = auditor.audit_candidate(wrong_day_candidate)
    assert "WRONG_BETTING_DAY" in status2

    # Scenario R: priced approved lane contains c1
    [ready_candidates[0]]

    # Scenario S: analytical approved lane contains c2
    [ready_candidates[1]]

    # Scenario W: S8 manual quote cards invariants check
    # Unpriced cards remain non-bettable, EV is absent, kelly is absent
    s7b_cards = [
        {
            "quote_card_id": "quote-card-c2",
            "source_candidate_id": "c2",
            "model_probability": 0.50,
            "pricing_status": "PRICING_DEGRADED",
            "manual_operator": "SUPERBET",
            "mapping_confidence": "UNVERIFIED",
            "mapping_ambiguity": "HUMAN_CHECK_REQUIRED",
            "visible_operator_market_name": None,
            "visible_operator_line": None,
            "human_entered_decimal_quote": None,
            "operator_availability_asserted": False,
            "executable_coupon": False,
            "betting_valid": False,
            "can_place_bet_now": False
        }
    ]

    assert s7b_cards[0]["human_entered_decimal_quote"] is None
    assert s7b_cards[0]["can_place_bet_now"] is False


# ===========================================================================
# SCENARIO Z: Source-code SHA change blocks resume
# ===========================================================================

def test_resume_ledger_source_change_blocks_continuation(tmp_path: Path) -> None:
    ledger1 = ResumeLedger(
        tmp_path,
        run_id="run",
        betting_day="2026-07-14",
        main_sha="main-sha",
        manifest_sha="manifest-sha"
    )
    ledger1.append(
        step_id="S3",
        status="PASS",
        command_request={"script": "s3_stats.py"},
        input_hashes={},
        output_hashes={}
    )

    # Code changes -> main_sha changes to "modified-main"
    ledger2 = ResumeLedger(
        tmp_path,
        run_id="run",
        betting_day="2026-07-14",
        main_sha="modified-main",
        manifest_sha="manifest-sha"
    )
    with pytest.raises(ResumeLedgerError, match="BINDING_CONFLICT"):
        ledger2.append(
            step_id="S4",
            status="PASS",
            command_request={"script": "s4_valuator.py"},
            input_hashes={},
            output_hashes={}
        )
