from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_manifest() -> dict:
    return json.loads((ROOT / "config" / "pipeline_manifest.json").read_text(encoding="utf-8"))


def test_manifest_has_superbet_manual_bet_builder_global_rules() -> None:
    manifest = load_manifest()
    rules = manifest.get("global_rules", {})
    required_true = [
        "fail_closed",
        "point_in_time_required",
        "odds_optional_for_analysis",
        "odds_required_for_ev_bettable_and_final_coupon",
        "analysis_candidate_generation_not_blocked_by_missing_odds",
        "manual_operator_quote_required_before_bettable",
        "superbet_bet_builder_combined_odds_operator_screen_only",
        "no_combined_bookmaker_odds_computation",
        "no_automated_bookmaker_placement",
        "many_event_full_day_generation_required",
        "tipster_layer_non_primary_evidence",
        "weather_injury_tournament_context_required",
        "use_kilo_code_active_default_model",
        "no_per_agent_model_override_in_betting_agents",
        "same_game_builder_groupings_are_ideas_until_human_quote",
        "point_in_time_source_timestamp_required",
        "unknown_instead_of_guessing_required",
    ]
    missing = [key for key in required_true if rules.get(key) is not True]
    assert not missing, f"Missing/false global rules: {missing}"
    assert rules.get("operator_workflow") == "SUPERBET_MANUAL_BET_BUILDER"


def test_manifest_keeps_enrichment_non_betting_and_s7b_before_s8() -> None:
    manifest = load_manifest()
    steps = manifest.get("steps", [])
    by_id = {step.get("id"): step for step in steps}
    ordered_ids = [step.get("id") for step in steps]

    assert ordered_ids.index("S2.9") < ordered_ids.index("S3")
    assert ordered_ids.index("S7b") < ordered_ids.index("S8")
    assert by_id["S8"].get("next") == ["S9"]

    for sid in ["S2.3", "S2.5", "S2.7", "S2.9"]:
        hard_rules = set(by_id[sid].get("hard_rules", []))
        assert {"no_pick", "no_edge", "no_stake", "no_coupon"}.issubset(hard_rules)


def test_manifest_superbet_rules_are_attached_to_every_key_phase() -> None:
    manifest = load_manifest()
    by_id = {step.get("id"): step for step in manifest.get("steps", [])}
    expected_rules = {
        "S1": ["full_day_event_universe_required", "fixture_identity_point_in_time_required"],
        "S2": ["tipster_layer_separate_from_verified_facts", "tipster_bias_grading_required"],
        "S3": ["market_family_probability_inputs_required", "no_fake_probabilities"],
        "S4": ["odds_missing_becomes_price_pending_not_analysis_block", "ev_requires_model_probability_and_operator_odds"],
        "S5": ["weather_context_required", "tipster_sentiment_layer_checked", "bet_builder_correlation_precheck"],
        "S6": ["cross_event_and_same_game_correlation_guard", "no_chase_after_loss_guard"],
        "S7": ["analytical_status_allowed_without_odds", "bettable_blocked_without_manual_quote"],
        "S7b": ["superbet_manual_market_name_line_mapping_only", "manual_quote_required_when_operator_quote_missing", "no_operator_browser_automation"],
        "S8": ["same_game_builder_correlation_check", "no_combined_bookmaker_odds_computation", "manual_quote_cards_required", "idea_grouping_not_final_coupon"],
        "S9": ["manual_user_verification_in_superbet", "human_entered_quote_required"],
        "S10": ["settlement_and_learning_only", "no_retroactive_pick_mutation"],
    }
    failures: dict[str, list[str]] = {}
    for sid, rules in expected_rules.items():
        hard_rules = set(by_id[sid].get("hard_rules", []))
        missing = [rule for rule in rules if rule not in hard_rules]
        if missing:
            failures[sid] = missing
    assert not failures, f"Missing Superbet phase hard rules: {failures}"
