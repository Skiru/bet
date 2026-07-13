from __future__ import annotations
from datetime import datetime, timezone, timedelta
from typing import Any
import pytest
from bet.pipeline.live_fixture_audit import LiveFixtureAudit

def test_audit_candidate_rejected_test_or_synthetic() -> None:
    future = datetime.now(timezone.utc) + timedelta(days=1)
    audit = LiveFixtureAudit(target_date=future.strftime("%Y-%m-%d"))

    # Candidate names are irrelevant; explicit provenance controls classification.
    for keyword in ["test", "fake", "example", "ghost", "TEST_123", "FAKE_MATCH"]:
        candidate = {
            "candidate_id": f"match_{keyword}",
            "betting_day": future.strftime("%Y-%m-%d"),
            "kickoff": future.isoformat(),
            "home_team": "Team A",
            "away_team": "Team B",
            "provenance": {"kind": "TEST_FIXTURE"},
        }
        status, reason = audit.audit_candidate(candidate)
        assert status == "REJECTED_TEST_OR_SYNTHETIC_FIXTURE"
        assert "explicit test provenance" in reason

def test_audit_candidate_rejected_wrong_betting_day() -> None:
    audit = LiveFixtureAudit(target_date="2026-07-08")
    
    # Wrong betting_day field
    candidate = {
        "candidate_id": "match_123",
        "betting_day": "2026-07-09",
        "kickoff": "2026-07-08T20:00:00Z",
        "home_team": "Team A",
        "away_team": "Team B"
    }
    status, reason = audit.audit_candidate(candidate)
    assert status == "REJECTED_WRONG_BETTING_DAY"
    assert "does not match target" in reason

def test_audit_candidate_missing_kickoff() -> None:
    audit = LiveFixtureAudit(target_date="2026-07-08")
    
    candidate = {
        "candidate_id": "match_123",
        "betting_day": "2026-07-08",
        "home_team": "Team A",
        "away_team": "Team B"
    }
    status, reason = audit.audit_candidate(candidate)
    assert status == "REJECTED_UNVERIFIED_FIXTURE_IDENTITY"
    assert "Missing kickoff timestamp" in reason

def test_audit_candidate_invalid_kickoff_format() -> None:
    audit = LiveFixtureAudit(target_date="2026-07-08")
    
    candidate = {
        "candidate_id": "match_123",
        "betting_day": "2026-07-08",
        "kickoff": "invalid-date-format",
        "home_team": "Team A",
        "away_team": "Team B"
    }
    status, reason = audit.audit_candidate(candidate)
    assert status == "REJECTED_UNVERIFIED_FIXTURE_IDENTITY"
    assert "Failed to parse kickoff timestamp" in reason

def test_audit_candidate_already_started() -> None:
    audit = LiveFixtureAudit(target_date="2026-07-08")
    
    # Kickoff in the past
    past_time = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    candidate = {
        "candidate_id": "match_123",
        "betting_day": "2026-07-08",
        "kickoff": past_time,
        "home_team": "Team A",
        "away_team": "Team B"
    }
    status, reason = audit.audit_candidate(candidate)
    assert status == "REJECTED_ALREADY_STARTED"
    assert "is in the past" in reason

def test_audit_candidate_kickoff_wrong_betting_day() -> None:
    audit = LiveFixtureAudit(target_date="2026-07-08")
    
    # Kickoff on a different day (future)
    future_time = (datetime.now(timezone.utc) + timedelta(days=2))
    # Ensure it's not on 2026-07-08
    if future_time.strftime("%Y-%m-%d") == "2026-07-08":
        future_time += timedelta(days=1)
    
    candidate = {
        "candidate_id": "match_123",
        "kickoff": future_time.isoformat(),
        "home_team": "Team A",
        "away_team": "Team B"
    }
    status, reason = audit.audit_candidate(candidate)
    assert status == "REJECTED_WRONG_BETTING_DAY"
    assert "does not match target" in reason

