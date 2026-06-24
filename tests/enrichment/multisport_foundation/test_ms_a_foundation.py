import json
from pathlib import Path
from bet.enrichment.multisport_foundation.contracts import SportKey, ProofLevel, OutcomeStatus, PassKind
from bet.enrichment.multisport_foundation.profiles import build_sport_profiles
from bet.enrichment.multisport_foundation.providers import build_provider_profiles, provider_matrix
from bet.enrichment.multisport_foundation.plan import build_multisport_wave_plan
from bet.enrichment.multisport_foundation.verifier import verify_plan
from bet.enrichment.multisport_foundation.renderer import render_all, render_master_prompt, render_plan_markdown


def test_all_seven_sport_profiles_exist() -> None:
    profiles = build_sport_profiles()
    assert set(profiles) == set(SportKey)
    assert len(profiles) == 7


def test_each_sport_has_provider_candidates() -> None:
    profiles = build_sport_profiles()
    for sport, profile in profiles.items():
        assert profile.provider_candidates, f"Sport {sport} has no provider candidates."


def test_every_sport_has_required_identity_facts() -> None:
    profiles = build_sport_profiles()
    for sport, profile in profiles.items():
        fact_names = {fact.name for fact in profile.required_facts}
        assert "fixture_identity" in fact_names, f"Sport {sport} missing fixture_identity in required facts."
        assert "participants" in fact_names, f"Sport {sport} missing participants in required facts."
        assert any(fact.required_for_shadow_ready for fact in profile.required_facts), f"Sport {sport} has no mandatory shadow-ready facts."


def test_every_provider_has_allowed_proof_levels_and_https_docs_url() -> None:
    providers = build_provider_profiles()
    for key, provider in providers.items():
        assert provider.allowed_proof_levels, f"Provider {key} has no allowed proof levels."
        assert ProofLevel.NO_PROOF not in provider.allowed_proof_levels, f"Provider {key} has invalid NO_PROOF."
        assert provider.docs_url.startswith("https://"), f"Provider {key} docs url {provider.docs_url} is not HTTPS."


def test_fail_closed_observation_status_is_first_class() -> None:
    plan = build_multisport_wave_plan()
    success_statuses = {
        status for pass_def in plan.passes for status in pass_def.success_statuses
    }
    assert OutcomeStatus.REAL_PROVIDER_ACCESS_OBSERVED_BUT_MAPPING_INSUFFICIENT in success_statuses


def test_no_fake_success_fallback_language_in_plan() -> None:
    plan = build_multisport_wave_plan()
    plan_str = str(plan.to_json()).lower()
    forbidden_terms = [
        "fallback score accepted",
        "fallback provider id accepted",
        "production_ready",
        "betting decision allowed",
    ]
    for term in forbidden_terms:
        assert term not in plan_str, f"Plan contains forbidden term: {term}"


def test_docs_and_reports_are_pretty_multiline() -> None:
    markdown = render_plan_markdown()
    assert "\n" in markdown
    assert "# Multisport Enrichment Wave Plan" in markdown
    assert "## Goals" or "## Goal" in markdown


def test_verifier_passes_production_plan() -> None:
    result = verify_plan()
    assert result.verdict == "PASS"
    assert not result.failed_requirements
    assert result.metrics["sport_count"] == 7
    assert result.metrics["provider_count"] == 6
    assert result.metrics["pass_count"] == 4


def test_renderer_writes_reports_and_master_prompt_contains_all_sports(tmp_path: Path) -> None:
    outputs = render_all(tmp_path)
    for path in outputs.values():
        assert Path(path).exists()

    verifier_data = json.loads(Path(outputs["verifier_json"]).read_text(encoding="utf-8"))
    assert verifier_data["verdict"] == "PASS"

    prompt = render_master_prompt().lower()
    for sport in ["basketball", "volleyball", "hockey", "tennis", "cs2", "dota2", "valorant"]:
        assert sport in prompt
    assert "no production routing activation" in prompt
    assert "public raw line table" in prompt


def test_provider_matrix_coverage() -> None:
    matrix = provider_matrix()
    assert set(matrix) == {sport.value for sport in SportKey}
    for sport_value, providers in matrix.items():
        assert providers, f"Sport {sport_value} has empty provider matrix coverage."
