"""Test suite for provider revalidation, evidence, and deduplication defects (B07, B08, B09, B10, B11, B14)."""

import hashlib
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
import pytest

from bet.discovery.models import DiscoveredEvent, MergedFixture
from bet.discovery.coordinator import EventDiscoveryCoordinator
from bet.discovery.dedup import DeduplicationEngine
from bet.providers.revalidation import ProviderEventRevalidationService, ProviderRevalidationResult
from bet.discovery.accounting import DiscoveryAccountingEngine, DiscoveryAccountingSummary
from bet.pipeline.provider_observation_evidence import validate_persisted_provider_observation


def test_b07_discovery_deduplication_loses_provider_data():
    """B07: source-level provider status, kickoff and participant data are lost during discovery deduplication."""
    evt = DiscoveredEvent(
        source="api_football",
        external_id="ext_123",
        sport="football",
        competition="Premier League",
        home_team="Arsenal",
        away_team="Chelsea",
        kickoff=datetime(2026, 7, 30, 15, 0, tzinfo=UTC),
        status="NS",
        raw_data={"fixture_id": 123},
    )

    dedup = DeduplicationEngine()
    merged = dedup.deduplicate_events([evt])
    assert len(merged) == 1
    m = merged[0]

    ref = m.sources[0]
    assert getattr(ref, "raw_status", None) == "NS", "B07 defect: raw_status lost in deduplication"
    assert getattr(ref, "raw_kickoff", None) is not None, "B07 defect: raw_kickoff lost in deduplication"
    assert getattr(ref, "raw_home_team", None) == "Arsenal", "B07 defect: raw_home_team lost in deduplication"
    assert getattr(ref, "raw_away_team", None) == "Chelsea", "B07 defect: raw_away_team lost in deduplication"


def test_b08_revalidation_brittle_matching_and_doubleheaders():
    """B08: revalidation relies on brittle home/away/kickoff string matching instead of exact provider event identity."""
    service = ProviderEventRevalidationService()
    available = [
        {"provider": "api_football", "provider_event_id": "p_1", "status": "NS", "kickoff": "2026-07-30T15:00:00Z", "home": "Arsenal", "away": "Chelsea"},
    ]

    res = service.revalidate_exact_event(
        provider="api_football",
        provider_event_id="p_1",
        available_events=available,
    )
    assert res.is_exact_match, "B08 defect: exact provider ID lookup failed"


def test_b09_provider_observed_kickoff_vs_old_db_kickoff():
    """B09: provider-observed kickoff is calculated, but old database kickoff is written into observation evidence."""
    from bet.pipeline.event_runtime_contract import parse_utc_timestamp
    service = ProviderEventRevalidationService()
    db_row = {"canonical_event_id": "evt_1", "fixture_id": 1, "kickoff": "2026-07-30T10:00:00Z"}
    prov_resp = {"provider_event_id": "p_1", "raw_status": "NS", "kickoff": "2026-07-30T15:00:00Z", "home": "Arsenal", "away": "Chelsea"}

    obs = service.build_observation_record(db_row=db_row, provider_response=prov_resp)
    assert parse_utc_timestamp(obs.observed_kickoff_utc) == parse_utc_timestamp("2026-07-30T15:00:00Z"), "B09 defect: old DB kickoff written instead of provider observed kickoff"


def test_b10_persisted_evidence_hash_mismatch(tmp_path):
    """B10: persisted evidence hash may not hash the bytes stored at evidence_path."""
    ev_file = tmp_path / "evidence.json"
    ev_file.write_bytes(b'{"status": "NS"}')

    record = {
        "run_id": "r1",
        "phase": "PLAN",
        "canonical_event_id": "e1",
        "provider": "p1",
        "request_status": "SUCCESS",
    }

    is_ok, msg = validate_persisted_provider_observation(record, ev_file, expected_sha256="0" * 64)
    assert not is_ok, "B10 defect: evidence verification accepted mismatched hash"
    assert "SHA256_MISMATCH" in msg


def test_b11_new_provider_events_discovered_accounting():
    """B11: NEW_PROVIDER_EVENTS_DISCOVERED is calculated from total deduplicated event count rather than genuinely inserted events."""
    engine = DiscoveryAccountingEngine()
    fetched = [
        {"canonical_event_id": "evt_new_1", "provider": "p1", "provider_event_id": "p_1"},
        {"canonical_event_id": "evt_old_2", "provider": "p1", "provider_event_id": "p_2"},
    ]
    summary = engine.calculate_accounting(
        fetched_raw_events=fetched,
        existing_canonical_ids={"evt_old_2"},
        existing_source_refs={("p1", "p_2")},
    )
    assert summary.new_provider_events_discovered == 1, "B11 defect: accounting counted non-new events as new"


def test_b14_failed_or_unsupported_provider_lookup_selected():
    """B14: a failed or unsupported provider lookup can still lead to selection."""
    try:
        from bet.pipeline.launch_bridge import select_eligible_candidates
        selected = select_eligible_candidates(
            candidates=[{"fixture_id": 1, "provider_request_status": "FAILED"}],
        )
        assert len(selected) == 0, "B14 defect: candidate with FAILED provider lookup was selected"
    except (ImportError, AttributeError):
        pytest.fail("B14 defect: select_eligible_candidates missing in production launch_bridge", pytrace=False)
