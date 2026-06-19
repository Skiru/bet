from __future__ import annotations

from datetime import UTC, datetime

import pytest

from bet.enrichment.football_data_foundation.active_enrichment import (
    ActiveEnrichmentOrchestrator,
    ActiveEnrichmentRequest,
)
from bet.enrichment.football_data_foundation.competition_profiles import (
    get_competition_profile,
)
from bet.enrichment.football_data_foundation.endpoint_verification import (
    EndpointVerificationRequest,
    parse_espn_scoreboard_payload,
    verify_endpoint,
)
from bet.enrichment.football_data_foundation.enrichment_state import (
    EnrichmentCapabilityRequirement,
    EnrichmentCompletenessRecord,
    FileEnrichmentStateStore,
    make_fetch_decision,
)
from bet.enrichment.football_data_foundation.event_identity import (
    IdentitySeed,
    ProviderEventIdentity,
    match_identities,
)
from bet.enrichment.football_data_foundation.scanner_contracts import (
    ScannerEventCandidate,
)


@pytest.fixture
def scanner_event() -> ScannerEventCandidate:
    return ScannerEventCandidate(
        scanner_event_id="66456944",
        profile_id="world-cup-2026",
        sport="football",
        canonical_competition_scope="football:world:8/world-championship:lvUBR5F8",
        canonical_season_scope="2026",
        kickoff_local="2026-06-19T21:00:00+02:00",
        kickoff_utc="2026-06-19T19:00:00Z",
        home_team_name="United States",
        home_team_code="USA",
        away_team_name="Australia",
        away_team_code="AUS",
        group_label="Group D",
        scanner_source="acceptance_fixture_seed",
        scanner_truth_kind="schedule_snapshot",
        scanner_confidence="high",
    )


def test_competition_profile_exists():
    profile = get_competition_profile("world-cup-2026")
    assert profile.profile_id == "world-cup-2026"
    assert profile.canonical_scope.sport == "football"
    assert (
        profile.canonical_scope.competition_scope
        == "football:world:8/world-championship:lvUBR5F8"
    )


def test_unknown_profile_fails_closed():
    with pytest.raises(KeyError):
        get_competition_profile("unknown-profile")


def test_future_profiles_represented():
    # Tennis
    tennis_profile = get_competition_profile("example-tennis-tournament-profile")
    assert tennis_profile.canonical_scope.sport == "tennis"

    # Esports
    esports_profile = get_competition_profile("example-esports-match-profile")
    assert esports_profile.canonical_scope.sport == "esports"


def test_scanner_event_to_enrichment_request(scanner_event):
    request = ActiveEnrichmentRequest(
        profile_id=scanner_event.profile_id,
        scanner_event_candidate=scanner_event,
        canonical_match_identity={
            "home_team": scanner_event.home_team_name,
            "away_team": scanner_event.away_team_name,
        },
        canonical_competition_scope=scanner_event.canonical_competition_scope,
        canonical_season_scope=scanner_event.canonical_season_scope,
        requested_capabilities=("current_discovery", "detailed_metrics"),
    )
    assert request.profile_id == "world-cup-2026"
    assert request.scanner_event_candidate.scanner_event_id == "66456944"


def test_scanner_event_cannot_be_used_as_evidence(scanner_event):
    # Scanner event is only an input seed triggering the request, it doesn't carry evidence identities
    assert scanner_event.scanner_source == "acceptance_fixture_seed"
    assert not hasattr(scanner_event, "evidence_identity")


def test_mock_espn_scoreboard_parser():
    mock_payload = {
        "events": [
            {
                "id": "66456944",
                "date": "2026-06-19T19:00:00Z",
                "name": "United States vs Australia",
                "shortName": "USA @ AUS",
                "competitions": [
                    {
                        "id": "1",
                        "status": {
                            "type": {
                                "name": "STATUS_SCHEDULED",
                                "state": "pre",
                                "completed": False,
                            }
                        },
                        "competitors": [
                            {
                                "id": "1",
                                "homeAway": "home",
                                "team": {
                                    "name": "United States",
                                    "abbreviation": "USA",
                                    "id": "home_1",
                                },
                                "records": [{"name": "overall", "summary": "1-0"}],
                            },
                            {
                                "id": "2",
                                "homeAway": "away",
                                "team": {
                                    "name": "Australia",
                                    "abbreviation": "AUS",
                                    "id": "away_2",
                                },
                                "records": [{"name": "overall", "summary": "0-1"}],
                            },
                        ],
                        "venue": {
                            "fullName": "MetLife Stadium",
                            "address": {"city": "East Rutherford", "country": "USA"},
                        },
                        "broadcasts": [{"names": ["FOX"]}],
                    }
                ],
            }
        ]
    }
    events = parse_espn_scoreboard_payload(mock_payload)
    assert len(events) == 1
    ev = events[0]
    assert ev.provider_event_id == "66456944"
    assert ev.home_team_name == "United States"
    assert ev.home_team_code == "USA"
    assert ev.away_team_name == "Australia"
    assert ev.away_team_code == "AUS"
    assert ev.venue_name == "MetLife Stadium"
    assert ev.broadcasts == ("FOX",)


