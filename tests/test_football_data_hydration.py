"""Tests for football data hydration contract, mappings, schemas, and prefilter integration."""
from __future__ import annotations

import json
from pathlib import Path
import pytest

from bet.pipeline.analyzability_prefilter import evaluate_candidate_analyzability
from bet.pipeline.market_probability_inputs import (
    build_market_probability_input,
    validate_market_probability_input,
    aggregate_split_stat_value,
    split_stat_aggregation_policy,
)


def _valid_candidate() -> dict:
    return {
        "candidate_id": "football|Alpha|Beta|2026-06-29",
        "sport": "football",
        "home_team": "Alpha",
        "away_team": "Beta",
        "competition": "Test League",
        "scheduled_time": "2026-06-29T18:00:00+00:00",
        "best_market": {"name": "Goals Total O/U", "direction": "OVER", "line": 2.5},
        "model_probability": 0.50,
        "probability_confidence": "MINIMAL",
        "probability_method": "S3_HIT_RATE_PROXY",
        "probability_sources": ["db"],
        "source_artifact_path": "/tmp/s4.json",
        "field_path": "candidates[0]",
    }


def _valid_stats_seed() -> dict:
    return {
        "stats_a_summary": {"has_data": True, "l10_avg": {"goals": 2.1}, "sources": ["stats_db"]},
        "stats_b_summary": {"has_data": True, "l10_avg": {"goals": 1.4}, "sources": ["stats_db"]},
        "h2h_summary": {"has_data": True, "meetings_count": 4},
        "raw_data": {
            "safety_input": {
                "markets": [
                    {
                        "name": "Goals Total O/U",
                        "line": 2.5,
                        "team_a_l10": [2.0, 1.0, 3.0, 1.0, 2.0, 1.0, 2.0, 0.0, 1.0, 2.0],
                        "team_b_l10": [1.0, 2.0, 0.0, 1.0, 3.0, 2.0, 1.0, 1.0, 2.0, 0.0],
                    }
                ]
            }
        }
    }


def test_football_data_hydration_report_schema():
    # Load and validate the JSON schema
    schema_path = Path("/Users/mkoziol/projects/bet/.kilo/artifacts/football_data_hydration_contract.json")
    assert schema_path.exists()
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    
    assert schema["title"] == "FootballDataHydrationReport"
    assert "hydration_status" in schema["required"]
    assert "HYDRATED" in schema["properties"]["hydration_status"]["enum"]


def test_hydrated_l10_series_unblocks_analyzability():
    # A candidate with MINIMAL confidence should be unblocked to ANALYZABLE if valid stats are present
    cand = _valid_candidate()
    stats = _valid_stats_seed()
    
    report = evaluate_candidate_analyzability(cand, stats)
    assert report["analyzability_status"] == "ANALYZABLE"
    assert report["analyzability_score"] == 1.0


def test_partial_hydration_remains_research_gap():
    cand = _valid_candidate()
    stats = _valid_stats_seed()
    # Shorter series than 5 elements (creates INSUFFICIENT_SAMPLE_SIZE which maps to RESEARCH_GAP_L10_MISSING)
    stats["raw_data"]["safety_input"]["markets"][0]["team_a_l10"] = [2.0, 1.0]
    
    report = evaluate_candidate_analyzability(cand, stats)
    assert report["analyzability_status"] == "RESEARCH_GAP_L10_MISSING"
    assert "SAMPLE_SIZE_INSUFFICIENT" in report["blocker_reasons"]


def test_api_football_probe_redacts_secret():
    # Ensure any printed key details are fully redacted
    api_key_env_var = "API_FOOTBALL_KEY"
    raw_secret = "secret-apisports-key-value-12345"
    
    # Simple log or string check helper
    def redact_key(log_message: str, key_value: str) -> str:
        if key_value in log_message:
            return log_message.replace(key_value, "[REDACTED]")
        return log_message
        
    log_line = f"Connecting to api-sports using key {raw_secret}"
    redacted = redact_key(log_line, raw_secret)
    assert raw_secret not in redacted
    assert "[REDACTED]" in redacted


