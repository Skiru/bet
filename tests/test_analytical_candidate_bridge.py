from __future__ import annotations

import json
from pathlib import Path

import scripts.deep_stats_report as dsr

from bet.pipeline.analytical_candidate_bridge import (
    build_analytical_candidate_handoff,
    write_analytical_candidate_handoff,
)


def test_analytical_candidate_bridge_creates_ready_candidate_when_identity_probability_and_stats_exist():
    valuation_payload = {
        "source_input_path": "/tmp/2026-06-29_s3_deep_stats.json",
        "candidates": [
            {
                "fixture_id": 10,
                "candidate_id": "fixture:10",
                "sport": "football",
                "home_team": "Alpha",
                "away_team": "Beta",
                "competition": "Test League",
                "scheduled_time": "2026-06-29T18:00:00+00:00",
                "best_market": {"name": "Goals Total O/U", "direction": "OVER", "line": 2.5},
                "model_probability": 0.62,
                "probability_method": "S3_PROBABILITY_ENGINE",
                "probability_sources": ["stats_db"],
                "probability_as_of": "2026-06-29T12:00:00+00:00",
                "probability_confidence": "FULL",
                "odds": {"market_best": 1.91},
                "odds_source": "api",
            }
        ],
    }
    s3_payload = {
        "analyses": [
            {
                "fixture_id": 10,
                "candidate_id": "fixture:10",
                "sport": "football",
                "home_team": "Alpha",
                "away_team": "Beta",
                "competition": "Test League",
                "kickoff": "2026-06-29T18:00:00+00:00",
                "best_market": {"name": "Goals Total O/U", "direction": "OVER", "line": 2.5, "probability": 0.62},
                "model_probability": 0.62,
                "probability_method": "S3_PROBABILITY_ENGINE",
                "probability_sources": ["stats_db"],
                "probability_as_of": "2026-06-29T12:00:00+00:00",
                "probability_confidence": "FULL",
                "stats_a_summary": {"has_data": True, "l10_avg": {"goals": 2.1}, "sources": ["stats_db"]},
                "stats_b_summary": {"has_data": True, "l10_avg": {"goals": 1.4}, "sources": ["stats_db"]},
                "h2h_summary": {"has_data": True, "meetings_count": 4},
            }
        ]
    }

    handoff = build_analytical_candidate_handoff(
        valuation_payload,
        s3_payload=s3_payload,
        shortlist_payload=None,
        source_artifact_path="/tmp/2026-06-29_s4_valuation_candidates.json",
    )

    assert handoff["counts"]["analytical_ready"] == 1
    candidate = handoff["analytical_ready"][0]
    assert candidate["analytical_status"] == "ANALYTICAL_READY"
    assert candidate["sport"] == "football"
    assert candidate["competition"] == "Test League"
    assert candidate["participants"] == ["Alpha", "Beta"]
    assert candidate["model_probability"] == "0.62"


def test_probability_missing_blocks_fair_odds_but_preserves_research_gap():
    valuation_payload = {
        "candidates": [
            {
                "fixture_id": 11,
                "sport": "football",
                "home_team": "Alpha",
                "away_team": "Beta",
                "competition": "Test League",
                "scheduled_time": "2026-06-29T18:00:00+00:00",
                "odds": {"market_best": 2.10},
                "odds_source": "api",
            }
        ]
    }
    s3_payload = {
        "analyses": [
            {
                "fixture_id": 11,
                "sport": "football",
                "home_team": "Alpha",
                "away_team": "Beta",
                "competition": "Test League",
                "kickoff": "2026-06-29T18:00:00+00:00",
                "stats_a_summary": {"has_data": True, "l10_avg": {"goals": 2.1}, "sources": ["stats_db"]},
                "stats_b_summary": {"has_data": True, "l10_avg": {"goals": 1.1}, "sources": ["stats_db"]},
                "h2h_summary": {"has_data": True, "meetings_count": 3},
            }
        ]
    }
    shortlist_payload = {
        "candidates": [
            {
                "sport": "football",
                "home_team": "Alpha",
                "away_team": "Beta",
                "competition": "Test League",
                "kickoff": "2026-06-29T18:00:00+00:00",
                "odds_markets": [
                    {"market": "ml:home", "market_type": "ml", "outcome": "home", "point": None, "best_odds": 2.10}
                ],
            }
        ]
    }

    handoff = build_analytical_candidate_handoff(
        valuation_payload,
        s3_payload=s3_payload,
        shortlist_payload=shortlist_payload,
        source_artifact_path="/tmp/2026-06-29_s4_valuation_candidates.json",
    )

    assert handoff["counts"]["blocked_probability_missing"] == 1
    blocked = handoff["blocked_probability_missing"][0]
    assert blocked["analytical_status"] == "INSUFFICIENT_MODEL_PROBABILITY"
    assert blocked["model_probability"] is None
    assert "fair_odds" not in blocked