def test_verify_endpoint_schema_mismatch():
    req = EndpointVerificationRequest(
        profile_id="world-cup-2026",
        provider_id="espn-fifa-worldcup",
        endpoint_url="https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard",
        canonical_competition_scope="football:world:8/world-championship:lvUBR5F8",
        canonical_season_scope="2026",
        expected_shape={"missing_key": []},
    )
    res = verify_endpoint(req, mock_payload={"events": []})
    assert res.status == "ENDPOINT_SCHEMA_ERROR"


def test_event_identity_matching(scanner_event):
    seed = IdentitySeed(
        profile_id=scanner_event.profile_id,
        fixture_seed_id=scanner_event.scanner_event_id,
        canonical_competition_scope=scanner_event.canonical_competition_scope,
        canonical_season_scope=scanner_event.canonical_season_scope,
        kickoff_local=scanner_event.kickoff_local,
        kickoff_utc=scanner_event.kickoff_utc,
        home_team_name=scanner_event.home_team_name,
        home_team_code=scanner_event.home_team_code,
        away_team_name=scanner_event.away_team_name,
        away_team_code=scanner_event.away_team_code,
    )

    provider_identity = ProviderEventIdentity(
        profile_id="world-cup-2026",
        provider_id="espn-fifa-worldcup",
        provider_event_id="66456944",
        kickoff_utc="2026-06-19T19:00:00Z",
        kickoff_local="2026-06-19T21:00:00+02:00",
        home_team_name="United States",
        home_team_code="USA",
        away_team_name="Australia",
        away_team_code="AUS",
        evidence_identity="mock-evidence-id",
    )

    result = match_identities(seed, [provider_identity])
    assert result.identity_status == "IDENTITY_CONFIRMED"
    assert result.matched_provider_ids == ("espn-fifa-worldcup",)


def test_event_identity_matching_tolerance(scanner_event):
    seed = IdentitySeed(
        profile_id=scanner_event.profile_id,
        fixture_seed_id=scanner_event.scanner_event_id,
        canonical_competition_scope=scanner_event.canonical_competition_scope,
        canonical_season_scope=scanner_event.canonical_season_scope,
        kickoff_local=scanner_event.kickoff_local,
        kickoff_utc=scanner_event.kickoff_utc,
        home_team_name=scanner_event.home_team_name,
        home_team_code=scanner_event.home_team_code,
        away_team_name=scanner_event.away_team_name,
        away_team_code=scanner_event.away_team_code,
    )

    # 4 hours kickoff difference (should pass since tolerance is 5 hours)
    provider_identity_4h = ProviderEventIdentity(
        profile_id="world-cup-2026",
        provider_id="espn-fifa-worldcup",
        provider_event_id="66456944",
        kickoff_utc="2026-06-19T23:00:00Z",
        kickoff_local="2026-06-20T01:00:00+02:00",
        home_team_name="United States",
        home_team_code="USA",
        away_team_name="Australia",
        away_team_code="AUS",
    )

    result_4h = match_identities(seed, [provider_identity_4h])
    assert result_4h.identity_status == "IDENTITY_CONFIRMED"

    # 6 hours kickoff difference (should fail since tolerance is 5 hours)
    provider_identity_6h = ProviderEventIdentity(
        profile_id="world-cup-2026",
        provider_id="espn-fifa-worldcup",
        provider_event_id="66456944",
        kickoff_utc="2026-06-20T01:00:00Z",
        kickoff_local="2026-06-20T03:00:00+02:00",
        home_team_name="United States",
        home_team_code="USA",
        away_team_name="Australia",
        away_team_code="AUS",
    )

    result_6h = match_identities(seed, [provider_identity_6h])
    assert result_6h.identity_status == "IDENTITY_MISMATCH"


