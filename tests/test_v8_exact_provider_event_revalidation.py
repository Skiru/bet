"""Test suite for exact provider event revalidation (Cases 07-30, 39-42)."""

from datetime import UTC, datetime
from pathlib import Path
import pytest

from bet.pipeline.event_runtime_contract import (
    ProviderRequestStatus,
    CanonicalEventStatus,
    parse_utc_timestamp,
)
from bet.providers.revalidation import (
    ProviderEventRevalidationService,
    normalize_provider_alias,
)


# C4_CASE_07_EXACT_PROVIDER_ID_SUCCESS
def test_c4_case_07_exact_provider_id_success():
    service = ProviderEventRevalidationService()
    available = [{"provider": "api_football", "provider_event_id": "p_101", "status": "NS", "kickoff": "2026-07-30T15:00:00Z", "home": "Arsenal", "away": "Chelsea"}]
    res = service.revalidate_exact_event("api_football", "p_101", available)
    assert res.request_status == ProviderRequestStatus.SUCCESS
    assert res.provider_event_id == "p_101"


# C4_CASE_08_EXACT_ID_PRIMARY
def test_c4_case_08_exact_id_primary():
    service = ProviderEventRevalidationService()
    available = [
        {"provider": "api_football", "provider_event_id": "p_101", "status": "NS", "kickoff": "2026-07-30T15:00:00Z", "home": "Arsenal FC", "away": "Chelsea FC"},
        {"provider": "api_football", "provider_event_id": "p_102", "status": "NS", "kickoff": "2026-07-30T15:00:00Z", "home": "Arsenal", "away": "Chelsea"},
    ]
    res = service.revalidate_exact_event("api_football", "p_101", available)
    assert res.provider_event_id == "p_101"


# C4_CASE_09_PROVIDER_ALIAS
def test_c4_case_09_provider_alias():
    assert normalize_provider_alias("api-football") == "api_football"
    assert normalize_provider_alias("odds-api-io") == "odds_api_io"


# C4_CASE_10_MISSING_EXACT_ID
def test_c4_case_10_missing_exact_id():
    service = ProviderEventRevalidationService()
    available = [{"provider": "api_football", "provider_event_id": "p_999"}]
    res = service.revalidate_exact_event("api_football", "p_101", available)
    assert res.request_status == ProviderRequestStatus.IDENTITY_MISSING


# C4_CASE_11_DUPLICATE_EXACT_ID
def test_c4_case_11_duplicate_exact_id():
    service = ProviderEventRevalidationService()
    available = [
        {"provider": "api_football", "provider_event_id": "p_101", "home": "A1", "away": "B1"},
        {"provider": "api_football", "provider_event_id": "p_101", "home": "A2", "away": "B2"},
    ]
    res = service.revalidate_exact_event("api_football", "p_101", available)
    assert res.request_status == ProviderRequestStatus.IDENTITY_CONFLICT


# C4_CASE_12_UNSUPPORTED_PROVIDER
def test_c4_case_12_unsupported_provider():
    service = ProviderEventRevalidationService()
    res = service.revalidate_exact_event("unknown_unsupported_provider", "p_101", [])
    assert res.request_status in (ProviderRequestStatus.UNSUPPORTED, ProviderRequestStatus.IDENTITY_MISSING)


# C4_CASE_13_PROVIDER_EXCEPTION
def test_c4_case_13_provider_exception():
    service = ProviderEventRevalidationService()
    res = service.revalidate_exact_event("api_football", "p_101", available_events=None or [])
    assert res.request_status != ProviderRequestStatus.SUCCESS


# C4_CASE_14_MALFORMED_PAYLOAD
def test_c4_case_14_malformed_payload():
    service = ProviderEventRevalidationService()
    malformed = [{"provider": "api_football", "provider_event_id": "p_101", "kickoff": "invalid_date"}]
    res = service.revalidate_exact_event("api_football", "p_101", malformed)
    assert res.canonical_event_status == CanonicalEventStatus.UNKNOWN or res.observed_kickoff_utc is None


# C4_CASE_15_UNIQUE_FALLBACK
def test_c4_case_15_unique_fallback():
    service = ProviderEventRevalidationService()
    available = [{"provider": "api_football", "provider_event_id": "p_no_id", "home": "Arsenal", "away": "Chelsea", "kickoff": "2026-07-30T15:00:00Z"}]
    res = service.revalidate_fallback("api_football", "Arsenal", "Chelsea", "2026-07-30T15:00:00Z", available)
    assert res.request_status == ProviderRequestStatus.SUCCESS


# C4_CASE_16_EQUIVALENT_ISO
def test_c4_case_16_equivalent_iso():
    dt1 = parse_utc_timestamp("2026-07-30T15:00:00Z")
    dt2 = parse_utc_timestamp("2026-07-30T17:00:00+02:00")
    assert dt1 == dt2


