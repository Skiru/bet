from __future__ import annotations

import json
from pathlib import Path

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
    validate_evidence_identity,
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

FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "fixtures/football_data_foundation"


def load_fixture(name: str) -> dict[str, object]:
    return json.loads((FIXTURE_ROOT / name).read_text(encoding="utf-8"))


@pytest.fixture
def scoreboard_payload() -> dict[str, object]:
    return load_fixture("espn_world_cup_usa_australia_scoreboard.json")


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


def build_provider_evidence() -> dict[str, dict[str, object]]:
    common_event = {
        "provider_event_id": "760442",
        "event_date_utc": "2026-06-19T19:00Z",
        "event_date_local": "2026-06-19T21:00:00+02:00",
        "home_team_name": "United States",
        "home_team_code": "USA",
        "away_team_name": "Australia",
        "away_team_code": "AUS",
        "status_name": "STATUS_SECOND_HALF",
        "status_state": "in",
        "retrieval_timestamp_utc": "2026-06-19T20:18:51+00:00",
    }
    return {
        "current_discovery": {
            "provider_id": "espn-fifa-worldcup",
            "provider_event_id": "760442",
            "evidence_identity": "1f8cdb0748846c1cec8b312ad47f5607b116e3c17a56eb32a8f0ac6f537c73b0",
            "schema_fingerprint": "1adbcb1991fbe027d188ffc1f3241a1a555f26d209df871e6c58c36d47828839",
            "retrieved_at": "2026-06-19T20:18:51+00:00",
            "event": {
                **common_event,
                "venue_name": "Lumen Field",
                "venue_city": "Seattle, Washington",
                "venue_country": "USA",
                "broadcasts": ["FOX", "Tele", "FOX One"],
                "score_home": 2,
                "score_away": 0,
            },
        },
        "current_form": {
            "provider_id": "espn-fifa-worldcup",
            "provider_event_id": "760442",
            "evidence_identity": "f5963336e643f2d5b8311475147031730d4f56f5ed9ee3aa66d2e4ef641f0d91",
            "schema_fingerprint": "1adbcb1991fbe027d188ffc1f3241a1a555f26d209df871e6c58c36d47828839",
            "retrieved_at": "2026-06-19T20:18:51+00:00",
            "event": {
                **common_event,
                "team_records": [
                    {
                        "home_away": "home",
                        "team_name": "United States",
                        "team_code": "USA",
                        "team_record_summary": "1-0-0",
                        "records": [{"name": "total", "summary": "1-0-0"}],
                    },
                    {
                        "home_away": "away",
                        "team_name": "Australia",
                        "team_code": "AUS",
                        "team_record_summary": "1-0-0",
                        "records": [{"name": "total", "summary": "1-0-0"}],
                    },
                ],
            },
        },
        "detailed_metrics": {
            "provider_id": "espn-fifa-worldcup",
            "provider_event_id": "760442",
            "evidence_identity": "b8fa6502f7bd73a0d9614dc0e04e4e8de97505c7de2b4b476dbb5ebf69485f71",
            "schema_fingerprint": "1adbcb1991fbe027d188ffc1f3241a1a555f26d209df871e6c58c36d47828839",
            "retrieved_at": "2026-06-19T20:18:51+00:00",
            "event": {
                **common_event,
                "statistics": [
                    {
                        "home_away": "home",
                        "name": "possessionPct",
                        "display_value": "71.5",
                        "value": 71.5,
                    },
                    {
                        "home_away": "home",
                        "name": "shotsOnTarget",
                        "display_value": "2",
                        "value": 2,
                    },
                    {
                        "home_away": "home",
                        "name": "totalShots",
                        "display_value": "11",
                        "value": 11,
                    },
                    {
                        "home_away": "away",
                        "name": "possessionPct",
                        "display_value": "28.5",
                        "value": 28.5,
                    },
                    {
                        "home_away": "away",
                        "name": "shotsOnTarget",
                        "display_value": "1",
                        "value": 1,
                    },
                    {
                        "home_away": "away",
                        "name": "totalShots",
                        "display_value": "2",
                        "value": 2,
                    },
                ],
            },
        },
    }


def seed_provider_evidence(state_store: FileEnrichmentStateStore) -> None:
    for capability, payload in build_provider_evidence().items():
        state_store.put_evidence(f"espn-fifa-worldcup_{capability}_evidence", payload)


