"""Test suite for V8 runtime contract defects and C2 contract specifications."""

import os
import sys
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch
import pytest

from bet.pipeline.launch_bridge import (
    verify_canonical_db_and_preflight,
)
from bet.utils.common import normalize_for_matching
from bet.pipeline.event_runtime_contract import (
    CanonicalEventStatus,
    ProviderRequestStatus,
    ProviderObservationRecord,
    normalize_provider_status,
    is_status_allowed_for_plan,
    is_status_allowed_for_continuation,
    build_participant_identity,
    sha256_file,
    verify_evidence_file,
    verify_evidence_envelope,
    validate_provider_observation,
    compute_runtime_input_fingerprint,
    classify_event_eligibility,
    parse_utc_timestamp,
    NaiveDatetimeError,
    InvalidEvidenceError,
)


def test_b01_baseline_enforcement_fail_open():
    """B01: verify_canonical_db_and_preflight(..., enforce_baseline=True) detects mismatches but does not reliably block."""
    real_db = (Path.cwd() / "betting" / "data" / "betting.db").resolve()
    
    with patch("bet.pipeline.launch_bridge.EXPECTED_START_HEAD", "0000000000000000000000000000000000000000"):
        preflight = verify_canonical_db_and_preflight(
            repo_root=Path.cwd(),
            explicit_db_path=real_db,
            enforce_baseline=True,
        )
    
        assert preflight.status != "PASS", (
            f"B01 defect: preflight status is PASS despite baseline mismatch (head_sha={preflight.head_sha})"
        )
        assert preflight.status == "BLOCKED_FOR_BASELINE", (
            f"Expected BLOCKED_FOR_BASELINE, got {preflight.status}"
        )


def test_c2_status_mappings():
    """C2 test 1, 2, 3, 7, 8, 9, 10, 11: status mappings, lowercase/whitespace, unknown fail-closed."""
    now_utc = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)
    future_kickoff = datetime(2026, 7, 30, 18, 0, tzinfo=UTC)

    # Lowercase & whitespace
    assert normalize_provider_status("  pEnDiNg  ", observed_kickoff_utc=future_kickoff, observed_at_utc=now_utc) == CanonicalEventStatus.SCHEDULED

    # Postponed
    assert normalize_provider_status("POST") == CanonicalEventStatus.POSTPONED
    assert normalize_provider_status("pst") == CanonicalEventStatus.POSTPONED

    # Awarded & Walkover
    assert normalize_provider_status("AWD") == CanonicalEventStatus.AWARDED_TERMINAL
    assert normalize_provider_status("WO") == CanonicalEventStatus.WALKOVER

    # All live statuses
    for live in ["LIVE", "IN_PLAY", "HT", "1H", "2H", "ET", "Q1", "OT"]:
        assert normalize_provider_status(live) == CanonicalEventStatus.LIVE, f"Failed for live status: {live}"

    # All finished statuses
    for fin in ["FINISHED", "FT", "AET", "PEN", "FINAL"]:
        assert normalize_provider_status(fin) == CanonicalEventStatus.FINISHED, f"Failed for finished status: {fin}"

    # Unknown status fail-closed
    assert normalize_provider_status("SOME_RANDOM_STATUS") == CanonicalEventStatus.UNKNOWN
    assert normalize_provider_status(None) == CanonicalEventStatus.UNKNOWN


def test_c2_pending_ns_lead_and_passed_kickoff():
    """C2 test 4, 5, 6: PENDING with valid lead, PENDING after kickoff, NS with insufficient lead."""
    now_utc = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)

    # 4. PENDING with valid lead time
    kickoff_future = datetime(2026, 7, 30, 15, 0, tzinfo=UTC)
    s_valid = normalize_provider_status(
        "PENDING",
        observed_kickoff_utc=kickoff_future,
        observed_at_utc=now_utc,
        minimum_lead=timedelta(minutes=30),
    )
    assert s_valid == CanonicalEventStatus.SCHEDULED

    # 5. PENDING after kickoff
    kickoff_passed = datetime(2026, 7, 30, 11, 0, tzinfo=UTC)
    s_passed = normalize_provider_status(
        "PENDING",
        observed_kickoff_utc=kickoff_passed,
        observed_at_utc=now_utc,
    )
    assert s_passed == CanonicalEventStatus.UNKNOWN

    # 6. NS with insufficient lead
    kickoff_tight = datetime(2026, 7, 30, 12, 10, tzinfo=UTC)
    s_tight = normalize_provider_status(
        "NS",
        observed_kickoff_utc=kickoff_tight,
        observed_at_utc=now_utc,
        minimum_lead=timedelta(minutes=30),
    )
    assert s_tight == CanonicalEventStatus.UNKNOWN


def test_b17_runtime_input_fingerprint_excludes_critical_fields():
    """B17 / C2 test 26, 27: runtime input fingerprint excludes participants, evidence, status, versions."""
    base_payload = {
        "canonical_event_id": "evt_100",
        "fixture_id": 100,
        "provider": "api_football",
        "provider_event_id": "p_100",
        "canonical_status": "SCHEDULED",
        "observed_kickoff_utc": "2026-07-30T15:00:00Z",
        "home_participant": "Arsenal",
        "away_participant": "Chelsea",
        "provider_evidence_sha256": "a" * 64,
        "stage_contract_version": "v1",
        "config_digest": "b" * 64,
    }
    
    fp_base = compute_runtime_input_fingerprint(base_payload)
    
    # 27. Test every field change alters fingerprint
    for key, alt_val in [
        ("home_participant", "Arsenal FC"),
        ("provider_evidence_sha256", "c" * 64),
        ("canonical_status", "POSTPONED"),
        ("stage_contract_version", "v2"),
        ("observed_kickoff_utc", "2026-07-30T18:00:00Z"),
    ]:
        alt_payload = dict(base_payload, **{key: alt_val})
        assert compute_runtime_input_fingerprint(alt_payload) != fp_base, f"Fingerprint did not change for {key}"

    # 26. Key order independence
    reordered_payload = {k: base_payload[k] for k in reversed(list(base_payload.keys()))}
    assert compute_runtime_input_fingerprint(reordered_payload) == fp_base