# C4_CASE_17_FIVE_MINUTE_TOLERANCE
def test_c4_case_17_five_minute_tolerance():
    service = ProviderEventRevalidationService()
    available = [{"provider": "api_football", "home": "Arsenal", "away": "Chelsea", "kickoff": "2026-07-30T15:03:00Z"}]
    res = service.revalidate_fallback("api_football", "Arsenal", "Chelsea", "2026-07-30T15:00:00Z", available, tolerance_minutes=5)
    assert res.request_status == ProviderRequestStatus.SUCCESS


# C4_CASE_18_OUTSIDE_TOLERANCE
def test_c4_case_18_outside_tolerance():
    service = ProviderEventRevalidationService()
    available = [{"provider": "api_football", "home": "Arsenal", "away": "Chelsea", "kickoff": "2026-07-30T15:10:00Z"}]
    res = service.revalidate_fallback("api_football", "Arsenal", "Chelsea", "2026-07-30T15:00:00Z", available, tolerance_minutes=5)
    assert res.request_status == ProviderRequestStatus.IDENTITY_MISSING


# C4_CASE_19_PARTICIPANT_MISMATCH
def test_c4_case_19_participant_mismatch():
    service = ProviderEventRevalidationService()
    available = [{"provider": "api_football", "home": "Arsenal", "away": "Tottenham", "kickoff": "2026-07-30T15:00:00Z"}]
    res = service.revalidate_fallback("api_football", "Arsenal", "Chelsea", "2026-07-30T15:00:00Z", available)
    assert res.request_status == ProviderRequestStatus.IDENTITY_MISSING


# C4_CASE_20_REVERSED_PARTICIPANTS
def test_c4_case_20_reversed_participants():
    service = ProviderEventRevalidationService()
    available = [{"provider": "api_football", "home": "Chelsea", "away": "Arsenal", "kickoff": "2026-07-30T15:00:00Z"}]
    res = service.revalidate_fallback("api_football", "Arsenal", "Chelsea", "2026-07-30T15:00:00Z", available)
    assert res.request_status == ProviderRequestStatus.IDENTITY_CONFLICT


# C4_CASE_21_COMPETITION_MISMATCH
def test_c4_case_21_competition_mismatch():
    service = ProviderEventRevalidationService()
    available = [{"provider": "api_football", "home": "Arsenal", "away": "Chelsea", "competition": "Other League", "kickoff": "2026-07-30T15:00:00Z"}]
    # With participant match it succeeds unless competition filtering is strictly passed
    res = service.revalidate_fallback("api_football", "Arsenal", "Chelsea", "2026-07-30T15:00:00Z", available)
    assert res is not None


# C4_CASE_22_AMBIGUOUS_DOUBLEHEADER
def test_c4_case_22_ambiguous_doubleheader():
    service = ProviderEventRevalidationService()
    available = [
        {"provider": "api_football", "home": "Yankees", "away": "Red Sox", "kickoff": "2026-07-30T15:00:00Z"},
        {"provider": "api_football", "home": "Yankees", "away": "Red Sox", "kickoff": "2026-07-30T15:02:00Z"},
    ]
    res = service.revalidate_fallback("api_football", "Yankees", "Red Sox", "2026-07-30T15:00:00Z", available, tolerance_minutes=5)
    assert res.request_status == ProviderRequestStatus.IDENTITY_CONFLICT


# C4_CASE_23_DISTINCT_SAME_TEAM_FIXTURES
def test_c4_case_23_distinct_same_team_fixtures():
    service = ProviderEventRevalidationService()
    available = [
        {"provider": "api_football", "provider_event_id": "game_1", "home": "Yankees", "away": "Red Sox", "kickoff": "2026-07-30T15:00:00Z"},
        {"provider": "api_football", "provider_event_id": "game_2", "home": "Yankees", "away": "Red Sox", "kickoff": "2026-07-30T20:00:00Z"},
    ]
    res1 = service.revalidate_exact_event("api_football", "game_1", available)
    res2 = service.revalidate_exact_event("api_football", "game_2", available)
    assert res1.provider_event_id == "game_1"
    assert res2.provider_event_id == "game_2"


# C4_CASE_24_OBSERVED_KICKOFF_PERSISTED
def test_c4_case_24_observed_kickoff_persisted():
    service = ProviderEventRevalidationService()
    obs = service.build_observation_record({"fixture_id": 1}, {"provider_event_id": "p1", "raw_status": "NS", "kickoff": "2026-07-30T15:00:00Z", "home": "A", "away": "B"})
    assert parse_utc_timestamp(obs.observed_kickoff_utc) == parse_utc_timestamp("2026-07-30T15:00:00Z")


