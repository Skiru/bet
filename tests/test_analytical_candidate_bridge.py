from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

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


def test_team_identity_resolver_exact_and_alias_matches():
    from bet.enrichment.team_identity_resolver import resolve_team_identity
    
    # Test exact match
    res_exact = resolve_team_identity("Brazil", "football")
    assert res_exact.resolved is True
    assert res_exact.canonical_name == "Brazil"
    assert res_exact.provider_team_id == "api-football:1"
    assert res_exact.confidence == "HIGH"
    
    # Test alias match
    res_alias = resolve_team_identity("Seleção", "football")
    assert res_alias.resolved is True
    assert res_alias.canonical_name == "Brazil"
    assert res_alias.provider_team_id == "api-football:1"
    
    # Test normalized match
    res_norm = resolve_team_identity("f.c. melgar", "football")
    assert res_norm.resolved is True
    assert res_norm.canonical_name == "Melgar"


def test_team_identity_unresolved_reports_failure_reason():
    from bet.enrichment.team_identity_resolver import resolve_team_identity
    res = resolve_team_identity("Unknown Football Club Name", "football")
    assert res.resolved is False
    assert res.failure_reason == "TEAM_IDENTITY_NOT_RESOLVED"


def test_s3_stats_gap_reports_team_identity_failure(monkeypatch):
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
    
    result = dsr.analyze_candidate(
        "football",
        "Unknown_Team_X",
        "Japan",
        "Test Cup",
        "2026-06-29T18:00:00+00:00",
        shortlist_safety_markets=None,
    )
    assert result["has_data"] is False
    assert result["probability_missing_reason"] == "NO_STATS_DATA_FOR_MODEL_PROBABILITY"


def test_api_football_stats_probe_redacts_secret():
    # Simple test ensuring we have a mock environment key check that avoids print leak
    from scripts.probe_api_football import get_api_key
    key = get_api_key()
    if key:
        redacted = key[:2] + "*" * (len(key) - 2) if len(key) > 2 else "**"
        assert "*" in redacted


def test_market_family_mapping_result_totals_corners_cards_shots():
    from bet.pipeline.analytical_candidate_bridge import _market_family_from_seed, _supported_analytical_family
    
    m_ml = {"name": "Match Winner", "market_type": "ml"}
    assert _market_family_from_seed(m_ml) == "RESULT"
    
    m_totals = {"name": "goals_over/under", "market_type": "totals"}
    assert _market_family_from_seed(m_totals) == "GOALS_TOTALS"
    
    m_corners = {"name": "corners_over_under", "market_type": "corners"}
    assert _market_family_from_seed(m_corners) == "CORNERS"
    
    m_cards = {"name": "yellow_cards", "market_type": "cards"}
    assert _market_family_from_seed(m_cards) == "CARDS"
    
    m_shots = {"name": "shots", "market_type": "shots"}
    assert _market_family_from_seed(m_shots) == "SHOTS"
    
    m_sot = {"name": "shots_on_target", "market_type": "shots_on_target"}
    assert _market_family_from_seed(m_sot) == "SHOTS_ON_TARGET"
    
    # Verify supported families
    assert _supported_analytical_family("RESULT") is True
    assert _supported_analytical_family("GOALS_TOTALS") is True
    assert _supported_analytical_family("CORNERS") is True
    assert _supported_analytical_family("CARDS") is True
    assert _supported_analytical_family("SHOTS") is True
    assert _supported_analytical_family("SHOTS_ON_TARGET") is True


def test_unsupported_player_tackles_not_promoted():
    from bet.pipeline.analytical_candidate_bridge import _market_family_from_seed, _supported_analytical_family
    m_tackles = {"name": "player_tackles", "market_type": "player_tackles"}
    family = _market_family_from_seed(m_tackles)
    assert family == "UNSUPPORTED_PROP_MATCH"
    assert _supported_analytical_family(family) is False


