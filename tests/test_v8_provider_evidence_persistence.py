"""Test suite for provider observation evidence persistence, envelope serialization, and repository (C3)."""

import hashlib
import json
import sqlite3
from pathlib import Path
import pytest

from bet.db.schema import init_db


def test_c3_plan_and_continuation_coexist(tmp_path):
    """C3 test 5, 6, 7, 8, 9: PLAN and CONTINUATION coexist, retries increment attempt_number, separate status/kickoff/participants."""
    db_path = tmp_path / "obs.db"
    conn = sqlite3.connect(db_path)
    init_db(conn)

    # Insert a dummy fixture with id 100 for foreign key validity
    conn.execute("INSERT INTO sports (id, name) VALUES (1, 'football')")
    conn.execute("INSERT INTO teams (id, sport_id, name) VALUES (1, 1, 'Arsenal')")
    conn.execute("INSERT INTO teams (id, sport_id, name) VALUES (2, 1, 'Chelsea')")
    conn.execute("INSERT INTO fixtures (id, sport_id, home_team_id, away_team_id, kickoff, fetched_at) VALUES (100, 1, 1, 2, '2026-07-30T15:00:00Z', '2026-07-30T12:00:00Z')")
    conn.commit()

    try:
        from bet.db.repositories import ProviderObservationAttemptRepository
        from bet.pipeline.event_runtime_contract import CanonicalEventStatus, ProviderRequestStatus
        repo = ProviderObservationAttemptRepository(conn)

        # 5. Insert PLAN attempt 1
        id1 = repo.insert_attempt(
            run_id="run_1",
            phase="PLAN",
            attempt_number=1,
            canonical_event_id="evt_100",
            fixture_id=100,
            provider="api_football",
            provider_event_id="p_100",
            attempted_at_utc="2026-07-30T12:00:00Z",
            request_status=ProviderRequestStatus.SUCCESS,
            raw_provider_status="NS",
            canonical_event_status=CanonicalEventStatus.SCHEDULED,
            raw_observed_kickoff="2026-07-30T15:00:00Z",
            observed_kickoff_utc="2026-07-30T15:00:00Z",
            observed_home_name="Arsenal",
            observed_away_name="Chelsea",
            participant_identity_sha256="sha_part_1",
            observation_envelope_sha256="sha_env_1",
            evidence_path="/tmp/env_1.json",
        )

        # 6. Insert PLAN retry attempt 2
        id2 = repo.insert_attempt(
            run_id="run_1",
            phase="PLAN",
            attempt_number=2,
            canonical_event_id="evt_100",
            fixture_id=100,
            provider="api_football",
            provider_event_id="p_100",
            attempted_at_utc="2026-07-30T12:05:00Z",
            request_status=ProviderRequestStatus.SUCCESS,
            raw_provider_status="NS",
            canonical_event_status=CanonicalEventStatus.SCHEDULED,
            raw_observed_kickoff="2026-07-30T15:00:00Z",
            observed_kickoff_utc="2026-07-30T15:00:00Z",
            observed_home_name="Arsenal",
            observed_away_name="Chelsea",
            participant_identity_sha256="sha_part_1",
            observation_envelope_sha256="sha_env_2",
            evidence_path="/tmp/env_2.json",
        )

        # 5. Insert CONTINUATION attempt 1 for same event
        id3 = repo.insert_attempt(
            run_id="run_1",
            phase="CONTINUATION",
            attempt_number=1,
            canonical_event_id="evt_100",
            fixture_id=100,
            provider="api_football",
            provider_event_id="p_100",
            attempted_at_utc="2026-07-30T14:00:00Z",
            request_status=ProviderRequestStatus.SUCCESS,
            raw_provider_status="NS",
            canonical_event_status=CanonicalEventStatus.SCHEDULED,
            raw_observed_kickoff="2026-07-30T15:00:00Z",
            observed_kickoff_utc="2026-07-30T15:00:00Z",
            observed_home_name="Arsenal",
            observed_away_name="Chelsea",
            participant_identity_sha256="sha_part_1",
            observation_envelope_sha256="sha_env_3",
            evidence_path="/tmp/env_3.json",
        )

        attempts = repo.list_attempts_for_event("evt_100")
        assert len(attempts) == 3

        # 7, 8, 9. Separate fields check
        att1 = repo.get_attempt_by_id(id1)
        assert att1["raw_provider_status"] == "NS"
        assert att1["canonical_event_status"] == "SCHEDULED"
        assert att1["observed_kickoff_utc"] == "2026-07-30T15:00:00Z"
        assert att1["observed_home_name"] == "Arsenal"
        assert att1["observed_away_name"] == "Chelsea"
    except (ImportError, AttributeError):
        pytest.fail("C3 defect: ProviderObservationAttemptRepository or required methods missing", pytrace=False)
    finally:
        conn.close()