def test_audit_candidate_missing_participants() -> None:
    tomorrow = datetime.now(timezone.utc) + timedelta(days=1)
    target_date = tomorrow.strftime("%Y-%m-%d")
    kickoff_time = tomorrow.replace(hour=20, minute=0, second=0, microsecond=0).isoformat()
    audit = LiveFixtureAudit(target_date=target_date)
    
    # Missing home_team
    candidate = {
        "candidate_id": "match_123",
        "kickoff": kickoff_time,
        "away_team": "Team B"
    }
    status, reason = audit.audit_candidate(candidate)
    assert status == "REJECTED_PARTICIPANT_MISMATCH"
    assert "Missing home_team or away_team" in reason

    # Missing away_team
    candidate = {
        "candidate_id": "match_123",
        "kickoff": kickoff_time,
        "home_team": "Team A"
    }
    status, reason = audit.audit_candidate(candidate)
    assert status == "REJECTED_PARTICIPANT_MISMATCH"
    assert "Missing home_team or away_team" in reason

def test_audit_candidate_stale_fixture() -> None:
    tomorrow = (datetime.now(timezone.utc) + timedelta(days=1))
    # Stale probability_as_of (> 24 hours)
    stale_time = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
    kickoff_time = (tomorrow + timedelta(hours=2)).isoformat()
    target_date = datetime.fromisoformat(kickoff_time).strftime("%Y-%m-%d")
    audit = LiveFixtureAudit(target_date=target_date)
    candidate = {
        "candidate_id": "match_123",
        "kickoff": kickoff_time,
        "home_team": "Team A",
        "away_team": "Team B",
        "probability_as_of": stale_time
    }
    status, reason = audit.audit_candidate(candidate)
    assert status == "REJECTED_STALE_FIXTURE"
    assert "Source artifact is stale" in reason

    # Stale stats_as_of (> 24 hours)
    candidate = {
        "candidate_id": "match_123",
        "kickoff": kickoff_time,
        "home_team": "Team A",
        "away_team": "Team B",
        "stats_as_of": stale_time
    }
    status, reason = audit.audit_candidate(candidate)
    assert status == "REJECTED_STALE_FIXTURE"
    assert "Source artifact is stale" in reason