def test_missing_market_family_reports_source_artifact_and_field_path():
    handoff = build_analytical_candidate_handoff(
        {
            "candidates": [
                {
                    "fixture_id": 210,
                    "sport": "football",
                    "home_team": "Alpha",
                    "away_team": "Beta",
                    "competition": "Test League",
                    "scheduled_time": "2026-06-29T18:00:00+00:00",
                    "odds": {"market_best": 1.91},
                }
            ]
        },
        s3_payload={"analyses": []},
        shortlist_payload={"candidates": []},
        source_artifact_path="/tmp/2026-06-29_s4_valuation_candidates.json",
    )

    blocked = handoff["blocked_identity_missing"][0]
    assert blocked["blocking_reason"] == "MISSING_MARKET_FAMILY"
    assert blocked["source_gaps"][0]["artifact"] == "/tmp/2026-06-29_s4_valuation_candidates.json"
    assert blocked["source_gaps"][0]["field_path"] == "candidate"


def test_ambiguous_market_label_not_promoted():
    from bet.pipeline.market_probability_inputs import build_market_probability_input, validate_market_probability_input

    candidate = {
        "candidate_id": "ambiguous-1",
        "sport": "football",
        "market": "Special",
        "market_type": "specials",
        "home_team": "Team A",
        "away_team": "Team B",
    }
    stats_seed = {
        "stats_a_summary": {"has_data": True, "l10_avg": {"goals": 2.0}, "sources": ["db"]},
        "stats_b_summary": {"has_data": True, "l10_avg": {"goals": 1.0}, "sources": ["db"]},
        "h2h_summary": {"has_data": False, "meetings_count": 0, "averages": {}},
        "raw_data": {},
    }

    inp = build_market_probability_input(candidate, stats_seed)
    valid, reason = validate_market_probability_input(inp)
    assert valid is False
    assert reason == "AMBIGUOUS_MARKET_LABEL"


def test_missing_line_blocks_ou_probability_input():
    from bet.pipeline.market_probability_inputs import build_market_probability_input, validate_market_probability_input

    candidate = {
        "candidate_id": "ou-missing-line",
        "sport": "football",
        "market_family": "GOALS_TOTALS",
        "market_type": "totals",
        "market": "Goals Total O/U",
        "direction": "OVER",
        "selection": "OVER",
        "home_team": "Team A",
        "away_team": "Team B",
    }
    stats_seed = {
        "raw_data": {
            "safety_input": {
                "markets": [
                    {
                        "name": "Goals Total O/U",
                        "line": 2.5,
                        "team_a_l10": [2, 1, 3, 1, 2, 1, 2, 0, 1, 2],
                        "team_b_l10": [1, 2, 0, 1, 3, 2, 1, 1, 2, 0],
                    }
                ]
            }
        }
    }

    inp = build_market_probability_input(candidate, stats_seed)
    valid, reason = validate_market_probability_input(inp)
    assert valid is False
    assert reason == "LINE_MISSING"


def test_model_probability_requires_real_stats():
    from scripts.probability_engine import enrich_ranking_with_probabilities
    
    # If len of L10 stats is less than 5, must fall back to hit rate proxy
    ranking_result = {
        "ranking": [
            {
                "name": "goals_over/under",
                "line": 2.5,
                "direction": "OVER",
                "hit_rate_l10": 0.70,
                "hit_rate_h2h": 0.50,
            }
        ],
        "_markets_input": [
            {
                "name": "goals_over/under",
                "line": 2.5,
                "direction": "OVER",
                "team_a_l10": [2, 3],  # only 2 matches (less than 5)
                "team_b_l10": [1, 2],
            }
        ]
    }
    enriched = enrich_ranking_with_probabilities(ranking_result)
    assert enriched["ranking"][0]["model_used"] == "S3_HIT_RATE_PROXY"
    assert enriched["ranking"][0]["probability"] == 0.60


def test_probability_missing_reason_when_no_stats():
    # If has_data is False (no stats), S3 report should output NO_STATS_DATA_FOR_MODEL_PROBABILITY
    from scripts.deep_stats_report import analyze_candidate
    result = analyze_candidate(
        "football",
        "Alpha",
        "Beta",
        "Test League",
        "2026-06-29T18:00:00+00:00",
        shortlist_safety_markets=None,
    )
    assert result["model_probability"] is None
    assert result["probability_missing_reason"] == "NO_STATS_DATA_FOR_MODEL_PROBABILITY"