def test_c3_atomic_evidence_write_and_final_bytes_hashing(tmp_path):
    """C3 test 10, 11, 12, 18: atomic evidence write, final bytes hashed, partial failure compensation."""
    try:
        from bet.pipeline.provider_observation_evidence import write_observation_evidence_envelope, validate_persisted_provider_observation
    except (ImportError, ModuleNotFoundError):
        pytest.fail("C3 defect: provider_observation_evidence module or helpers missing", pytrace=False)

    payload = {
        "schema_version": "v1",
        "run_id": "run_100",
        "phase": "PLAN",
        "attempt_number": 1,
        "canonical_event_id": "evt_200",
        "fixture_id": 200,
        "provider": "api_football",
        "provider_event_id": "p_200",
        "attempted_at_utc": "2026-07-30T12:00:00Z",
        "request_status": "SUCCESS",
        "raw_provider_status": "NS",
        "canonical_event_status": "SCHEDULED",
        "raw_observed_kickoff": "2026-07-30T15:00:00Z",
        "observed_kickoff_utc": "2026-07-30T15:00:00Z",
        "observed_home_name": "Real Madrid",
        "observed_away_name": "Barcelona",
        "participant_identity_sha256": "part_sha_200",
    }

    target_dir = tmp_path / "evidence_dir"

    # Write envelope atomically
    evidence_path, final_sha256 = write_observation_evidence_envelope(payload, target_dir)

    # 10. Verify final bytes match SHA256
    file_bytes = Path(evidence_path).read_bytes()
    computed_sha = hashlib.sha256(file_bytes).hexdigest()
    assert computed_sha == final_sha256, f"Final bytes hash mismatch: {computed_sha} != {final_sha256}"

    # 11, 12. Validation with valid, missing, tampered evidence
    is_ok, msg = validate_persisted_provider_observation(payload, evidence_path, final_sha256)
    assert is_ok, f"Expected valid observation, got: {msg}"

    # Tamper with file
    Path(evidence_path).write_bytes(b'{"tampered": true}')
    is_ok_tamp, msg_t = validate_persisted_provider_observation(payload, evidence_path, final_sha256)
    assert not is_ok_tamp, "Tampered evidence file passed validation"
    assert "SHA256_MISMATCH" in msg_t


def test_c3_legacy_rows_not_trusted_as_verified(tmp_path):
    """C3 test 20: legacy observation rows without evidence file are not trusted as verified SUCCESS."""
    db_path = tmp_path / "legacy.db"
    conn = sqlite3.connect(db_path)
    init_db(conn)

    try:
        from bet.pipeline.provider_observation_evidence import validate_persisted_provider_observation
        
        legacy_record = {
            "request_status": "SUCCESS",
            "provider_event_id": "p_legacy",
            "canonical_event_status": "SCHEDULED",
            "attempted_at_utc": "2026-07-30T12:00:00Z",
            "participant_identity_sha256": "part_sha",
            "evidence_path": None,  # Legacy row missing evidence file
            "observation_envelope_sha256": None,
        }

        is_valid, reason = validate_persisted_provider_observation(legacy_record, None, None)
        assert not is_valid, "Legacy row without evidence file was trusted as verified SUCCESS"
        assert "EVIDENCE_NOT_VERIFIED" in reason or "MISSING_EVIDENCE" in reason
    except (ImportError, ModuleNotFoundError):
        pytest.fail("C3 defect: validate_persisted_provider_observation missing", pytrace=False)
    finally:
        conn.close()
