from __future__ import annotations

import json
from pathlib import Path

import pytest

from bet.pipeline.unified_live_analyst_session import (
    BetBuilderComboIdea,
    apply_human_quote_if_valid,
    build_package_from_candidates,
    load_candidates_from_path,
    validate_human_superbet_quote,
)


def _football_candidate(**overrides):
    base = {
        "candidate_id": "c1",
        "sport": "football",
        "event_id": "e1",
        "competition": "World Cup",
        "home_team": "Alpha",
        "away_team": "Beta",
        "market_family": "CORNERS",
        "line": 7.5,
        "direction": "OVER",
        "supporting_evidence": [
            "Alpha create pressure from wide areas",
            "Beta concede territory when underdog",
        ],
        "counter_evidence": ["Referee/venue data unknown"],
    }
    base.update(overrides)
    return base


def _tennis_candidate(**overrides):
    base = {
        "candidate_id": "t1",
        "sport": "tennis",
        "event_label": "Player A vs Player B",
        "competition": "Wimbledon",
        "market_family": "TOTAL_GAMES",
        "line": 21.5,
        "direction": "OVER",
        "supporting_evidence": ["Both players have serve-oriented profile in available notes"],
        "counter_evidence": ["Exact recent hold/break data unavailable"],
    }
    base.update(overrides)
    return base


def test_odds_missing_does_not_block_live_analyst_idea():
    package = build_package_from_candidates([_football_candidate()], run_id="r1")
    assert package.package_type == "ANALYST_RECOMMENDATION_PACKAGE"
    assert len(package.recommendations) == 1
    idea = package.recommendations[0]
    assert idea.odds_available is False
    assert idea.ev_available is False
    assert package.ready_for_manual_operator_quote_review is True


def test_hydration_missing_does_not_block_live_analyst_idea():
    package = build_package_from_candidates([_football_candidate(hydration_status="MINIMAL_HYDRATION")], run_id="r1")
    assert len(package.recommendations) == 1
    assert package.recommendations[0].hydrated_available is False
    assert "not blocked" in " ".join(package.recommendations[0].source_gaps)


def test_model_probability_missing_does_not_block_recommendation_but_prevents_ev():
    package = build_package_from_candidates([_football_candidate(model_probability=None)], run_id="r1")
    idea = package.recommendations[0]
    assert idea.model_probability_available is False
    assert idea.ev_available is False
    assert idea.fair_odds_available is False


def test_missing_model_probability_prevents_ev_claim():
    package = build_package_from_candidates([_football_candidate(model_probability=None, odds_decimal=2.1)], run_id="r1")
    idea = package.recommendations[0]
    assert idea.odds_available is True
    assert idea.model_probability_available is False
    assert idea.ev_available is False


def test_partial_data_lowers_confidence_or_watchlist():
    package = build_package_from_candidates([_football_candidate(supporting_evidence=["Only one partial signal"], counter_evidence=[])], run_id="r1")
    ideas = package.recommendations + package.watchlist_only
    assert ideas
    assert ideas[0].analyst_confidence in {"C", "D"}


def test_unknown_data_quality_cannot_be_high_confidence():
    package = build_package_from_candidates([_football_candidate(supporting_evidence=[], counter_evidence=[])], run_id="r1")
    idea = (package.recommendations + package.watchlist_only)[0]
    assert idea.data_quality in {"LOW", "UNKNOWN"}
    assert idea.analyst_confidence not in {"A", "B"}


def test_weak_evidence_becomes_watchlist_only():
    package = build_package_from_candidates([_football_candidate(supporting_evidence=[], counter_evidence=[])], run_id="r1")
    assert len(package.watchlist_only) == 1
    assert package.watchlist_only[0].suggested_use == "WATCHLIST_ONLY"


def test_every_recommendation_has_counter_evidence_field():
    package = build_package_from_candidates([_football_candidate(counter_evidence=[])], run_id="r1")
    idea = (package.recommendations + package.watchlist_only)[0]
    assert idea.counter_evidence
    assert "UNKNOWN" in idea.counter_evidence[0]


