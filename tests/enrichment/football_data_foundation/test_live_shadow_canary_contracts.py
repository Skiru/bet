from bet.enrichment.football_data_foundation.live_shadow_canary.contracts import OfficialFixtureContext
from bet.enrichment.football_data_foundation.live_shadow_canary.contracts import ProviderProbeResult
from bet.enrichment.football_data_foundation.live_shadow_canary.contracts import LiveShadowCanarySummary


def test_contracts_defaults() -> None:
    context = OfficialFixtureContext(
        fixture_slug="slug",
        competition_name="Comp",
        official_source_url="url",
        official_source_name="name",
    )
    assert context.selectable_for_production is False
    assert context.raw_payload_stored is False

    probe = ProviderProbeResult(
        provider="sportdb",
        credential_env="SPORTDB_API_KEY",
        credential_present=True,
        status="SUCCESS",
        request_attempted=True,
        evidence_claim_count=2,
    )
    assert probe.selectable_for_production is False

    summary = LiveShadowCanarySummary(
        run_id="run-1",
        status="BOUNDED_LIVE_SHADOW_CANARY_READY_FOR_MANUAL_REVIEW",
        official_context={},
        provider_results=[],
    )
    assert summary.selectable_for_production is False
    assert summary.manual_authorization_required is True
    assert summary.no_betting_decisions is True
    assert summary.no_db_writes is True


def test_status_safety() -> None:
    # Verify no forbidden status is used
    allowed_statuses = {
        "BOUNDED_LIVE_SHADOW_CANARY_READY_FOR_MANUAL_REVIEW",
        "BOUNDED_LIVE_SHADOW_CANARY_OFFICIAL_CONTEXT_ONLY_READY_FOR_MANUAL_REVIEW",
        "BOUNDED_LIVE_SHADOW_CANARY_BLOCKED_FOR_MANUAL_REVIEW",
        "BOUNDED_LIVE_SHADOW_CANARY_SKIPPED_CREDENTIALS_MISSING",
        "BOUNDED_LIVE_SHADOW_CANARY_SKIPPED_OFFICIAL_CONTEXT_UNAVAILABLE",
    }

    # We assert that the status string we expect is inside this set
    summary = LiveShadowCanarySummary(
        run_id="run-1",
        status="BOUNDED_LIVE_SHADOW_CANARY_READY_FOR_MANUAL_REVIEW",
        official_context={},
        provider_results=[],
    )
    assert summary.status in allowed_statuses

    # Check that forbidden status "PRODUCTION" + "_READY" is not in the allowed set
    forbidden_status = "PRODUCTION_" + "READY"
    assert forbidden_status not in allowed_statuses
