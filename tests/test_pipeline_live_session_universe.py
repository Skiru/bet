"""Unit and integration tests for Live Session Candidate Universe Gate."""
from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from datetime import datetime, timezone, timedelta
import pytest

from bet.pipeline.live_session_universe import (
    LiveSessionUniverseConfig,
    CandidateInput,
    classify_candidate_quality,
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

def test_missing_line_for_ou_rejected():
    config = LiveSessionUniverseConfig()
    cand = CandidateInput.from_dict(_candidate({"market": "Over 2.5", "line": "MISSING"}))
    res = classify_candidate_quality(cand, config)
    assert res.is_valid is False
    assert res.verdict == "REJECTED_MISSING_LINE"

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