def test_event_only_football_can_generate_reference_line_watch_or_recommendation():
    package = build_package_from_candidates([
        {
            "candidate_id": "wc1",
            "sport": "football",
            "competition": "World Cup",
            "home_team": "Team Wide",
            "away_team": "Team Deep Block",
            "notes": "wide attacks, territory and pressure; corner pattern should be checked",
            "counter_evidence": ["No exact L10 corner data"],
        }
    ], run_id="r1")
    ideas = package.recommendations + package.watchlist_only
    assert ideas
    assert ideas[0].market_family == "CORNERS"
    assert ideas[0].line_source == "DEFAULT_REFERENCE_NEEDS_OPERATOR_CHECK"
    assert "operator line" in " ".join(ideas[0].source_gaps).lower()


def test_wimbledon_tennis_not_blocked_by_missing_hydration():
    package = build_package_from_candidates([_tennis_candidate()], run_id="r1")
    assert len(package.recommendations) == 1
    assert package.recommendations[0].sport == "tennis"
    assert package.recommendations[0].hydrated_available is False


def test_tennis_event_only_defaults_total_games_check():
    package = build_package_from_candidates([
        {
            "candidate_id": "w1",
            "competition": "Wimbledon",
            "player_one": "Server A",
            "player_two": "Server B",
            "notes": "grass surface, serve-oriented notes, tie-break risk",
        }
    ], run_id="r1")
    ideas = package.recommendations + package.watchlist_only
    assert ideas
    assert ideas[0].sport == "tennis"
    assert ideas[0].market_family in {"TOTAL_GAMES", "ACES"}


def test_bet_builder_combo_does_not_compute_combined_odds():
    combo = BetBuilderComboIdea(combo_id="x", idea_ids=["a", "b"], event_label="A vs B", combo_note="manual", correlation_notes=[], conflict_risks=[])
    assert combo.to_dict()["combined_odds_decimal"] is None
    with pytest.raises(ValueError):
        BetBuilderComboIdea(combo_id="bad", idea_ids=["a"], event_label="A", combo_note="bad", correlation_notes=[], conflict_risks=[], combined_odds_decimal=2.5).to_dict()


def test_no_final_coupon_without_human_quote():
    package = build_package_from_candidates([_football_candidate()], run_id="r1")
    assert package.ready_for_final_coupon is False
    assert package.ready_for_manual_placement is False


def test_manual_quote_required_for_final_coupon():
    package = build_package_from_candidates([_football_candidate(candidate_id="c1")], run_id="r1")
    rec_id = package.recommendations[0].idea_id
    ok, issues = validate_human_superbet_quote(package, {
        "entered_by_human": True,
        "operator": "Superbet",
        "as_of_utc": "2026-06-30T12:00:00Z",
        "quotes": [{
            "recommendation_id": rec_id,
            "legs_confirmed_on_operator_screen": True,
            "operator_market_labels": ["Total corners"],
            "operator_lines": ["7.5"],
            "combined_odds_decimal": 2.1,
        }],
    })
    assert ok, issues
    final = apply_human_quote_if_valid(package, {
        "entered_by_human": True,
        "operator": "Superbet",
        "as_of_utc": "2026-06-30T12:00:00Z",
        "quotes": [{
            "recommendation_id": rec_id,
            "legs_confirmed_on_operator_screen": True,
            "operator_market_labels": ["Total corners"],
            "operator_lines": ["7.5"],
            "combined_odds_decimal": 2.1,
        }],
    })
    assert final.package_type == "FINAL_MANUAL_COUPON_PACKAGE"
    assert final.ready_for_final_coupon is True


def test_invalid_quote_rejected():
    package = build_package_from_candidates([_football_candidate()], run_id="r1")
    rejected = apply_human_quote_if_valid(package, {"entered_by_human": False, "operator": "Superbet", "quotes": []})
    assert rejected.package_type == "QUOTE_REJECTED_PACKAGE"
    assert rejected.ready_for_manual_placement is False


def test_ready_for_manual_operator_quote_review_true_with_recommendations():
    package = build_package_from_candidates([_football_candidate()], run_id="r1")
    assert package.ready_for_manual_operator_quote_review is True


def test_load_candidates_from_run_artifact(tmp_path: Path):
    p = tmp_path / "artifact.json"
    p.write_text(json.dumps({"candidates": [_football_candidate()]}), encoding="utf-8")
    loaded = load_candidates_from_path(tmp_path)
    assert loaded
    package = build_package_from_candidates(loaded, run_id="r1")
    assert package.package_type == "ANALYST_RECOMMENDATION_PACKAGE"