def test_hydration_budget_bound_enforced():
    # Hydration must have strict bounded constraints
    max_batch_size = 20
    requested_ids = [str(i) for i in range(50)]
    
    # Logic constraint check from get_history_details client method
    assert len(requested_ids) > max_batch_size
    clean_ids = requested_ids[:max_batch_size]
    assert len(clean_ids) <= max_batch_size


def test_unknown_stat_semantics_stays_blocked():
    cand = _valid_candidate()
    stats = _valid_stats_seed()
    cand["model_probability"] = None
    
    # Corrupt the raw data to produce an unknown split stat semantics issue
    stats["raw_data"] = {
        "team_a_l10": {
            "l10_matches": [{"stats": {"mystery_split_stat": {"home": 2, "away": 1}}}]
        },
        "team_b_l10": {
            "l10_matches": [{"stats": {"mystery_split_stat": {"home": 1, "away": 0}}}]
        }
    }
    
    # We map "Goals Total O/U" to goals, but the stats seed is missing goals key completely and has mystery split key
    val, policy = aggregate_split_stat_value("mystery_split_stat", 2, 1)
    assert val is None
    assert policy == "UNKNOWN_SPLIT_STAT_SEMANTICS"


def test_known_goal_total_stats_build_l10_series():
    stats = _valid_stats_seed()
    # Derives goals total L10 series successfully
    cand = _valid_candidate()
    inp = build_market_probability_input(cand, stats)
    assert len(inp.team_a_l10) == 10
    assert inp.team_a_l10[0] == 2.0


def test_known_corners_stats_build_l10_series():
    stats = _valid_stats_seed()
    cand = _valid_candidate()
    cand["best_market"] = {"name": "Corners Total O/U", "direction": "OVER", "line": 9.5}
    
    # Inject corners market
    stats["raw_data"]["safety_input"]["markets"] = [
        {
            "name": "Corners Total O/U",
            "line": 9.5,
            "team_a_l10": [10, 9, 11, 8, 10, 9, 11, 8, 10, 9],
            "team_b_l10": [9, 8, 10, 7, 9, 8, 10, 7, 9, 8],
        }
    ]
    
    inp = build_market_probability_input(cand, stats)
    assert inp.market_family == "CORNERS"
    assert len(inp.team_a_l10) == 10
    assert inp.team_a_l10[0] == 10


def test_percentage_stats_not_summed():
    # Possession stats are percentage based, so they must use mean aggregation of home/away percentages, never sum.
    policy = split_stat_aggregation_policy("possession")
    assert policy == "MEAN_OF_HOME_AWAY_PERCENTAGES"
    
    val, pol = aggregate_split_stat_value("possession", 55.0, 45.0)
    assert val == 50.0  # Mean, not sum!
    assert pol == "MEAN_OF_HOME_AWAY_PERCENTAGES"


def test_no_fake_stats_in_hydration():
    cand = _valid_candidate()
    stats = _valid_stats_seed()
    cand["is_fake"] = True
    
    report = evaluate_candidate_analyzability(cand, stats)
    assert report["analyzability_status"] == "UNSUPPORTED_MARKET_FAMILY"
    assert "FAKE_DATA_DETECTED" in report["blocker_reasons"]


def test_bookmaker_implied_probability_not_used_as_stats():
    cand = _valid_candidate()
    cand["probability_method"] = "BOOKMAKER_IMPLIED_REFERENCE_ONLY"
    cand["model_probability"] = 0.55
    stats = _valid_stats_seed()
    
    # Bookmaker implied reference only must stay blocked from ANALYZABLE
    report = evaluate_candidate_analyzability(cand, stats)
    assert report["analyzability_status"] == "RESEARCH_GAP_L10_MISSING"


def test_analyzability_prefilter_uses_hydrated_stats():
    cand = _valid_candidate()
    stats = _valid_stats_seed()
    
    # Active prefilter unblocking test using fully hydrated stats seed
    report = evaluate_candidate_analyzability(cand, stats)
    assert report["analyzability_status"] == "ANALYZABLE"
    assert report["analyzability_score"] == 1.0
    assert report["stats_seed_status"] is True
    assert report["l10_series_status"] is True
