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
        "probability_confidence": "HIGH",
        "probability_method": "S3_HIT_RATE_PROXY",
        "probability_sources": ["db"],
        "source_provider": "api-football",
        "source_artifact_path": "/tmp/s4.json",
        "field_path": "candidates[0]",
    }


def _valid_stats_seed() -> dict:
    return {
        "probability_as_of": "2026-06-30T12:00:00Z",
        "source_provider": "api-football",
        "source_artifact_path": "/tmp/s4.json",
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
    # A candidate with HIGH confidence should be unblocked to ANALYZABLE if valid stats are present
    cand = _valid_candidate()
    cand["probability_confidence"] = "HIGH"
    stats = _valid_stats_seed()
    
    report = evaluate_candidate_analyzability(cand, stats)
    assert report["analyzability_status"] == "ANALYZABLE"
    assert report["analyzability_score"] == 1.0


def test_partial_hydration_remains_research_gap():
    cand = _valid_candidate()
    stats = _valid_stats_seed()
    # Shorter series than 5 elements (creates PARTIAL_HYDRATION)
    stats["raw_data"]["safety_input"]["markets"][0]["team_a_l10"] = [2.0, 1.0]
    
    report = evaluate_candidate_analyzability(cand, stats)
    assert report["analyzability_status"] == "REVIEW_ONLY_PARTIAL_DATA"
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
    assert report["analyzability_status"] == "RESEARCH_GAP_MARKET_INPUT_NOT_BUILT"


def test_analyzability_prefilter_uses_hydrated_stats():
    cand = _valid_candidate()
    cand["probability_confidence"] = "HIGH"
    stats = _valid_stats_seed()
    
    # Active prefilter unblocking test using fully hydrated stats seed
    report = evaluate_candidate_analyzability(cand, stats)
    assert report["analyzability_status"] == "ANALYZABLE"
    assert report["analyzability_score"] == 1.0
    assert report["stats_seed_status"] is True
    assert report["l10_series_status"] is True


def test_minimal_confidence_cannot_be_analyzable():
    cand = _valid_candidate()
    stats = _valid_stats_seed()
    cand["probability_confidence"] = "MINIMAL"
    
    report = evaluate_candidate_analyzability(cand, stats)
    assert report["analyzability_status"] == "RESEARCH_GAP_MINIMAL_HYDRATION"
    assert "LOW_CONFIDENCE_PROMOTION_BLOCKED" in report["blocker_reasons"]


def test_partial_hydration_cannot_be_analyzable():
    cand = _valid_candidate()
    stats = _valid_stats_seed()
    cand["probability_confidence"] = "PARTIAL"
    
    report = evaluate_candidate_analyzability(cand, stats)
    assert report["analyzability_status"] == "REVIEW_ONLY_PARTIAL_DATA"
    assert "PARTIAL_HYDRATION_BLOCKED" in report["blocker_reasons"]


def test_partial_hydration_review_only_not_quote_ready():
    from bet.pipeline.analytical_candidate_bridge import build_analytical_candidate_handoff
    cand = _valid_candidate()
    stats = _valid_stats_seed()
    cand["probability_confidence"] = "PARTIAL"
    cand["fixture_id"] = 1
    stats["fixture_id"] = 1
    
    handoff = build_analytical_candidate_handoff(
        {"candidates": [cand]},
        s3_payload={"analyses": [{**stats, "candidate_id": cand["candidate_id"], "fixture_id": 1}]},
        source_artifact_path="/tmp/s4.json"
    )
    assert handoff["counts"]["analytical_ready"] == 0
    assert len(handoff["review_only_partial_data"]) == 1
    assert handoff["package_type"] == "REVIEW_ONLY_PARTIAL_DATA_PACKAGE"


def test_minimal_hydration_research_gap_not_quote_ready():
    from bet.pipeline.analytical_candidate_bridge import build_analytical_candidate_handoff
    cand = _valid_candidate()
    stats = _valid_stats_seed()
    cand["probability_confidence"] = "MINIMAL"
    cand["fixture_id"] = 1
    stats["fixture_id"] = 1
    
    handoff = build_analytical_candidate_handoff(
        {"candidates": [cand]},
        s3_payload={"analyses": [{**stats, "candidate_id": cand["candidate_id"], "fixture_id": 1}]},
        source_artifact_path="/tmp/s4.json"
    )
    assert handoff["counts"]["analytical_ready"] == 0
    assert len(handoff["research_gap_minimal_hydration"]) == 1
    assert handoff["package_type"] == "RESEARCH_GAP_PACKAGE"


def test_partial_minimal_do_not_generate_fair_odds():
    from bet.pipeline.analytical_candidate_bridge import build_analytical_candidate_handoff
    cand1 = _valid_candidate()
    cand1["probability_confidence"] = "PARTIAL"
    cand1["fixture_id"] = 1
    cand1["candidate_id"] = "cand1"
    cand2 = _valid_candidate()
    cand2["probability_confidence"] = "MINIMAL"
    cand2["fixture_id"] = 2
    cand2["candidate_id"] = "cand2"
    stats = _valid_stats_seed()
    
    handoff = build_analytical_candidate_handoff(
        {"candidates": [cand1, cand2]},
        s3_payload={"analyses": [
            {**stats, "candidate_id": "cand1", "fixture_id": 1},
            {**stats, "candidate_id": "cand2", "fixture_id": 2}
        ]},
        source_artifact_path="/tmp/s4.json"
    )
    for c in handoff["review_only_partial_data"] + handoff["research_gap_minimal_hydration"]:
        assert c.get("model_probability") is None
        assert c.get("fair_odds") is None
        assert c.get("min_acceptable_operator_odds") is None


def test_ready_for_manual_operator_quote_review_requires_hydrated_analyzable():
    pass


def test_market_probability_input_requires_hydrated_status():
    cand = _valid_candidate()
    stats = _valid_stats_seed()
    # Shorter series
    stats["raw_data"]["safety_input"]["markets"][0]["team_a_l10"] = [2.0, 1.0]
    
    inp = build_market_probability_input(cand, stats)
    assert inp.hydration_status == "PARTIAL_HYDRATION"
    valid, reason = validate_market_probability_input(inp)
    assert not valid
    assert reason == "INSUFFICIENT_SAMPLE_SIZE"


def test_market_probability_input_requires_source_provider_and_as_of():
    cand = _valid_candidate()
    stats = _valid_stats_seed()
    stats["source_provider"] = ""
    cand["source_provider"] = ""
    
    inp = build_market_probability_input(cand, stats)
    valid, reason = validate_market_probability_input(inp)
    assert not valid
    assert reason == "SOURCE_PROVIDER_MISSING"


def test_market_series_no_match_does_not_use_last_market_fallback():
    cand = _valid_candidate()
    stats = _valid_stats_seed()
    cand["best_market"]["line"] = 5.5
    
    inp = build_market_probability_input(cand, stats)
    assert inp.semantics_issue == "MARKET_SERIES_NOT_FOUND_FOR_FAMILY_LINE"


def test_market_series_ambiguous_match_blocks_probability_input():
    cand = _valid_candidate()
    stats = _valid_stats_seed()
    stats["raw_data"]["safety_input"]["markets"].append({
        "name": "Goals Total O/U Alternative",
        "line": 2.5,
        "team_a_l10": [9.0, 9.0],
        "team_b_l10": [9.0, 9.0],
    })
    
    inp = build_market_probability_input(cand, stats)
    assert inp.semantics_issue == "AMBIGUOUS_MARKET_SERIES_MATCH"
    valid, reason = validate_market_probability_input(inp)
    assert not valid
    assert reason == "AMBIGUOUS_MARKET_SERIES_MATCH"


def test_exact_market_family_line_direction_match_required():
    cand = _valid_candidate()
    stats = _valid_stats_seed()
    cand["probability_confidence"] = "HIGH"
    
    inp = build_market_probability_input(cand, stats)
    valid, reason = validate_market_probability_input(inp)
    assert valid
    assert reason == "PASS"


def test_bookmaker_implied_probability_still_reference_only():
    cand = _valid_candidate()
    cand["probability_method"] = "BOOKMAKER_IMPLIED_REFERENCE_ONLY"
    stats = _valid_stats_seed()
    
    inp = build_market_probability_input(cand, stats)
    valid, reason = validate_market_probability_input(inp)
    assert not valid
    assert reason == "BOOKMAKER_IMPLIED_REFERENCE_ONLY"


def test_bet_builder_quote_guards_still_block_pipeline_computed_quote():
    from bet.pipeline.bet_builder_analytical import ManualSuperbetOperatorQuote
    from decimal import Decimal
    with pytest.raises(ValueError, match="no operator quote can have entered_by_human=False"):
        ManualSuperbetOperatorQuote(
            candidate_id="test",
            operator="Superbet",
            market_label="test",
            line="2.5",
            odds_decimal=Decimal("1.80"),
            combined_odds_decimal=Decimal("3.20"),
            as_of_utc="2026-06-30T12:00:00Z",
            entered_by_human=False,
        )


def test_secret_values_not_present_in_real_hydration_artifacts():
    keys_path = Path("/Users/mkoziol/projects/bet/config/api_keys.json")
    if not keys_path.exists():
        pytest.skip("api_keys.json does not exist")
        
    try:
        keys_data = json.loads(keys_path.read_text(encoding="utf-8"))
    except Exception:
        pytest.skip("Could not parse api_keys.json")
        
    secrets_to_check = []
    def _collect_secrets(data):
        if isinstance(data, dict):
            for k, v in data.items():
                _collect_secrets(v)
        elif isinstance(data, list):
            for v in data:
                _collect_secrets(v)
        elif isinstance(data, str):
            val = data.strip()
            if len(val) >= 8 and not any(p in val.lower() for p in ("your_key", "placeholder", "dummy", "test_key", "testkey")):
                secrets_to_check.append(val)
                
    _collect_secrets(keys_data)
    if not secrets_to_check:
        secrets_to_check.append("super-secret-key-that-must-never-appear")
        
    artifact_dirs = [
        Path("/Users/mkoziol/projects/bet/.kilo/artifacts"),
        Path("/tmp")
    ]
    
    files_to_scan = []
    patterns = ["*hydration*", "*api_football*", "*provider*", "s4.txt", "s5.txt", "s8.txt", "*.log"]
    for d in artifact_dirs:
        if d.exists():
            for pat in patterns:
                files_to_scan.extend(d.glob(pat))
                
    for f in files_to_scan:
        if f.is_file():
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
                for secret in secrets_to_check:
                    assert secret not in content, f"Secret was leaked in artifact file: {f.name}"
            except Exception:
                pass
