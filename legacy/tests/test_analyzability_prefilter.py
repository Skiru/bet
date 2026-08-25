"""Unit tests for the analyzability prefilter module."""
from __future__ import annotations

import json
from pathlib import Path
import pytest

from bet.pipeline.analyzability_prefilter import (
    evaluate_candidate_analyzability,
    rank_analyzable_candidates,
    split_analyzable_and_research_gap,
)
from bet.pipeline.analytical_candidate_bridge import build_analytical_candidate_handoff


def _valid_candidate() -> dict:
    return {
        "candidate_id": "football|Alpha|Beta|2026-06-29",
        "sport": "football",
        "home_team": "Alpha",
        "away_team": "Beta",
        "competition": "Test League",
        "scheduled_time": "2026-06-29T18:00:00+00:00",
        "best_market": {"name": "Goals Total O/U", "direction": "OVER", "line": 2.5},
        "model_probability": 0.62,
        "probability_method": "S3_PROBABILITY_ENGINE",
        "probability_sources": ["stats_db"],
        "probability_confidence": "FULL",
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


def test_analyzability_prefilter_marks_supported_candidate_analyzable():
    cand = _valid_candidate()
    stats = _valid_stats_seed()

    report = evaluate_candidate_analyzability(cand, stats)
    assert report["analyzability_status"] == "ANALYZABLE"
    assert report["analyzability_score"] == 1.0
    assert not report["blocker_reasons"]


def test_analyzability_prefilter_blocks_l10_missing():
    cand = _valid_candidate()
    stats = _valid_stats_seed()
    # Wipe L10 series data
    stats["raw_data"]["safety_input"]["markets"] = []
    # Make sure we don't have existing model probability which would bypass it
    cand["model_probability"] = None

    report = evaluate_candidate_analyzability(cand, stats)
    assert report["analyzability_status"] == "RESEARCH_GAP_L10_MISSING"
    assert "L10_SERIES_MISSING" in report["blocker_reasons"]


def test_analyzability_prefilter_blocks_unknown_split_stat_semantics():
    cand = _valid_candidate()
    stats = _valid_stats_seed()
    cand["model_probability"] = None

    # We corrupt the stats series to produce a semantic mapping issue
    stats["raw_data"] = {
        "team_a_l10": {
            "l10_matches": [{"stats": {"mystery_stat": {"home": 2}}}]
        },
        "team_b_l10": {
            "l10_matches": [{"stats": {"mystery_stat": {"home": 1}}}]
        }
    }

    report = evaluate_candidate_analyzability(cand, stats)
    assert report["analyzability_status"] == "RESEARCH_GAP_L10_MISSING"


def test_analyzability_prefilter_blocks_missing_line_for_ou_market():
    cand = _valid_candidate()
    stats = _valid_stats_seed()
    cand["best_market"]["line"] = None

    report = evaluate_candidate_analyzability(cand, stats)
    assert report["analyzability_status"] == "LINE_OR_DIRECTION_GAP"
    assert "LINE_MISSING" in report["blocker_reasons"]


def test_analyzability_prefilter_blocks_unsupported_player_prop():
    cand = _valid_candidate()
    stats = _valid_stats_seed()
    cand["best_market"]["name"] = "Player Tackles"

    report = evaluate_candidate_analyzability(cand, stats)
    assert report["analyzability_status"] == "UNSUPPORTED_MARKET_FAMILY"
    assert "UNSUPPORTED_MARKET_FAMILY" in report["blocker_reasons"]


def test_analyzability_prefilter_preserves_source_artifact_and_field_path():
    cand = _valid_candidate()
    stats = _valid_stats_seed()

    report = evaluate_candidate_analyzability(cand, stats)
    assert report["source_artifact_path"] == "/tmp/s4.json"
    assert report["field_path"] == "candidates[0]"


def test_rank_analyzable_candidates_prefers_probability_input_ready():
    c1 = {"candidate_id": "c1", "analyzability_score": 0.5, "market_probability_input_status": False}
    c2 = {"candidate_id": "c2", "analyzability_score": 1.0, "market_probability_input_status": True}
    c3 = {"candidate_id": "c3", "analyzability_score": 0.8, "market_probability_input_status": True}

    ranked = rank_analyzable_candidates([c1, c2, c3])
    assert ranked[0]["candidate_id"] == "c2"
    assert ranked[1]["candidate_id"] == "c3"
    assert ranked[2]["candidate_id"] == "c1"


def test_full_smoke_selection_uses_analyzable_candidates_first():
    cand = _valid_candidate()
    cand["fixture_id"] = 2
    stats = _valid_stats_seed()

    # Let's run a full handoff with 1 valid and 1 blocked candidate
    cand_blocked = _valid_candidate()
    cand_blocked["candidate_id"] = "blocked"
    cand_blocked["fixture_id"] = 1
    cand_blocked["model_probability"] = None
    stats_blocked = _valid_stats_seed()
    stats_blocked["raw_data"]["safety_input"]["markets"] = []

    valuation_payload = {
        "candidates": [cand_blocked, cand]
    }
    s3_payload = {
        "analyses": [
            {**stats_blocked, "candidate_id": "blocked", "fixture_id": 1},
            {**stats, "candidate_id": cand["candidate_id"], "fixture_id": 2}
        ]
    }

    handoff = build_analytical_candidate_handoff(
        valuation_payload,
        s3_payload=s3_payload,
        source_artifact_path="/tmp/s4.json"
    )

    # Ranked correctly
    assert handoff["counts"]["analytical_ready"] == 1
    assert handoff["analytical_ready"][0]["candidate_id"] == cand["candidate_id"]


def test_research_gap_package_when_no_analyzable_candidates():
    # If both candidates are blocked, analytical_ready is empty, so package is RESEARCH_GAP_PACKAGE
    cand1 = _valid_candidate()
    cand1["model_probability"] = None
    stats1 = _valid_stats_seed()
    stats1["raw_data"]["safety_input"]["markets"] = []

    valuation_payload = {
        "candidates": [cand1]
    }
    s3_payload = {
        "analyses": [{**stats1, "candidate_id": cand1["candidate_id"]}]
    }

    handoff = build_analytical_candidate_handoff(
        valuation_payload,
        s3_payload=s3_payload,
        source_artifact_path="/tmp/s4.json"
    )

    assert handoff["counts"]["analytical_ready"] == 0
    assert handoff["package_type"] == "RESEARCH_GAP_PACKAGE"


def test_no_fake_stats_or_probability_in_prefilter():
    cand = _valid_candidate()
    stats = _valid_stats_seed()

    # Force fake stats flag
    cand["is_fake"] = True

    report = evaluate_candidate_analyzability(cand, stats)
    assert report["analyzability_status"] == "UNSUPPORTED_MARKET_FAMILY"
    assert "FAKE_DATA_DETECTED" in report["blocker_reasons"]