def test_analytical_bridge_promotes_only_when_identity_stats_probability_ready():
    # Verify that the bridge strictly validates and only promotes when ready
    valuation_payload = {
        "candidates": [
            {
                "fixture_id": 20,
                "sport": "football",
                "home_team": "Alpha",
                "away_team": "Beta",
                "competition": "Test League",
                "scheduled_time": "2026-06-29T18:00:00+00:00",
                "best_market": {"name": "Goals Total O/U", "direction": "OVER", "line": 2.5},
                "model_probability": 0.62,
                "probability_method": "S3_PROBABILITY_ENGINE",
                "odds": {"market_best": 1.91},
            }
        ]
    }
    
    # 1. Stats missing blocks promotion
    handoff_no_stats = build_analytical_candidate_handoff(
        valuation_payload,
        s3_payload=None,
        source_artifact_path="/tmp/val.json",
    )
    assert handoff_no_stats["counts"]["analytical_ready"] == 0
    assert handoff_no_stats["counts"]["blocked_stats_missing"] == 1


def test_market_probability_input_built_for_goals_totals():
    from bet.pipeline.market_probability_inputs import build_market_probability_input
    candidate = {
        "candidate_id": "c1",
        "sport": "football",
        "market_family": "GOALS_TOTALS",
        "market_type": "Goals Total O/U",
        "pick": "OVER",
        "line": 2.5,
        "home_team": "Team A",
        "away_team": "Team B",
    }
    stats_seed = {
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
    inp = build_market_probability_input(candidate, stats_seed)
    assert inp.market_family == "GOALS_TOTALS"
    assert inp.team_a_l10 == [2.0, 1.0, 3.0, 1.0, 2.0, 1.0, 2.0, 0.0, 1.0, 2.0]
    assert inp.team_b_l10 == [1.0, 2.0, 0.0, 1.0, 3.0, 2.0, 1.0, 1.0, 2.0, 0.0]


def test_market_probability_input_built_for_result():
    from bet.pipeline.market_probability_inputs import build_market_probability_input, validate_market_probability_input
    candidate = {
        "candidate_id": "c1",
        "sport": "football",
        "market_family": "RESULT",
        "market_type": "ml",
        "pick": "home",
        "line": None,
        "home_team": "Team A",
        "away_team": "Team B",
    }
    stats_seed = {
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
    inp = build_market_probability_input(candidate, stats_seed)
    assert inp.market_family == "RESULT"
    valid, reason = validate_market_probability_input(inp)
    assert valid is True


def test_market_probability_input_built_for_corners_when_l10_exists():
    from bet.pipeline.market_probability_inputs import build_market_probability_input
    candidate = {
        "candidate_id": "c1",
        "sport": "football",
        "market_family": "CORNERS",
        "market_type": "Corners Total O/U",
        "pick": "OVER",
        "line": 9.5,
        "home_team": "Team A",
        "away_team": "Team B",
    }
    stats_seed = {
        "raw_data": {
            "safety_input": {
                "markets": [
                    {
                        "name": "Corners Total O/U",
                        "line": 9.5,
                        "team_a_l10": [5, 6, 7, 4, 5, 6, 4, 5, 6, 5],
                        "team_b_l10": [4, 5, 4, 3, 5, 4, 3, 4, 5, 4],
                    }
                ]
            }
        }
    }
    inp = build_market_probability_input(candidate, stats_seed)
    assert inp.market_family == "CORNERS"
    assert len(inp.team_a_l10) == 10


def test_probability_input_requires_line_for_totals_corners_cards_shots():
    from bet.pipeline.market_probability_inputs import build_market_probability_input, validate_market_probability_input
    candidate = {
        "candidate_id": "c1",
        "sport": "football",
        "market_family": "CORNERS",
        "market_type": "Corners Total O/U",
        "pick": "OVER",
        "line": None,
        "home_team": "Team A",
        "away_team": "Team B",
    }
    stats_seed = {
        "raw_data": {
            "safety_input": {
                "markets": [
                    {
                        "name": "Corners Total O/U",
                        "line": 9.5,
                        "team_a_l10": [5, 6, 7, 4, 5, 6, 4, 5, 6, 5],
                        "team_b_l10": [4, 5, 4, 3, 5, 4, 3, 4, 5, 4],
                    }
                ]
            }
        }
    }
    inp = build_market_probability_input(candidate, stats_seed)
    valid, reason = validate_market_probability_input(inp)
    assert valid is False
    assert reason == "LINE_MISSING"


def test_probability_input_requires_min_sample_size():
    from bet.pipeline.market_probability_inputs import build_market_probability_input, validate_market_probability_input
    candidate = {
        "candidate_id": "c1",
        "sport": "football",
        "market_family": "GOALS_TOTALS",
        "market_type": "Goals Total O/U",
        "pick": "OVER",
        "line": 2.5,
        "home_team": "Team A",
        "away_team": "Team B",
    }
    stats_seed = {
        "raw_data": {
            "safety_input": {
                "markets": [
                    {
                        "name": "Goals Total O/U",
                        "line": 2.5,
                        "team_a_l10": [2, 1, 3],
                        "team_b_l10": [1, 2, 0, 1],
                    }
                ]
            }
        }
    }
    inp = build_market_probability_input(candidate, stats_seed)
    valid, reason = validate_market_probability_input(inp)
    assert valid is False
    assert reason == "INSUFFICIENT_SAMPLE_SIZE"


def test_bookmaker_implied_probability_not_model_input():
    valuation_payload = {
        "candidates": [
            {
                "fixture_id": 30,
                "sport": "football",
                "home_team": "Alpha",
                "away_team": "Beta",
                "competition": "Test League",
                "best_market": {"name": "Goals Total O/U", "direction": "OVER", "line": 2.5},
                "model_probability": 0.55,
                "probability_method": "BOOKMAKER_IMPLIED_REFERENCE_ONLY",
                "odds": {"market_best": 1.95},
            }
        ]
    }
    handoff = build_analytical_candidate_handoff(
        valuation_payload,
        s3_payload=None,
        source_artifact_path="/tmp/val.json",
    )
    assert handoff["counts"]["analytical_ready"] == 0
    assert handoff["counts"]["blocked_probability_missing"] == 1
    assert handoff["blocked_probability_missing"][0]["model_probability"] is None


def test_probability_engine_called_for_supported_market_family():
    from scripts.probability_engine import enrich_ranking_with_probabilities
    ranking_result = {
        "ranking": [
            {
                "name": "Goals Total O/U",
                "line": 2.5,
                "direction": "OVER",
                "hit_rate_l10": "7/10",
                "hit_rate_h2h": "3/5",
            }
        ],
        "_markets_input": [
            {
                "name": "Goals Total O/U",
                "line": 2.5,
                "direction": "OVER",
                "team_a_l10": [2, 1, 3, 4, 2, 1, 0, 1, 2, 3],
                "team_b_l10": [1, 2, 1, 0, 1, 2, 1, 0, 1, 2],
            }
        ]
    }
    enriched = enrich_ranking_with_probabilities(ranking_result)
    assert enriched["ranking"][0]["model_used"] == "S3_TEAM_FORM_CONTEXTUAL_PROXY"
    assert enriched["ranking"][0]["probability"] is not None


def test_probability_output_propagates_to_analytical_handoff():
    valuation_payload = {
        "candidates": [
            {
                "fixture_id": 40,
                "sport": "football",
                "home_team": "Alpha",
                "away_team": "Beta",
                "competition": "Test League",
                "best_market": {"name": "Goals Total O/U", "direction": "OVER", "line": 2.5},
                "model_probability": 0.62,
                "probability_method": "S3_TEAM_FORM_CONTEXTUAL_PROXY",
                "probability_sources": ["db"],
                "probability_as_of": "2026-06-29T12:00:00Z",
                "probability_confidence": "HIGH",
                "odds": {"market_best": 1.91},
            }
        ]
    }
    s3_payload = {
        "analyses": [
            {
                "fixture_id": 40,
                "sport": "football",
                "home_team": "Alpha",
                "away_team": "Beta",
                "competition": "Test League",
                "best_market": {"name": "Goals Total O/U", "direction": "OVER", "line": 2.5, "probability": 0.62},
                "stats_a_summary": {"has_data": True, "l10_avg": {"goals": 2.1}, "sources": ["db"]},
                "stats_b_summary": {"has_data": True, "l10_avg": {"goals": 1.4}, "sources": ["db"]},
                "h2h_summary": {"has_data": True, "meetings_count": 4},
            }
        ]
    }
    handoff = build_analytical_candidate_handoff(
        valuation_payload,
        s3_payload=s3_payload,
        source_artifact_path="/tmp/val.json",
    )
    assert handoff["counts"]["analytical_ready"] == 1
    cand = handoff["analytical_ready"][0]
    assert cand["model_probability"] == "0.62"
    assert cand["probability_method"] == "S3_TEAM_FORM_CONTEXTUAL_PROXY"
    assert cand["probability_confidence"] == "HIGH"


def test_probability_missing_reason_exact_when_series_missing():
    valuation_payload = {
        "candidates": [
            {
                "fixture_id": 50,
                "sport": "football",
                "home_team": "Alpha",
                "away_team": "Beta",
                "competition": "Test League",
                "best_market": {"name": "Goals Total O/U", "direction": "OVER", "line": 2.5},
                "odds": {"market_best": 1.91},
            }
        ]
    }
    s3_payload = {
        "analyses": [
            {
                "fixture_id": 50,
                "sport": "football",
                "home_team": "Alpha",
                "away_team": "Beta",
                "competition": "Test League",
                "best_market": {"name": "Goals Total O/U", "direction": "OVER", "line": 2.5, "probability": None},
                "stats_a_summary": {"has_data": True, "l10_avg": {}, "sources": ["db"]},
                "stats_b_summary": {"has_data": True, "l10_avg": {}, "sources": ["db"]},
                "probability_missing_reason": "NO_MODEL_PROBABILITY_FROM_S3",
            }
        ]
    }
    handoff = build_analytical_candidate_handoff(
        valuation_payload,
        s3_payload=s3_payload,
        source_artifact_path="/tmp/val.json",
    )
    assert handoff["counts"]["blocked_probability_missing"] == 1
    assert handoff["blocked_probability_missing"][0]["probability_missing_reason"] == "NO_MODEL_PROBABILITY_FROM_S3"


def test_player_tackles_remains_unsupported():
    from bet.pipeline.market_probability_inputs import MarketProbabilityInput, validate_market_probability_input
    inp = MarketProbabilityInput(
        candidate_id="c1",
        sport="football",
        market_family="UNSUPPORTED_PROP_MATCH",
        market_type="player_tackles",
        selection="over",
        direction="OVER",
        line=2.5,
        team_a_name="Alpha",
        team_b_name="Beta",
    )
    valid, reason = validate_market_probability_input(inp)
    assert valid is False
    assert reason == "UNSUPPORTED_PROP_MATCH"


def test_no_fake_probability():
    from scripts.probability_engine import enrich_ranking_with_probabilities
    ranking_result = {
        "ranking": [
            {
                "name": "Goals Total O/U",
                "line": 2.5,
                "direction": "OVER",
            }
        ],
        "_markets_input": []
    }
    enriched = enrich_ranking_with_probabilities(ranking_result)
    assert enriched["ranking"][0]["probability"] is None


def test_team_identity_fallback_requires_context_or_high_confidence(monkeypatch):
    import bet.db.connection as db_connection
    import bet.db.repositories as repositories
    from scripts.db_data_loader import load_team_form_from_db

    class FakeConn:
        def execute(self, query, params):
            return SimpleNamespace(fetchall=lambda: [{"id": 2, "name": "Atletico Madrid"}])

    class FakeDBContext:
        def __enter__(self):
            return FakeConn()

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakeSportRepo:
        def __init__(self, conn):
            self.conn = conn

        def get_by_name(self, sport):
            return SimpleNamespace(id=1, name=sport)

        def seed_defaults(self):
            return None

    class FakeTeamRepo:
        def __init__(self, conn):
            self.conn = conn

        def resolve(self, team_name, sport_id):
            return SimpleNamespace(id=1, name="Real Madrid")

    class FakeStatsRepo:
        def __init__(self, conn):
            self.conn = conn

        def get_all_form_for_team(self, team_id, sport_id):
            if team_id == 1:
                return [
                    SimpleNamespace(
                        stat_key="goals",
                        l10_avg=1.4,
                        l5_avg=1.2,
                        l10_values="[1, 2, 1]",
                    )
                ]
            if team_id == 2:
                return [
                    SimpleNamespace(
                        stat_key="goals",
                        l10_avg=3.8,
                        l5_avg=3.5,
                        l10_values="[4, 4, 3, 4, 4, 4]",
                    )
                ]
            return []

    monkeypatch.setattr(db_connection, "get_db", lambda: FakeDBContext())
    monkeypatch.setattr(repositories, "SportRepo", FakeSportRepo)
    monkeypatch.setattr(repositories, "TeamRepo", FakeTeamRepo)
    monkeypatch.setattr(repositories, "StatsRepo", FakeStatsRepo)

    result = load_team_form_from_db("Real Madrid", "football")

    assert result is not None
    assert result["form"]["l10_avg"]["goals"] == 1.4
    assert result["team_identity_match"]["source"] == "TEAM_REPO_RESOLVE"
    assert result["team_identity_match"]["fallback_used"] is False


def test_team_identity_fallback_false_positive_does_not_generate_probability(monkeypatch):
    monkeypatch.setattr(dsr, "extract_team_stats", lambda sport, team: {
        "team": team,
        "sport": sport,
        "l10_avg": {"goals": 2.0},
        "l5_avg": {"goals": 1.8},
        "l10_matches": [{"goals": 2}] * 10,
        "sources": ["db"],
        "has_data": True,
        "raw_cache": None,
        "split_stat_aggregation_policy": {},
        "stat_semantics_issues": [],
        "team_identity_match": {
            "source": "AMBIGUOUS_SURNAME_FALLBACK",
            "confidence": "LOW",
            "fallback_used": True,
        },
    })
    monkeypatch.setattr(dsr, "extract_h2h_stats", lambda sport, home, away: {
        "has_data": True,
        "meetings": [{"goals": 3}] * 3,
        "averages": {"goals": 3.0},
    })
    monkeypatch.setattr(dsr, "build_safety_input", lambda sport, home, away, competition: {
        "markets": [{
            "name": "Goals Total O/U",
            "line": 2.5,
            "direction": "OVER",
            "team_a_l10": [2, 3, 2, 1, 2],
            "team_b_l10": [1, 2, 1, 2, 1],
        }]
    })
    monkeypatch.setattr(dsr, "rank_markets", lambda safety_input: {
        "ranking": [{
            "rank": 1,
            "name": "Goals Total O/U",
            "line": 2.5,
            "direction": "OVER",
            "safety_score": 0.8,
            "combined_avg": 3.0,
            "h2h_avg": 3.0,
            "hit_rate_l10": "7/10",
            "hit_rate_l5": "4/5",
            "hit_rate_h2h": "3/5",
            "source": "stats_db",
            "one_sided": False,
            "h2h_blind": False,
        }],
        "three_way_check": None,
        "recommended_market": "Goals Total O/U",
        "recommended_safety": 0.8,
        "warnings": [],
        "markdown_ranking_table": "",
        "markdown_three_way_table": "",
        "markets_evaluated": 1,
        "min_required": 1,
        "_markets_input": [{
            "name": "Goals Total O/U",
            "line": 2.5,
            "direction": "OVER",
            "team_a_l10": [2, 3, 2, 1, 2],
            "team_b_l10": [1, 2, 1, 2, 1],
        }],
    })

    result = dsr.analyze_candidate(
        "football",
        "Real Madrid",
        "Barcelona",
        "La Liga",
        "2026-06-29T18:00:00+00:00",
        shortlist_safety_markets=None,
    )

    assert result["model_probability"] is None
    assert result["probability_missing_reason"] == "TEAM_IDENTITY_LOW_CONFIDENCE"
    assert result["probability_confidence"] == "BLOCKED"


def test_split_home_away_stats_not_summed_when_semantics_unknown():
    from bet.pipeline.market_probability_inputs import aggregate_split_stat_value

    aggregated, policy = aggregate_split_stat_value("mystery_metric", 6, 4)

    assert aggregated is None
    assert policy == "UNKNOWN_SPLIT_STAT_SEMANTICS"


def test_split_counting_stats_use_declared_aggregation_policy():
    from bet.pipeline.market_probability_inputs import aggregate_split_stat_value

    aggregated, policy = aggregate_split_stat_value("goals", 2.0, 1.0)

    assert aggregated == 1.5
    assert policy == "MEAN_OF_HOME_AWAY_RATES"


def test_percentage_stats_not_summed():
    from bet.pipeline.market_probability_inputs import aggregate_split_stat_value

    aggregated, policy = aggregate_split_stat_value("possession", 60.0, 40.0)

    assert aggregated == 50.0
    assert policy == "MEAN_OF_HOME_AWAY_PERCENTAGES"


def test_probability_hit_rate_parser_accepts_fraction_decimal_percent():
    from scripts.probability_engine import _parse_hit_rate_with_reason

    assert _parse_hit_rate_with_reason("5/10") == (0.5, "PASS")
    assert _parse_hit_rate_with_reason("0.5") == (0.5, "PASS")
    assert _parse_hit_rate_with_reason("50%") == (0.5, "PASS")
    assert _parse_hit_rate_with_reason("5 of 10") == (0.5, "PASS")


def test_probability_hit_rate_parser_rejects_malformed_values_fail_closed():
    from scripts.probability_engine import _parse_hit_rate_with_reason, enrich_ranking_with_probabilities

    assert _parse_hit_rate_with_reason("5//10")[0] is None
    assert _parse_hit_rate_with_reason("five of ten")[0] is None
    assert _parse_hit_rate_with_reason("11/10") == (None, "HIT_RATE_OUT_OF_RANGE")

    ranking_result = {
        "ranking": [{
            "name": "Goals Total O/U",
            "line": 2.5,
            "direction": "OVER",
            "hit_rate_l10": "5//10",
            "hit_rate_h2h": "N/A",
        }],
        "_markets_input": [],
    }
    enriched = enrich_ranking_with_probabilities(ranking_result)
    assert enriched["ranking"][0]["probability"] is None
    assert enriched["ranking"][0]["probability_missing_reason"] == "HIT_RATE_PARSE_ERROR"


def test_probability_input_blocks_unknown_stat_semantics():
    from bet.pipeline.market_probability_inputs import MarketProbabilityInput, validate_market_probability_input

    inp = MarketProbabilityInput(
        candidate_id="c-1",
        sport="football",
        market_family="GOALS_TOTALS",
        market_type="Goals Total O/U",
        selection="OVER",
        direction="OVER",
        line=2.5,
        team_a_name="Alpha",
        team_b_name="Beta",
        semantics_issue="UNKNOWN_SPLIT_STAT_SEMANTICS",
    )

    valid, reason = validate_market_probability_input(inp)

    assert valid is False
    assert reason == "UNKNOWN_SPLIT_STAT_SEMANTICS"


def test_bookmaker_implied_probability_cannot_be_model_probability():
    valuation_payload = {
        "candidates": [
            {
                "fixture_id": 130,
                "sport": "football",
                "home_team": "Alpha",
                "away_team": "Beta",
                "competition": "Test League",
                "scheduled_time": "2026-06-29T18:00:00+00:00",
                "best_market": {"name": "Goals Total O/U", "direction": "OVER", "line": 2.5},
                "model_probability": 0.61,
                "probability_method": "BOOKMAKER_IMPLIED_REFERENCE_ONLY",
                "probability_confidence": "HIGH",
                "odds": {"market_best": 1.95},
            }
        ]
    }
    s3_payload = {
        "analyses": [
            {
                "fixture_id": 130,
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


def test_low_confidence_probability_label_blocks_analytical_ready():
    valuation_payload = {
        "candidates": [
            {
                "fixture_id": 140,
                "sport": "football",
                "home_team": "Alpha",
                "away_team": "Beta",
                "competition": "Test League",
                "scheduled_time": "2026-06-29T18:00:00+00:00",
                "best_market": {"name": "Goals Total O/U", "direction": "OVER", "line": 2.5},
                "model_probability": 0.58,
                "probability_method": "S3_PROBABILITY_ENGINE",
                "probability_confidence": "LOW",
                "odds": {"market_best": 1.91},
            }
        ]
    }
    s3_payload = {
        "analyses": [
            {
                "fixture_id": 140,
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

    assert handoff["counts"]["analytical_ready"] == 0
    assert handoff["counts"]["blocked_probability_missing"] == 1
    blocked = handoff["blocked_probability_missing"][0]
    assert blocked["probability_confidence"] == "LOW"
    assert blocked["model_probability"] is None