def test_completeness_state_decisions():
    requirement = EnrichmentCapabilityRequirement(
        capability="current_discovery",
        required_for_profile=True,
        freshness_ttl_seconds=1800,
        heavy_fetch=False,
        provider_priority=("espn",),
    )

    # Empty completeness => FETCH_REQUIRED
    decision_empty = make_fetch_decision(requirement, None)
    assert decision_empty.decision == "FETCH_REQUIRED"

    # Fresh completeness => REUSE_CACHED
    record_fresh = EnrichmentCompletenessRecord(
        profile_id="world-cup-2026",
        canonical_entity_id="66456944",
        entity_type="fixture",
        capability="current_discovery",
        provider_id="espn",
        evidence_identity="ev-id",
        schema_fingerprint="schema-fp",
        last_verified_at=datetime.now(UTC).isoformat(),
        last_enriched_at=datetime.now(UTC).isoformat(),
        completeness_status="COMPLETE_FRESH",
    )
    decision_fresh = make_fetch_decision(requirement, record_fresh)
    assert decision_fresh.decision == "REUSE_CACHED"

    # Bypassed completeness / Force refresh => FETCH_FORCED
    decision_force = make_fetch_decision(requirement, record_fresh, force_refresh=True)
    assert decision_force.decision == "FETCH_FORCED"

    # Unsupported provider => SKIP_UNSUPPORTED
    record_unsupported = EnrichmentCompletenessRecord(
        profile_id="world-cup-2026",
        canonical_entity_id="66456944",
        entity_type="fixture",
        capability="current_discovery",
        provider_id="espn",
        evidence_identity=None,
        schema_fingerprint=None,
        last_verified_at=None,
        last_enriched_at=None,
        completeness_status="PROVIDER_UNSUPPORTED",
    )
    decision_unsupported = make_fetch_decision(requirement, record_unsupported)
    assert decision_unsupported.decision == "SKIP_UNSUPPORTED"


def test_active_enrichment_fails_closed_on_missing_evidence(scanner_event, tmp_path):
    state_store = FileEnrichmentStateStore(tmp_path / "state_store")
    orchestrator = ActiveEnrichmentOrchestrator(state_store)

    request = ActiveEnrichmentRequest(
        profile_id=scanner_event.profile_id,
        scanner_event_candidate=scanner_event,
        canonical_match_identity={
            "home_team": scanner_event.home_team_name,
            "away_team": scanner_event.away_team_name,
        },
        canonical_competition_scope=scanner_event.canonical_competition_scope,
        canonical_season_scope=scanner_event.canonical_season_scope,
        requested_capabilities=(
            "current_discovery",
            "detailed_metrics",
            "current_form",
        ),
        force_refresh=False,
    )

    # Empty store and zero mocked evidence -> fails closed (ENRICH_FAILED_CLOSED) with empty facts list
    result = orchestrator.enrich_event(request)
    assert result.status == "ENRICH_FAILED_CLOSED"
    assert len(result.facts) == 0


def test_independent_review_payload(scanner_event, tmp_path):
    state_store = FileEnrichmentStateStore(tmp_path / "state_store")
    orchestrator = ActiveEnrichmentOrchestrator(state_store)

    # Seed mock evidence
    state_store.put_evidence(
        "espn-fifa-worldcup_current_discovery_evidence",
        {
            "provider_id": "espn-fifa-worldcup",
            "event": {
                "id": "66456944",
                "date": "2026-06-19T19:00:00Z",
                "home_team_name": "United States",
                "home_team_code": "USA",
                "away_team_name": "Australia",
                "away_team_code": "AUS",
            },
        },
    )

    request = ActiveEnrichmentRequest(
        profile_id=scanner_event.profile_id,
        scanner_event_candidate=scanner_event,
        canonical_match_identity={
            "home_team": scanner_event.home_team_name,
            "away_team": scanner_event.away_team_name,
        },
        canonical_competition_scope=scanner_event.canonical_competition_scope,
        canonical_season_scope=scanner_event.canonical_season_scope,
        requested_capabilities=("current_discovery",),
        force_refresh=False,
    )

    result = orchestrator.enrich_event(request)
    assert result.status == "ENRICHED_COMPLETE"
    assert len(result.facts) == 1

    # Verify fact contents
    f = result.facts[0]
    assert f.profile_id == "world-cup-2026"
    assert f.capability == "current_discovery"
    assert f.fact_value_text == "VERIFIED_SCHEDULED"
    assert f.provider_id == "espn-fifa-worldcup"
    assert f.evidence_identity == "evidence_espn-fifa-worldcup_current_discovery"