def test_c2_participant_identity_and_distinctions():
    """C2 test 19, 20, 21: Ł/Ø/Đ/ß, home/away order, women/youth/reserve/academy distinctions."""
    # 19. Polish and special characters
    p_pol = build_participant_identity("Łukasz Piszczek", " Wisła Kraków ")
    assert p_pol.home_normalized == "lukasz piszczek"
    assert p_pol.away_normalized == "wisla krakow"

    p_nordic = build_participant_identity(" Bodø/Glimt ", " Red Star ")
    assert p_nordic.home_normalized == "bodo glimt"

    # 20. Home/away order preservation
    p1 = build_participant_identity("Arsenal", "Chelsea")
    p2 = build_participant_identity("Chelsea", "Arsenal")
    assert p1.identity_sha256 != p2.identity_sha256, "Home/away reversal must produce different identity SHA"

    # 21. Team distinctions
    p_main = build_participant_identity("Arsenal FC", "Chelsea FC")
    p_women = build_participant_identity("Arsenal Women", "Chelsea Women")
    p_youth = build_participant_identity("Arsenal U21", "Chelsea U21")
    p_res = build_participant_identity("Arsenal II", "Chelsea B")

    assert p_main.identity_sha256 != p_women.identity_sha256, "Women team distinction lost"
    assert p_main.identity_sha256 != p_youth.identity_sha256, "Youth team distinction lost"
    assert p_main.identity_sha256 != p_res.identity_sha256, "Reserve team distinction lost"


def test_c2_evidence_validation(tmp_path):
    """C2 test 22, 23, 24, 25: evidence hash, missing evidence, tampered evidence, incomplete observation."""
    ev_file = tmp_path / "evidence.json"
    ev_bytes = b'{"provider": "api_football", "status": "NS"}'
    ev_file.write_bytes(ev_bytes)
    correct_sha = sha256_file(ev_file)

    # 22. Valid evidence
    is_valid, msg = verify_evidence_file(ev_file, correct_sha)
    assert is_valid, f"Expected verified evidence, got: {msg}"

    # 23. Missing evidence
    is_valid_missing, msg_m = verify_evidence_file(tmp_path / "non_existent.json", correct_sha)
    assert not is_valid_missing, "Missing evidence file accepted"

    # 24. Tampered evidence
    is_valid_tamp, msg_t = verify_evidence_file(ev_file, "0" * 64)
    assert not is_valid_tamp, "Tampered evidence accepted"

    # 25. SUCCESS observation with incomplete data
    obs_incomplete = ProviderObservationRecord(
        canonical_event_id="evt_1",
        fixture_id=1,
        provider="api_football",
        provider_event_id=None,  # Missing provider_event_id
        attempted_at_utc="2026-07-30T12:00:00Z",
        request_status=ProviderRequestStatus.SUCCESS,
        raw_provider_status="NS",
        canonical_event_status=CanonicalEventStatus.SCHEDULED,
        raw_observed_kickoff="2026-07-30T15:00:00Z",
        observed_kickoff_utc="2026-07-30T15:00:00Z",
        observed_home_name="Arsenal",
        observed_away_name="Chelsea",
        participant_identity_sha256=None,
        competition_identity_sha256=None,
    )
    is_obs_ok, reason = validate_provider_observation(obs_incomplete)
    assert not is_obs_ok, "Incomplete SUCCESS observation passed validation"
    assert "INCOMPLETE_OBSERVATION" in reason


def test_b20_provider_observation_schema_created_dynamically():
    """B20: provider-observation schema is created dynamically and drifts from committed migrations/schema definitions."""
    schema_sql_path = Path.cwd() / "src" / "bet" / "db" / "schema.sql"
    assert schema_sql_path.exists(), "schema.sql missing"
    schema_text = schema_sql_path.read_text()
    
    assert "pipeline_provider_observation_attempts" in schema_text, (
        "B20 defect: pipeline_provider_observation_attempts table missing from committed schema.sql"
    )


def test_b23_repository_import_environment():
    """B23: test commands do not consistently use the repository import environment."""
    env = os.environ.copy()
    repo_root = str(Path.cwd())
    venv_python = str(Path.cwd() / ".venv" / "bin" / "python3")
    
    cmd = [venv_python, "-c", "import bet; print(bet.__file__)"]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=repo_root, env=env)
    
    assert proc.returncode == 0, f"B23 defect: import bet failed: {proc.stderr}"
    assert "src/bet" in proc.stdout, f"B23 defect: imported bet from unexpected path: {proc.stdout}"


def test_b24_unicode_name_normalization_for_matching():
    """B24: creating another simplistic Unicode normalizer would break names such as Łukasz."""
    res1 = normalize_for_matching("Łukasz Piszczek")
    assert res1 == "lukasz piszczek", f"B24 defect: normalize_for_matching failed for Łukasz: got '{res1}'"

    res2 = normalize_for_matching("Wisła Kraków")
    assert res2 == "wisla krakow", f"B24 defect: normalize_for_matching failed for Wisła: got '{res2}'"

    res3 = normalize_for_matching(" FC Bayern München ")
    assert res3 == "fc bayern munchen", f"B24 defect: normalize_for_matching failed for München: got '{res3}'"
