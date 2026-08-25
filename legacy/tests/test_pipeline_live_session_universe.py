"""Unit and integration tests for Live Session Candidate Universe Gate."""
from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Any
import pytest
from scripts.pipeline_steps import s5_gate

from bet.pipeline.live_session_universe import (
    LiveSessionUniverseConfig,
    CandidateInput,
    build_s7_traceability_fields,
    classify_candidate_quality,
    classify_wiring_fault,
    build_pre_s7_universe,
)

def _candidate(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    # Default valid future candidate
    future_time = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat().replace("+00:00", "Z")
    base = {
        "candidate_id": "cand-valid-1",
        "event_id": "event-100",
        "event": "Team A vs Team B",
        "sport": "football",
        "competition": "Champions League",
        "kickoff": future_time,
        "market": "Over 2.5",
        "pick": "OVER",
        "line": "2.5",
        "odds_decimal": 1.95,
        "odds_captured_at_utc": "2026-06-28T12:00:00Z",
        "operator_name": "Betclic",
        "is_live": False,
        "supporting_stats": [
            {"metric": "Form", "value": "Good", "source": "ESPN", "as_of": "2026-06-28"},
            {"metric": "Injuries", "value": "None", "source": "SofaScore", "as_of": "2026-06-28"},
            {"metric": "Tipster consensus", "value": "Sufficient", "source": "Blogabet", "as_of": "2026-06-28"},
        ],
        "counter_stats": [
            {"metric": "H2H matches", "value": "5", "source": "Flashscore", "as_of": "2026-06-28"},
            {"metric": "Exact Stat-specific H2H", "value": "Yes", "source": "Flashscore", "as_of": "2026-06-28"},
        ],
    }
    if overrides:
        base.update(overrides)
    return base

def test_valid_future_candidate_passes():
    config = LiveSessionUniverseConfig()
    cand = CandidateInput.from_dict(_candidate())
    res = classify_candidate_quality(cand, config)
    assert res.is_valid is True
    assert res.verdict == "VALID"
    assert len(res.source_gaps) == 0

def test_stale_non_live_rejected():
    config = LiveSessionUniverseConfig()
    past_time = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat().replace("+00:00", "Z")
    cand = CandidateInput.from_dict(_candidate({"kickoff": past_time, "is_live": False}))
    res = classify_candidate_quality(cand, config)
    assert res.is_valid is False
    assert res.verdict == "REJECTED_STALE"

def test_live_in_progress_allowed():
    config = LiveSessionUniverseConfig()
    past_time = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat().replace("+00:00", "Z")
    cand = CandidateInput.from_dict(_candidate({"kickoff": past_time, "is_live": True}))
    res = classify_candidate_quality(cand, config)
    assert res.is_valid is True
    assert res.verdict == "VALID"

def test_empty_sport_competition_rejected():
    config = LiveSessionUniverseConfig()
    cand_no_sport = CandidateInput.from_dict(_candidate({"sport": ""}))
    res_no_sport = classify_candidate_quality(cand_no_sport, config)
    assert res_no_sport.is_valid is False
    assert res_no_sport.verdict == "REJECTED_MISSING_SPORT"

    cand_no_comp = CandidateInput.from_dict(_candidate({"competition": ""}))
    res_no_comp = classify_candidate_quality(cand_no_comp, config)
    assert res_no_comp.is_valid is False
    assert res_no_comp.verdict == "REJECTED_MISSING_COMPETITION"


def test_missing_sport_reports_source_field_path():
    config = LiveSessionUniverseConfig(min_candidates=1)
    report = build_pre_s7_universe(
        [_candidate({"candidate_id": "cand-missing-sport", "sport": ""})],
        config,
        source_artifact_path="/tmp/2026-06-29_s4_valuation_candidates.json",
    )

    assert report.rejected_reasons["REJECTED_MISSING_SPORT"] == 1
    rejected = report.rejected_candidates[0]
    assert rejected["rejection_source_artifact_path"] == "/tmp/2026-06-29_s4_valuation_candidates.json"
    assert rejected["rejection_field_path"] == "candidates[0].sport"

def test_missing_line_for_ou_rejected():
    config = LiveSessionUniverseConfig()
    cand = CandidateInput.from_dict(_candidate({"market": "Over 2.5", "line": "MISSING"}))
    res = classify_candidate_quality(cand, config)
    assert res.is_valid is False
    assert res.verdict == "REJECTED_MISSING_LINE"


def test_top_level_market_type_is_accepted_for_pre_s7_market_handoff():
    config = LiveSessionUniverseConfig(min_candidates=1)
    report = build_pre_s7_universe(
        [
            _candidate(
                {
                    "candidate_id": "cand-market-type",
                    "market": "",
                    "market_type": "ml",
                    "market_label": "ml:away",
                    "market_family": "RESULT",
                    "selection": "Team B",
                    "pick": "Team B",
                }
            )
        ],
        config,
        source_artifact_path="/tmp/2026-06-29_s4_valuation_candidates.json",
    )

    assert report.valid_count == 1
    assert report.rejected_count == 0

def test_missing_odds_timestamp_rejected():
    config = LiveSessionUniverseConfig()
    cand = CandidateInput.from_dict(_candidate({"odds_captured_at_utc": ""}))
    res = classify_candidate_quality(cand, config)
    assert res.is_valid is False
    assert res.verdict == "REJECTED_MISSING_TIMESTAMP"

def test_source_gaps_classified():
    config = LiveSessionUniverseConfig()
    # Candidate with empty/placeholder stats
    cand_raw = _candidate({
        "supporting_stats": [{"metric": "Form", "value": "UNKNOWN", "source": "UNKNOWN", "as_of": "UNKNOWN"}],
        "counter_stats": [{"metric": "H2H", "value": "UNKNOWN", "source": "UNKNOWN", "as_of": "UNKNOWN"}],
    })
    cand = CandidateInput.from_dict(cand_raw)
    res = classify_candidate_quality(cand, config)
    assert res.is_valid is True
    assert len(res.source_gaps) > 0
    gap_types = [g.gap_type for g in res.source_gaps]
    assert "H2H" in gap_types
    assert "INJURY" in gap_types
    assert "TIPSTER" in gap_types

def test_insufficient_candidate_universe():
    config = LiveSessionUniverseConfig(min_candidates=8)
    raw_list = [_candidate({"candidate_id": f"cand-{i}"}) for i in range(2)]
    report = build_pre_s7_universe(raw_list, config)
    assert report.status == "BLOCKED_INSUFFICIENT_CANDIDATE_UNIVERSE"
    assert report.valid_count == 2
    assert report.total_input_count == 2

def test_sufficient_universe_allows_s7():
    config = LiveSessionUniverseConfig(min_candidates=8)
    raw_list = [_candidate({"candidate_id": f"cand-{i}"}) for i in range(8)]
    report = build_pre_s7_universe(raw_list, config)
    assert report.status == "READY_FOR_S7"
    assert report.valid_count == 8

def test_provider_exhausted_path():
    config = LiveSessionUniverseConfig(min_candidates=8, provider_universe_exhausted=True)
    raw_list = [_candidate({"candidate_id": f"cand-{i}"}) for i in range(5)]
    report = build_pre_s7_universe(raw_list, config)
    assert report.status == "BLOCKED_PROVIDER_UNIVERSE_EXHAUSTED"
    assert report.valid_count == 5


def test_s7_traceability_reports_same_count_without_selection_limit(tmp_path: Path):
    config = LiveSessionUniverseConfig(min_candidates=2)
    raw_list = [_candidate({"candidate_id": f"cand-{i}"}) for i in range(2)]
    report = build_pre_s7_universe(raw_list, config)
    report_path = tmp_path / "2026-06-28_pre_s7_universe_report.json"

    fields = build_s7_traceability_fields(
        report,
        report_path=report_path,
        input_path=tmp_path / "2026-06-28_s4_valuation_candidates.json",
        selection_policy="none",
    )

    assert fields["pre_s7_valid_count"] == 2
    assert fields["s7_input_count"] == 2
    assert fields["s7_selection_policy"] == "none"
    assert fields["s7_selection_reason"] == "N/A"


def test_top_n_selection_requires_explicit_reason_and_source_path(tmp_path: Path):
    config = LiveSessionUniverseConfig(min_candidates=2)
    raw_list = [_candidate({"candidate_id": f"cand-{i}"}) for i in range(2)]
    report = build_pre_s7_universe(raw_list, config)
    report_path = tmp_path / "2026-06-28_pre_s7_universe_report.json"

    with pytest.raises(ValueError, match="selection_reason"):
        build_s7_traceability_fields(
            report,
            report_path=report_path,
            input_path=None,
            selection_policy="top_n",
            selected_count=1,
        )

    with pytest.raises(ValueError, match="selection_source_path"):
        build_s7_traceability_fields(
            report,
            report_path=report_path,
            input_path=None,
            selection_policy="top_n",
            selection_reason="ranked by score",
            selected_count=1,
        )


def test_metric_context_mixing_is_classified_explicitly():
    assert classify_wiring_fault(
        pre_s7_metric_context="EXPANDED_RETRY",
        s7_metric_context="BAD_SESSION_REPLAY",
        pre_s7_valid_count=427,
        s7_input_count=2,
        s7_selection_policy="none",
        s7_selection_reason="N/A",
        s7_selection_source_path="/tmp/bad-session/data/2026-06-28_s4_valuation_candidates.json",
    ) == "METRIC_CONTEXT_MIXED"


def test_s7_blocks_when_canonical_s6_is_missing_after_s4_pass(tmp_path: Path):
    run_root = Path("/tmp") / f"bet-s7-traceability-{tmp_path.name}"
    environ = {
        "BET_PIPELINE_RUNTIME_MODE": "DRY_RUN",
        "BET_PIPELINE_BETTING_DAY": "2026-06-28",
        "BET_PIPELINE_RUN_ID": "trace-run",
        "BET_PIPELINE_RUN_ROOT": str(run_root),
        "BET_PIPELINE_DATA_DIR": str(run_root / "data"),
        "BET_PIPELINE_COUPON_DIR": str(run_root / "coupons"),
        "BET_PIPELINE_ARTIFACT_DIR": str(run_root / "artifacts"),
    }
    data_dir = Path(environ["BET_PIPELINE_DATA_DIR"])
    artifact_dir = Path(environ["BET_PIPELINE_ARTIFACT_DIR"])
    data_dir.mkdir(parents=True, exist_ok=True)
    artifact_dir.mkdir(parents=True, exist_ok=True)

    s4_path = data_dir / "2026-06-28_s4_valuation_candidates.json"
    s4_path.write_text(
        json.dumps(
            {
                "candidates": [
                    _candidate(
                        {
                            "candidate_id": "cand-s4",
                            "fixture_id": 10,
                            "home_team": "Alpha",
                            "away_team": "Beta",
                            "best_market": {
                                "name": "Over 2.5",
                                "direction": "OVER",
                                "safety_score": 0.82,
                            },
                            "market_count": 4,
                            "ev": 0.11,
                            "odds": {"market_best": 1.91},
                        }
                    )
                ]
            }
        ),
        encoding="utf-8",
    )
    repeat_path = data_dir / "repeat_loss_handoff_2026-06-28.json"
    repeat_path.write_text(json.dumps({"candidates": [{"fixture_id": "stale-repeat"}]}), encoding="utf-8")

    s4_evidence = {
        "schema_version": 1,
        "artifact_type": "SCRIPT_EVIDENCE",
        "step_id": "S4",
        "status": "PASS",
        "payload": {"s4_valuation_output_path": str(s4_path)},
    }
    for path in (
        artifact_dir / "S4.json",
        run_root / "pipeline_runs" / "2026-06-28" / "trace-run" / "artifacts" / "S4.json",
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(s4_evidence), encoding="utf-8")

    resolution = s5_gate.resolve_s7_input(environ, "2026-06-28", "trace-run")

    assert resolution["path"] is None
    assert resolution["source_kind"] == "missing"
    assert "S6" in str(resolution["blocked_reason"])

def test_discover_events_migrates_logical_identity_when_missing():
    import sqlite3
    from bet.db.schema import init_db, get_schema_version

    # 1. Create a database up to v19 manually but WITHOUT logical_identity column in fixture_capability_observation
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE schema_meta (key TEXT PRIMARY KEY, value TEXT)")
    conn.execute("INSERT INTO schema_meta (key, value) VALUES ('version', '19')")

    # Create all required tables by migration version 20
    conn.execute("CREATE TABLE fixtures (id INTEGER PRIMARY KEY, status TEXT, kickoff TEXT, home_team_id INTEGER, away_team_id INTEGER)")
    conn.execute("CREATE TABLE teams (id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("CREATE TABLE analysis_snapshot (run_id TEXT)")
    conn.execute("CREATE TABLE source_entity_reference (sport TEXT, entity_type TEXT, provider TEXT, provider_entity_id TEXT, valid_to TEXT)")
    conn.execute("CREATE TABLE fixture_sources (fixture_id INTEGER REFERENCES fixtures(id), source TEXT, external_id TEXT)")

    conn.execute(
        "CREATE TABLE fixture_capability_observation ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "canonical_fixture_id INTEGER NOT NULL REFERENCES fixtures(id),"
        "team_id INTEGER NOT NULL REFERENCES teams(id),"
        "capability TEXT NOT NULL,"
        "source TEXT NOT NULL,"
        "request_identity TEXT NOT NULL,"
        "evidence_bundle_id TEXT NOT NULL DEFAULT '',"
        "native_fixture_id TEXT NOT NULL DEFAULT '',"
        "native_team_id TEXT NOT NULL DEFAULT '',"
        "status TEXT NOT NULL,"
        "http_status INTEGER,"
        "error_code TEXT NOT NULL DEFAULT '',"
        "retryable INTEGER NOT NULL DEFAULT 0,"
        "parser_version TEXT NOT NULL DEFAULT '',"
        "parser_diagnostics_json TEXT NOT NULL DEFAULT '{}',"
        "observed_at TEXT NOT NULL,"
        "valid_at TEXT NOT NULL,"
        "payload_sha256 TEXT NOT NULL DEFAULT '',"
        "payload_json TEXT NOT NULL DEFAULT '',"
        "dto_version TEXT NOT NULL DEFAULT '1',"
        "evidence_package_id TEXT NOT NULL DEFAULT ''"
        # logical_identity is missing!
        ")"
    )

    # 2. Run migrate directly to trigger the version 20 migration
    from bet.db.schema import migrate
    migrate(conn, 19, 20)

    # 3. Check column exists
    cursor = conn.execute("PRAGMA table_info(fixture_capability_observation)")
    columns = [row[1] for row in cursor.fetchall()]
    assert "logical_identity" in columns
    conn.close()

def test_discover_events_reports_schema_mismatch_without_silent_fallback():
    # Test our custom try-except wrapper in discover_events.py reporting DB schema mismatch
    # directly and exiting with 2.
    import subprocess
    import sys
    from pathlib import Path

    # We can invoke discover_events.py with a bad db path pointing to a directory
    # which raises sqlite3.OperationalError on opening
    script_path = Path(__file__).resolve().parent.parent / "scripts" / "discover_events.py"

    res = subprocess.run(
        [sys.executable, str(script_path), "--date", "2026-06-28", "--db-path", str(Path(__file__).parent)],
        capture_output=True,
        text=True
    )

    assert res.returncode == 2
    assert "BLOCKED_DISCOVERY_DB_SCHEMA_MISMATCH" in res.stdout
    assert '"db_schema_verdict": "FAIL"' in res.stdout
    assert '"fallback_used": false' in res.stdout

def test_s1_output_marks_fallback_universe_explicitly():
    # Verify S1 output wrapper script captures fallback and schema verdicts
    from scripts.pipeline_steps.s1_discover import _payload

    run_metrics = {
        "raw_discovery_count": 10,
        "after_dedup_count": 8,
        "provider_counts": {"api-football": 10},
        "fallback_used": True,
        "fallback_reason": "scrapers offline",
        "db_schema_verdict": "PASS"
    }

    p = _payload(
        rc=0,
        runtime_mode="LIVE_SHADOW",
        dry_run=False,
        allow_write=True,
        allow_live_network=True,
        child_env={},
        runtime_path_source="test",
        run_metrics=run_metrics
    )

    assert p["raw_discovery_count"] == 10
    assert p["after_dedup_count"] == 8
    assert p["provider_counts"] == {"api-football": 10}
    assert p["fallback_used"] is True
    assert p["fallback_reason"] == "scrapers offline"
    assert p["db_schema_verdict"] == "PASS"

def test_fallback_two_stale_fixtures_blocks_as_insufficient_universe():
    config = LiveSessionUniverseConfig(min_candidates=8)
    # 2 stale candidate list should be blocked
    raw_list = [
        _candidate({"candidate_id": "cand-stale-1", "competition": ""}),
        _candidate({"candidate_id": "cand-stale-2", "competition": ""})
    ]
    report = build_pre_s7_universe(raw_list, config)
    assert report.status == "BLOCKED_INSUFFICIENT_CANDIDATE_UNIVERSE"
    assert report.valid_count == 0

def test_live_session_universe_requires_non_fallback_or_sufficient_universe():
    # If fallback is used, it shouldn't be accepted unless there are enough candidates
    config = LiveSessionUniverseConfig(min_candidates=8, provider_universe_exhausted=False)
    raw_list = [_candidate({"candidate_id": f"cand-{i}"}) for i in range(5)]
    report = build_pre_s7_universe(raw_list, config)
    assert report.status == "BLOCKED_INSUFFICIENT_CANDIDATE_UNIVERSE"

    # If min candidates is met, status is READY_FOR_S7
    config_met = LiveSessionUniverseConfig(min_candidates=5, provider_universe_exhausted=False)
    report_met = build_pre_s7_universe(raw_list, config_met)
    assert report_met.status == "READY_FOR_S7"

def test_pre_s7_gate_rejects_empty_competition_and_stale_kickoff():
    config = LiveSessionUniverseConfig()

    # Rejects empty competition
    cand_empty_comp = CandidateInput.from_dict(_candidate({"competition": ""}))
    res_comp = classify_candidate_quality(cand_empty_comp, config)
    assert res_comp.is_valid is False
    assert res_comp.verdict == "REJECTED_MISSING_COMPETITION"

    # Rejects stale kickoff
    past_time = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat().replace("+00:00", "Z")
    cand_stale = CandidateInput.from_dict(_candidate({"kickoff": past_time}))
    res_stale = classify_candidate_quality(cand_stale, config)
    assert res_stale.is_valid is False
    assert res_stale.verdict == "REJECTED_STALE"

def test_expanded_discovery_does_not_report_no_bet_when_raw_discovery_zero():
    # If raw discovery is zero, verify that the exit code of discover_events.py is non-zero,
    # preventing silent fallback to a final NO_BET_SESSION_VALID.
    import subprocess
    import sys
    from pathlib import Path

    script_path = Path(__file__).resolve().parent.parent / "scripts" / "discover_events.py"

    # Let's run with a future date where there will be 0 events in db and live fetch has 0 results.
    import tempfile
    import os
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    try:
        res = subprocess.run(
            [sys.executable, str(script_path), "--date", "2035-12-31", "--db-path", db_path, "--sports", "valorant"],
            capture_output=True,
            text=True
        )
        assert res.returncode == 2
        assert "BLOCKED_DISCOVERY_EMPTY_UNIVERSE" in res.stdout or "BLOCKED_DISCOVERY_PROVIDER_UNAVAILABLE" in res.stdout
    finally:
        try:
            os.unlink(db_path)
        except OSError:
            pass


def test_live_session_universe_splits_priced_and_unpriced_candidates():
    config = LiveSessionUniverseConfig(min_candidates=1)
    priced = _candidate({"candidate_id": "priced-1", "odds_decimal": 1.95})
    unpriced = _candidate({"candidate_id": "unpriced-1", "odds_decimal": 0.0, "model_probability": 0.65})
    report = build_pre_s7_universe([priced, unpriced], config)
    assert len(report.priced_valid_candidates) == 1
    assert report.priced_valid_candidates[0]["candidate_id"] == "priced-1"
    assert len(report.unpriced_analytical_candidates) == 1
    assert report.unpriced_analytical_candidates[0]["candidate_id"] == "unpriced-1"
    assert report.unpriced_analytical_candidates[0]["status"] == "PRICE_PENDING_OPERATOR_CHECK"


def test_missing_odds_blocks_priced_valid_but_allows_analytical_queue():
    config = LiveSessionUniverseConfig(min_candidates=1)
    unpriced = _candidate({"candidate_id": "unpriced-1", "odds_decimal": 0.0, "model_probability": 0.65})
    report = build_pre_s7_universe([unpriced], config)
    assert len(report.priced_valid_candidates) == 0
    assert len(report.unpriced_analytical_candidates) == 1


def test_unpriced_candidates_do_not_increment_ready_for_s7_count():
    config = LiveSessionUniverseConfig(min_candidates=2)
    priced = _candidate({"candidate_id": "priced-1", "odds_decimal": 1.95})
    unpriced = _candidate({"candidate_id": "unpriced-1", "odds_decimal": 0.0, "model_probability": 0.65})
    report = build_pre_s7_universe([priced, unpriced], config)
    assert report.valid_count == 1
    assert report.status == "READY_FOR_ANALYTICAL_OPERATOR_QUOTE_REVIEW"


def test_only_unpriced_candidates_returns_ready_for_analytical_operator_quote_review():
    config = LiveSessionUniverseConfig(min_candidates=2)
    unpriced = _candidate({"candidate_id": "unpriced-1", "odds_decimal": 0.0, "model_probability": 0.65})
    report = build_pre_s7_universe([unpriced], config)
    assert report.status == "READY_FOR_ANALYTICAL_OPERATOR_QUOTE_REVIEW"
