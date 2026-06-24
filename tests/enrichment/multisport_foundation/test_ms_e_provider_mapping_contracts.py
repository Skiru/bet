import json

from bet.enrichment.multisport_foundation.provider_mapping import (
    ProviderMappingStatus,
    build_provider_mapping_plan,
    default_route_specs,
    validate_mapping_plan,
)
from bet.enrichment.multisport_foundation.verifier import verify_provider_mapping

TARGET_SPORTS = {"basketball", "volleyball", "hockey", "tennis", "cs2", "dota2", "valorant"}

def test_provider_mapping_plan_covers_exactly_target_sports():
    plan = build_provider_mapping_plan({})
    assert set(plan["target_sports"]) == TARGET_SPORTS
    assert set(plan["provider_mapping_by_sport"]) == TARGET_SPORTS

def test_no_live_calls_or_production_activation_or_betting_decisions():
    plan = build_provider_mapping_plan({})
    assert plan["live_calls_allowed"] is False
    assert plan["production_activation"] is False
    assert plan["betting_decisions"] is False
    for items in plan["provider_mapping_by_sport"].values():
        for item in items:
            assert item["live_call_allowed"] is False
            assert item["production_selectable"] is False
            assert item["betting_decisions_enabled"] is False
            assert item["sanitized_probe_only"] is True

def test_no_credentials_produces_blocked_no_credentials_for_api_sports_family():
    plan = build_provider_mapping_plan({})
    for sport in ["basketball", "volleyball", "hockey", "tennis"]:
        [item] = plan["provider_mapping_by_sport"][sport]
        assert item["provider_key"] == "api-sports-family"
        assert item["status"] == ProviderMappingStatus.BLOCKED_NO_CREDENTIALS
        assert item["missing_env_keys"]

def test_pandascore_is_terms_gated_before_probe_even_if_token_present():
    plan = build_provider_mapping_plan({"PANDASCORE_TOKEN": "secret"})
    for sport in ["cs2", "dota2", "valorant"]:
        [item] = plan["provider_mapping_by_sport"][sport]
        assert item["provider_key"] == "pandascore"
        assert item["status"] == ProviderMappingStatus.BLOCKED_PROVIDER_TERMS_OR_SCOPE
        assert item["blocked_reason"] == "terms_or_access_review_required_before_probe"

def test_api_sports_can_become_mapping_ready_with_sport_specific_key():
    plan = build_provider_mapping_plan({"API_BASKETBALL_KEY": "secret"})
    [basketball] = plan["provider_mapping_by_sport"]["basketball"]
    assert basketball["status"] == ProviderMappingStatus.MAPPING_READY_FOR_SANITIZED_PROBE
    assert basketball["proof_fields_required"]
    assert basketball["sanitized_probe_only"] is True
    assert basketball["production_selectable"] is False

def test_validate_mapping_plan_rejects_live_or_production_flags():
    plan = build_provider_mapping_plan({"API_BASKETBALL_KEY": "secret"})
    assert validate_mapping_plan(plan) == []
    plan["live_calls_allowed"] = True
    assert "live_calls_must_be_false" in validate_mapping_plan(plan)

def test_route_specs_do_not_include_odds_as_proof_fields():
    for spec in default_route_specs():
        assert "odds" not in spec.proof_fields_required
        assert "betting" in spec.forbidden_fields or "prediction" in spec.forbidden_fields

def test_mapping_report_json_is_pretty_and_sorted(tmp_path):
    from bet.enrichment.multisport_foundation.provider_mapping_report import write_provider_mapping_plan
    path = tmp_path / "provider_mapping_plan.json"
    write_provider_mapping_plan(path, env={})
    text = path.read_text()
    assert text.endswith("\n")
    assert "\n  " in text
    loaded = json.loads(text)
    assert loaded["phase_id"] == "MULTISPORT_PASS_E_PROVIDER_MAPPING_CONTRACTS"

def test_verify_provider_mapping_passes():
    res = verify_provider_mapping()
    assert res.verdict == "PASS"
    assert not res.failed_requirements
    assert res.metrics["target_sports_count"] == 7
    assert res.metrics["route_specs_count"] == 7