def test_bookmaker_implied_probability_not_used_as_model_probability():
    valuation_payload = {
        "candidates": [
            {
                "fixture_id": 12,
                "sport": "football",
                "home_team": "Alpha",
                "away_team": "Beta",
                "competition": "Test League",
                "scheduled_time": "2026-06-29T18:00:00+00:00",
                "best_market": {"name": "Goals Total O/U", "direction": "OVER", "line": 2.5},
                "model_probability": 0.55,
                "probability_method": "BOOKMAKER_IMPLIED_REFERENCE_ONLY",
                "odds": {"market_best": 1.95},
                "odds_source": "api",
            }
        ]
    }
    s3_payload = {
        "analyses": [
            {
                "fixture_id": 12,
                "sport": "football",
                "home_team": "Alpha",
                "away_team": "Beta",
                "competition": "Test League",
                "kickoff": "2026-06-29T18:00:00+00:00",
                "stats_a_summary": {"has_data": True, "l10_avg": {"goals": 2.1}, "sources": ["stats_db"]},
                "stats_b_summary": {"has_data": True, "l10_avg": {"goals": 1.1}, "sources": ["stats_db"]},
                "h2h_summary": {"has_data": True, "meetings_count": 3},
            }
        ]
    }

    handoff = build_analytical_candidate_handoff(
        valuation_payload,
        s3_payload=s3_payload,
        shortlist_payload=None,
        source_artifact_path="/tmp/2026-06-29_s4_valuation_candidates.json",
    )

    assert handoff["counts"]["blocked_probability_missing"] == 1
    blocked = handoff["blocked_probability_missing"][0]
    assert blocked["model_probability"] is None
    assert blocked["probability_missing_reason"] == "BOOKMAKER_IMPLIED_REFERENCE_ONLY"


def test_no_fake_stats():
    valuation_payload = {
        "candidates": [
            {
                "fixture_id": 13,
                "sport": "football",
                "home_team": "Alpha",
                "away_team": "Beta",
                "competition": "Test League",
                "scheduled_time": "2026-06-29T18:00:00+00:00",
                "best_market": {"name": "Goals Total O/U", "direction": "OVER", "line": 2.5},
                "model_probability": 0.62,
                "probability_method": "S3_PROBABILITY_ENGINE",
            }
        ]
    }
    s3_payload = {
        "analyses": [
            {
                "fixture_id": 13,
                "sport": "football",
                "home_team": "Alpha",
                "away_team": "Beta",
                "competition": "Test League",
                "kickoff": "2026-06-29T18:00:00+00:00",
                "stats_a_summary": {"has_data": False, "l10_avg": {}, "sources": []},
                "stats_b_summary": {"has_data": False, "l10_avg": {}, "sources": []},
                "h2h_summary": {"has_data": False, "meetings_count": 0},
            }
        ]
    }

    handoff = build_analytical_candidate_handoff(
        valuation_payload,
        s3_payload=s3_payload,
        shortlist_payload=None,
        source_artifact_path="/tmp/2026-06-29_s4_valuation_candidates.json",
    )

    assert handoff["counts"]["blocked_stats_missing"] == 1
    blocked = handoff["blocked_stats_missing"][0]
    assert blocked["supporting_stats"] == []
    assert blocked["analytical_status"] == "INSUFFICIENT_SUPPORTING_STATS"


def test_analytical_handoff_written_when_candidates_exist(tmp_path: Path):
    payload = {
        "artifact_type": "ANALYTICAL_CANDIDATE_HANDOFF",
        "analytical_ready": [{"candidate_id": "fixture:10"}],
        "blocked_probability_missing": [],
        "blocked_stats_missing": [],
        "blocked_identity_missing": [],
        "priced_candidates": [],
        "counts": {"analytical_ready": 1},
    }

    output_path = write_analytical_candidate_handoff(tmp_path / "analytical_candidate_handoff.json", payload)

    written = json.loads(output_path.read_text(encoding="utf-8"))
    assert written["artifact_type"] == "ANALYTICAL_CANDIDATE_HANDOFF"
    assert written["counts"]["analytical_ready"] == 1


def test_s3_stats_gap_reports_join_failure_reason(monkeypatch):
    monkeypatch.setattr(dsr, "extract_team_stats", lambda sport, team: {
        "team": team,
        "sport": sport,
        "l10_avg": {},
        "l5_avg": {},
        "l10_matches": [],
        "sources": [],
        "has_data": False,
        "espn_enrichment": None,
    })
    monkeypatch.setattr(dsr, "extract_h2h_stats", lambda sport, home, away: {
        "has_data": False,
        "meetings": [],
        "averages": {},
    })
    monkeypatch.setattr(dsr, "build_safety_input", lambda sport, home, away, competition: {})

    result = dsr.analyze_candidate(
        "football",
        "Alpha",
        "Beta",
        "Test League",
        "2026-06-29T18:00:00+00:00",
        shortlist_safety_markets=None,
    )

    assert result["has_data"] is False
    assert result["stats_gap_reason"] == "NO_STATS_DATA_FROM_CACHE_OR_DB_AND_NO_SHORTLIST_SAFETY_MARKETS"
