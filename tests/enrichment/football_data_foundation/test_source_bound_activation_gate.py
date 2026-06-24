import pytest

from bet.enrichment.football_data_foundation.source_bound_activation.contracts import ActivationPolicy
from bet.enrichment.football_data_foundation.source_bound_activation.gate import evaluate_activation_gate


REQUIRED_PROVIDERS = (
    "api-football",
    "football-data-org",
    "espn-baseline",
    "sportdb",
    "highlightly",
)


def make_valid_inputs():
    snapshot = {
        "fixture_slug": "worldcup2026-norway-senegal",
        "provider_ids": {p: "mock_id" for p in REQUIRED_PROVIDERS},
        "provider_fact_counts": {p: 10 for p in REQUIRED_PROVIDERS},
        "score": {"home": 3, "away": 2},
        "conflicts": [],
        "shadow_status": "SHADOW_ENRICHMENT_READY_FOR_MANUAL_REVIEW",
        "production_selectable": False,
        "manual_authorization_required": True,
    }
    verifier = {"verdict": "PASS"}
    provider_fact_counts = {p: 10 for p in REQUIRED_PROVIDERS}
    sqlite_summary = {
        "provider_fact_rows": {p: 10 for p in REQUIRED_PROVIDERS}
    }
    return snapshot, verifier, provider_fact_counts, sqlite_summary


def test_gate_passes_accepted_shadow_bundle() -> None:
    snapshot, verifier, provider_fact_counts, sqlite_summary = make_valid_inputs()
    policy = ActivationPolicy.strict_worldcup_acceptance()
    decision, failures = evaluate_activation_gate(
        fixture_slug="worldcup2026-norway-senegal",
        snapshot=snapshot,
        verifier=verifier,
        provider_fact_counts=provider_fact_counts,
        sqlite_summary=sqlite_summary,
        policy=policy,
    )
    assert not failures
    assert decision.status == "ACTIVATION_CANDIDATE_SHADOW_ONLY"
    assert decision.selectable_for_production is False


def test_gate_fails_if_provider_id_missing() -> None:
    snapshot, verifier, provider_fact_counts, sqlite_summary = make_valid_inputs()
    del snapshot["provider_ids"]["api-football"]
    policy = ActivationPolicy.strict_worldcup_acceptance()
    decision, failures = evaluate_activation_gate(
        fixture_slug="worldcup2026-norway-senegal",
        snapshot=snapshot,
        verifier=verifier,
        provider_fact_counts=provider_fact_counts,
        sqlite_summary=sqlite_summary,
        policy=policy,
    )
    assert "missing_provider_id:api-football" in failures


def test_gate_fails_if_provider_fact_count_zero() -> None:
    snapshot, verifier, provider_fact_counts, sqlite_summary = make_valid_inputs()
    provider_fact_counts["sportdb"] = 0
    policy = ActivationPolicy.strict_worldcup_acceptance()
    decision, failures = evaluate_activation_gate(
        fixture_slug="worldcup2026-norway-senegal",
        snapshot=snapshot,
        verifier=verifier,
        provider_fact_counts=provider_fact_counts,
        sqlite_summary=sqlite_summary,
        policy=policy,
    )
    assert "missing_provider_fact_count:sportdb" in failures


def test_gate_fails_if_sqlite_provider_rows_missing() -> None:
    snapshot, verifier, provider_fact_counts, sqlite_summary = make_valid_inputs()
    sqlite_summary["provider_fact_rows"]["highlightly"] = 0
    policy = ActivationPolicy.strict_worldcup_acceptance()
    decision, failures = evaluate_activation_gate(
        fixture_slug="worldcup2026-norway-senegal",
        snapshot=snapshot,
        verifier=verifier,
        provider_fact_counts=provider_fact_counts,
        sqlite_summary=sqlite_summary,
        policy=policy,
    )
    assert "sqlite_missing_provider_rows:highlightly" in failures


def test_gate_fails_if_score_mismatch_under_strict_acceptance_policy() -> None:
    snapshot, verifier, provider_fact_counts, sqlite_summary = make_valid_inputs()
    snapshot["score"] = {"home": 1, "away": 1}
    policy = ActivationPolicy.strict_worldcup_acceptance()
    decision, failures = evaluate_activation_gate(
        fixture_slug="worldcup2026-norway-senegal",
        snapshot=snapshot,
        verifier=verifier,
        provider_fact_counts=provider_fact_counts,
        sqlite_summary=sqlite_summary,
        policy=policy,
    )
    assert "score_mismatch" in failures


def test_generic_policy_with_expected_score_none_does_not_hardcode_score() -> None:
    snapshot, verifier, provider_fact_counts, sqlite_summary = make_valid_inputs()
    snapshot["score"] = {"home": 1, "away": 1}
    policy = ActivationPolicy(expected_fixture_slug="worldcup2026-norway-senegal", expected_score=None)
    decision, failures = evaluate_activation_gate(
        fixture_slug="worldcup2026-norway-senegal",
        snapshot=snapshot,
        verifier=verifier,
        provider_fact_counts=provider_fact_counts,
        sqlite_summary=sqlite_summary,
        policy=policy,
    )
    assert not failures


def test_gate_fails_if_conflicts_non_empty() -> None:
    snapshot, verifier, provider_fact_counts, sqlite_summary = make_valid_inputs()
    snapshot["conflicts"] = ["conflict details"]
    policy = ActivationPolicy.strict_worldcup_acceptance()
    decision, failures = evaluate_activation_gate(
        fixture_slug="worldcup2026-norway-senegal",
        snapshot=snapshot,
        verifier=verifier,
        provider_fact_counts=provider_fact_counts,
        sqlite_summary=sqlite_summary,
        policy=policy,
    )
    assert "conflicts_present" in failures


def test_gate_fails_if_production_selectable_true() -> None:
    snapshot, verifier, provider_fact_counts, sqlite_summary = make_valid_inputs()
    snapshot["production_selectable"] = True
    policy = ActivationPolicy.strict_worldcup_acceptance()
    decision, failures = evaluate_activation_gate(
        fixture_slug="worldcup2026-norway-senegal",
        snapshot=snapshot,
        verifier=verifier,
        provider_fact_counts=provider_fact_counts,
        sqlite_summary=sqlite_summary,
        policy=policy,
    )
    assert "production_selectable_not_false" in failures


def test_gate_fails_if_manual_authorization_required_false() -> None:
    snapshot, verifier, provider_fact_counts, sqlite_summary = make_valid_inputs()
    snapshot["manual_authorization_required"] = False
    policy = ActivationPolicy.strict_worldcup_acceptance()
    decision, failures = evaluate_activation_gate(
        fixture_slug="worldcup2026-norway-senegal",
        snapshot=snapshot,
        verifier=verifier,
        provider_fact_counts=provider_fact_counts,
        sqlite_summary=sqlite_summary,
        policy=policy,
    )
    assert "manual_authorization_required_not_true" in failures