def test_audit_candidate_valid() -> None:
    # Valid candidate
    future_time = (datetime.now(timezone.utc) + timedelta(hours=2))
    # Force target_date to match the future_time's date
    target_date = future_time.strftime("%Y-%m-%d")
    audit = LiveFixtureAudit(target_date=target_date)
    
    candidate = {
        "candidate_id": "match_123",
        "kickoff": future_time.isoformat(),
        "home_team": "Team A",
        "away_team": "Team B",
        "probability_as_of": (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    }
    status, reason = audit.audit_candidate(candidate)
    assert status == "LIVE_FIXTURE_VERIFIED_NOT_STARTED"
    assert reason == "PASS"

def test_assign_tiers_score_calculation() -> None:
    audit = LiveFixtureAudit(target_date="2026-07-08")
    
    # Base candidate with probability, standard hydration, high data quality, safety score
    candidate = {
        "candidate_id": "match_1",
        "probability": 0.6,
        "hydration_status": "STANDARD_HYDRATION",
        "team_a_l10": [1, 2, 3, 4, 5, 6, 7, 8],
        "team_b_l10": [1, 2, 3, 4, 5, 6, 7, 8],
        "data_quality": {"label": "HIGH"},
        "safety_score": 0.5
    }
    
    # Expected score:
    # 0.6 * 10.0 = 6.0
    # standard hydration -> 0.0
    # data quality HIGH -> +2.0
    # safety_score 0.5 -> +2.5
    # Total = 10.5
    
    results = audit.assign_tiers([candidate])
    assert len(results) == 1
    assert results[0]["review_score"] == 10.5
    assert results[0]["risk_label"] == "STANDARD_HYDRATION"
    assert results[0]["review_tier"] == "A_MANUAL_QUOTE_PRIORITY"

def test_assign_tiers_minimal_hydration_and_tiny_sample() -> None:
    audit = LiveFixtureAudit(target_date="2026-07-08")
    
    # Minimal hydration and tiny sample size
    candidate = {
        "candidate_id": "match_1",
        "model_probability": 0.8,
        "hydration_status": "MINIMAL_HYDRATION",
        "team_a_l10": [1, 2, 3, 4], # sample size 4 < 5
        "team_b_l10": [1, 2, 3],
        "data_quality": {"label": "MINIMAL"},
        "best_market": {"safety_score": 0.2}
    }
    
    # Expected score:
    # 0.8 * 10.0 = 8.0
    # MINIMAL_HYDRATION -> -3.0
    # data quality MINIMAL -> -1.0
    # best_market safety_score 0.2 -> +1.0
    # Total = 5.0
    # Since is_tiny_sample or is_minimal is True, tier should be C_WATCHLIST_ONLY
    
    results = audit.assign_tiers([candidate])
    assert len(results) == 1
    assert results[0]["review_score"] == 5.0
    assert results[0]["risk_label"] == "MINIMAL_HYDRATION_HIGH_UNCERTAINTY"
    assert results[0]["review_tier"] == "C_WATCHLIST_ONLY"

def test_assign_tiers_small_sample() -> None:
    audit = LiveFixtureAudit(target_date="2026-07-08")
    
    # Small sample size (5 <= sample_size < 8)
    candidate = {
        "candidate_id": "match_1",
        "probability": 0.8,
        "hydration_status": "STANDARD_HYDRATION",
        "team_a_l10": [1, 2, 3, 4, 5, 6], # sample size 6
        "team_b_l10": [1, 2, 3, 4, 5],
        "data_quality": {"label": "MEDIUM"},
        "safety_score": 0.4
    }
    
    # Expected score:
    # 0.8 * 10.0 = 8.0
    # data quality MEDIUM -> +1.0
    # safety_score 0.4 -> +2.0
    # Total = 11.0
    # Since is_small_sample is True, tier should be B_MANUAL_QUOTE_SECONDARY
    
    results = audit.assign_tiers([candidate])
    assert len(results) == 1
    assert results[0]["review_score"] == 11.0
    assert results[0]["review_tier"] == "B_MANUAL_QUOTE_SECONDARY"

def test_assign_tiers_capping_and_sorting() -> None:
    audit = LiveFixtureAudit(target_date="2026-07-08")
    
    # Create 30 candidates that would normally be A_MANUAL_QUOTE_PRIORITY
    # (score >= 7.5, sample_size >= 8, standard hydration)
    candidates = []
    for i in range(30):
        candidates.append({
            "candidate_id": f"match_{i}",
            "probability": 0.8, # score 8.0
            "hydration_status": "STANDARD_HYDRATION",
            "team_a_l10": [1, 2, 3, 4, 5, 6, 7, 8],
            "team_b_l10": [1, 2, 3, 4, 5, 6, 7, 8],
            # Give them slightly different scores to test sorting
            "safety_score": 0.1 * (30 - i)
        })
        
    results = audit.assign_tiers(candidates)
    
    # Verify sorting: first candidate should have the highest score
    assert results[0]["review_score"] > results[-1]["review_score"]
    
    # Verify capping:
    # Max 12 A_MANUAL_QUOTE_PRIORITY
    # Max 25 total A + B
    # Remaining 5 should be C_WATCHLIST_ONLY
    a_tier = [c for c in results if c["review_tier"] == "A_MANUAL_QUOTE_PRIORITY"]
    b_tier = [c for c in results if c["review_tier"] == "B_MANUAL_QUOTE_SECONDARY"]
    c_tier = [c for c in results if c["review_tier"] == "C_WATCHLIST_ONLY"]
    
    assert len(a_tier) == 12
    assert len(b_tier) == 13 # 25 - 12 = 13
    assert len(c_tier) == 5