def build_request(
    scanner_event: ScannerEventCandidate,
    *,
    capabilities: tuple[str, ...] = (
        "current_discovery",
        "detailed_metrics",
        "current_form",
    ),
    force_refresh: bool = False,
) -> ActiveEnrichmentRequest:
    return ActiveEnrichmentRequest(
        profile_id=scanner_event.profile_id,
        scanner_event_candidate=scanner_event,
        canonical_match_identity={
            "home_team": scanner_event.home_team_name,
            "away_team": scanner_event.away_team_name,
        },
        canonical_competition_scope=scanner_event.canonical_competition_scope,
        canonical_season_scope=scanner_event.canonical_season_scope,
        requested_capabilities=capabilities,
        force_refresh=force_refresh,
    )


def test_competition_profile_exists() -> None:
    profile = get_competition_profile("world-cup-2026")
    assert profile.profile_id == "world-cup-2026"
    assert profile.canonical_scope.sport == "football"


def test_scanner_event_is_input_only(scanner_event: ScannerEventCandidate) -> None:
    assert scanner_event.scanner_source == "acceptance_fixture_seed"
    assert not hasattr(scanner_event, "evidence_identity")


def test_mock_espn_scoreboard_parser_uses_real_provider_event_id(
    scoreboard_payload: dict[str, object],
    scanner_event: ScannerEventCandidate,
) -> None:
    events = parse_espn_scoreboard_payload(scoreboard_payload, scanner_event)
    assert len(events) == 1
    event = events[0]
    assert event.scanner_event_id == scanner_event.scanner_event_id
    assert event.provider_event_id == "760442"
    assert event.provider_event_id != scanner_event.scanner_event_id
    assert event.status_state == "in"
    assert event.score_home == 2
    assert event.score_away == 0
    assert any(stat["name"] == "possessionPct" for stat in event.statistics)


def test_verify_endpoint_preserves_scanner_and_provider_identity(
    scoreboard_payload: dict[str, object],
    scanner_event: ScannerEventCandidate,
) -> None:
    request = EndpointVerificationRequest(
        profile_id="world-cup-2026",
        provider_id="espn-fifa-worldcup",
        endpoint_url="https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard",
        canonical_competition_scope="football:world:8/world-championship:lvUBR5F8",
        canonical_season_scope="2026",
        scanner_event_candidate=scanner_event,
        expected_shape={"events": []},
    )
    result = verify_endpoint(request, mock_payload=scoreboard_payload)
    assert result.status == "ENDPOINT_VERIFIED"
    assert (
        validate_evidence_identity(result.evidence_identity) == result.evidence_identity
    )
    assert result.retrieval_timestamp_utc != scanner_event.kickoff_utc
    assert result.diagnostics["matched_event_count"] == 1
    assert result.events[0].scanner_event_id == scanner_event.scanner_event_id
    assert result.events[0].provider_event_id == "760442"


def test_event_identity_matches_by_team_time_scope_not_id(
    scanner_event: ScannerEventCandidate,
) -> None:
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
        provider_event_id="760442",
        kickoff_utc="2026-06-19T19:00:00Z",
        kickoff_local="2026-06-19T21:00:00+02:00",
        home_team_name="United States",
        home_team_code="USA",
        away_team_name="Australia",
        away_team_code="AUS",
        canonical_competition_scope=scanner_event.canonical_competition_scope,
        canonical_season_scope=scanner_event.canonical_season_scope,
        evidence_identity="1f8cdb0748846c1cec8b312ad47f5607b116e3c17a56eb32a8f0ac6f537c73b0",
        status_name="STATUS_SECOND_HALF",
        status_state="in",
    )
    result = match_identities(seed, [provider_identity])
    assert result.identity_status == "IDENTITY_CONFIRMED"
    assert result.scanner_event_id == "66456944"
    assert result.matched_provider_ids == ("espn-fifa-worldcup",)
    assert result.matched_provider_events[0]["provider_event_id"] == "760442"
    assert result.timezone_conversion_notes


def test_invalid_evidence_identity_with_spaces_fails() -> None:
    with pytest.raises(ValueError):
        validate_evidence_identity(
            "1f8cdb0748846c1cec8b312ad47f5607 b116e3c17a56eb32a8f0ac6f537c73b0"
        )