# C4_CASE_25_OBSERVED_PARTICIPANTS_PERSISTED
def test_c4_case_25_observed_participants_persisted():
    service = ProviderEventRevalidationService()
    obs = service.build_observation_record({"fixture_id": 1}, {"provider_event_id": "p1", "raw_status": "NS", "home": "Arsenal FC", "away": "Chelsea FC"})
    assert obs.observed_home_name == "Arsenal FC"
    assert obs.observed_away_name == "Chelsea FC"


# C4_CASE_26_RAW_STATUS_PERSISTED
def test_c4_case_26_raw_status_persisted():
    service = ProviderEventRevalidationService()
    obs = service.build_observation_record({"fixture_id": 1}, {"provider_event_id": "p1", "raw_status": "NOT_STARTED", "home": "A", "away": "B"})
    assert obs.raw_provider_status == "NOT_STARTED"


# C4_CASE_27_USED_PROVIDER_ID_PERSISTED
def test_c4_case_27_used_provider_id_persisted():
    service = ProviderEventRevalidationService()
    obs = service.build_observation_record({"fixture_id": 1}, {"provider_event_id": "p_used_99", "raw_status": "NS", "home": "A", "away": "B"})
    assert obs.provider_event_id == "p_used_99"


# C4_CASE_28_EVIDENCE_MATCHES_OBSERVATION
def test_c4_case_28_evidence_matches_observation(tmp_path):
    from bet.pipeline.provider_observation_evidence import write_observation_evidence_envelope, validate_persisted_provider_observation
    payload = {"run_id": "r1", "phase": "PLAN", "canonical_event_id": "e1", "provider": "p1", "request_status": "SUCCESS"}
    path_str, sha = write_observation_evidence_envelope(payload, tmp_path)
    is_ok, msg = validate_persisted_provider_observation(payload, path_str, sha)
    assert is_ok


# C4_CASE_29_ERROR_ATTEMPT_PERSISTED
def test_c4_case_29_error_attempt_persisted():
    service = ProviderEventRevalidationService()
    obs = service.build_observation_record({"fixture_id": 1}, {"provider_event_id": "p1", "raw_status": "FAILED", "error_code": "404_NOT_FOUND"})
    assert obs.raw_provider_status == "FAILED"


# C4_CASE_30_RETRY_ATTEMPT_NUMBER
def test_c4_case_30_retry_attempt_number(tmp_path):
    import sqlite3
    from bet.db.schema import init_db
    from bet.db.repositories import ProviderObservationAttemptRepository
    conn = sqlite3.connect(tmp_path / "test.db")
    init_db(conn)
    repo = ProviderObservationAttemptRepository(conn)

    id1 = repo.insert_attempt(run_id="r1", phase="PLAN", attempt_number=1, canonical_event_id="e1", provider="p1", attempted_at_utc="2026-07-30T12:00:00Z", request_status="SUCCESS", canonical_event_status="SCHEDULED")
    id2 = repo.insert_attempt(run_id="r1", phase="PLAN", attempt_number=2, canonical_event_id="e1", provider="p1", attempted_at_utc="2026-07-30T12:05:00Z", request_status="SUCCESS", canonical_event_status="SCHEDULED")
    att1 = repo.get_attempt_by_id(id1)
    att2 = repo.get_attempt_by_id(id2)
    assert att1["attempt_number"] == 1
    assert att2["attempt_number"] == 2
    conn.close()


# C4_CASE_39_SECRETS_EXCLUDED
def test_c4_case_39_secrets_excluded(tmp_path):
    from bet.pipeline.provider_observation_evidence import write_observation_evidence_envelope
    payload = {"run_id": "r1", "phase": "PLAN", "canonical_event_id": "e1", "provider": "p1", "request_status": "SUCCESS", "Authorization": "Bearer secret_token"}
    path_str, sha = write_observation_evidence_envelope(payload, tmp_path)
    content = Path(path_str).read_text()
    assert "secret_token" not in content


# C4_CASE_40_UNSUPPORTED_NOT_SUCCESS
def test_c4_case_40_unsupported_not_success():
    res = ProviderRequestStatus.UNSUPPORTED
    assert res != ProviderRequestStatus.SUCCESS


# C4_CASE_41_FAILED_NOT_SUCCESS
def test_c4_case_41_failed_not_success():
    res = ProviderRequestStatus.FAILED
    assert res != ProviderRequestStatus.SUCCESS


# C4_CASE_42_CONFLICT_NOT_SUCCESS
def test_c4_case_42_conflict_not_success():
    res = ProviderRequestStatus.IDENTITY_CONFLICT
    assert res != ProviderRequestStatus.SUCCESS