def test_completeness_state_decisions() -> None:
    requirement = EnrichmentCapabilityRequirement(
        capability="current_discovery",
        required_for_profile=True,
        freshness_ttl_seconds=1800,
        heavy_fetch=False,
        provider_priority=("espn-fifa-worldcup",),
    )
    decision_empty = make_fetch_decision(requirement, None)
    assert decision_empty.decision == "FETCH_REQUIRED"

    record_fresh = EnrichmentCompletenessRecord(
        profile_id="world-cup-2026",
        canonical_entity_id="66456944",
        entity_type="fixture",
        capability="current_discovery",
        provider_id="espn-fifa-worldcup",
        evidence_identity="1f8cdb0748846c1cec8b312ad47f5607b116e3c17a56eb32a8f0ac6f537c73b0",
        schema_fingerprint="schema-fp",
        last_verified_at="2026-06-19T20:18:51+00:00",
        last_enriched_at="2026-06-19T20:18:51+00:00",
        completeness_status="COMPLETE_FRESH",
    )
    assert make_fetch_decision(requirement, record_fresh).decision == "REUSE_CACHED"
    assert (
        make_fetch_decision(requirement, record_fresh, force_refresh=True).decision
        == "FETCH_FORCED"
    )


def test_active_enrichment_empty_store_cannot_complete(
    scanner_event: ScannerEventCandidate, tmp_path: Path
) -> None:
    state_store = FileEnrichmentStateStore(tmp_path / "state_store")
    result = ActiveEnrichmentOrchestrator(state_store).enrich_event(
        build_request(scanner_event)
    )
    assert result.status == "ENRICH_FAILED_CLOSED"
    assert not result.facts
    assert result.unavailable_capabilities


def test_active_enrichment_extracts_real_facts_without_placeholders(
    scanner_event: ScannerEventCandidate, tmp_path: Path
) -> None:
    state_store = FileEnrichmentStateStore(tmp_path / "state_store")
    seed_provider_evidence(state_store)
    orchestrator = ActiveEnrichmentOrchestrator(state_store)

    result = orchestrator.enrich_event(build_request(scanner_event))
    assert result.status == "ENRICHED_COMPLETE"
    assert all(f.provider_event_id == "760442" for f in result.facts)
    assert all(f.fact_value_text != "VERIFIED_SCHEDULED" for f in result.facts)
    assert any(
        f.fact_name == "event_status_state" and f.fact_value_text == "in"
        for f in result.facts
    )
    assert any(
        f.fact_name == "home_team_record_summary" and f.fact_value_text == "1-0-0"
        for f in result.facts
    )
    assert any(
        f.fact_name == "home_totalShots" and f.fact_value_num == 11.0
        for f in result.facts
    )


def test_reuse_store_uses_real_cached_evidence(
    scanner_event: ScannerEventCandidate, tmp_path: Path
) -> None:
    state_store = FileEnrichmentStateStore(tmp_path / "state_store")
    seed_provider_evidence(state_store)
    orchestrator = ActiveEnrichmentOrchestrator(state_store)
    orchestrator.enrich_event(build_request(scanner_event))

    result = orchestrator.enrich_event(build_request(scanner_event))
    assert result.status == "ENRICHED_COMPLETE"
    assert {decision.decision for decision in result.fetch_decisions} == {
        "REUSE_CACHED"
    }
    assert all(f.provider_event_id == "760442" for f in result.facts)


def test_force_refresh_bypasses_completeness_and_revalidates(
    scanner_event: ScannerEventCandidate, tmp_path: Path
) -> None:
    state_store = FileEnrichmentStateStore(tmp_path / "state_store")
    seed_provider_evidence(state_store)
    orchestrator = ActiveEnrichmentOrchestrator(state_store)
    orchestrator.enrich_event(build_request(scanner_event))

    result = orchestrator.enrich_event(build_request(scanner_event, force_refresh=True))
    assert result.status == "ENRICHED_COMPLETE"
    assert {decision.decision for decision in result.fetch_decisions} == {
        "FETCH_FORCED"
    }


def test_invalid_cached_evidence_identity_blocks_enrichment(
    scanner_event: ScannerEventCandidate, tmp_path: Path
) -> None:
    state_store = FileEnrichmentStateStore(tmp_path / "state_store")
    payload = build_provider_evidence()["current_discovery"]
    payload["evidence_identity"] = "invalid evidence id"
    state_store.put_evidence("espn-fifa-worldcup_current_discovery_evidence", payload)

    result = ActiveEnrichmentOrchestrator(state_store).enrich_event(
        build_request(scanner_event, capabilities=("current_discovery",))
    )
    assert result.status == "ENRICH_FAILED_CLOSED"
    assert result.unavailable_capabilities[0]["reason"] == "invalid_evidence_identity"
