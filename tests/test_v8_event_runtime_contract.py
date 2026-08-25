"""Dedicated Unit Test Suite for C2 Event Runtime Contract Requirements 1-27."""

from datetime import UTC, datetime, timedelta, date
from pathlib import Path
import pytest

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
    validate_provider_observation,
    compute_runtime_input_fingerprint,
    betting_day_utc_bounds,
    parse_utc_timestamp,
    NaiveDatetimeError,
    InvalidEvidenceError,
    ProviderEventRevalidationRegistry,
)


# C2_REQUIREMENT_01_STATUS_MAPPING
@pytest.mark.parametrize("raw,expected", [
    ("SCHEDULED", CanonicalEventStatus.SCHEDULED),
    ("LIVE", CanonicalEventStatus.LIVE),
    ("FINISHED", CanonicalEventStatus.FINISHED),
    ("POSTPONED", CanonicalEventStatus.POSTPONED),
    ("CANCELLED", CanonicalEventStatus.CANCELLED),
    ("ABANDONED", CanonicalEventStatus.ABANDONED),
    ("SUSPENDED", CanonicalEventStatus.SUSPENDED),
    ("WALKOVER", CanonicalEventStatus.WALKOVER),
    ("AWARDED_TERMINAL", CanonicalEventStatus.AWARDED_TERMINAL),
    ("UNKNOWN", CanonicalEventStatus.UNKNOWN),
])
def test_req01_status_mapping(raw, expected):
    now_utc = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)
    kickoff = datetime(2026, 7, 30, 18, 0, tzinfo=UTC)
    res = normalize_provider_status(raw, observed_kickoff_utc=kickoff, observed_at_utc=now_utc)
    assert res == expected


# C2_REQUIREMENT_02_CASE_WHITESPACE
def test_req02_case_and_whitespace():
    now_utc = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)
    kickoff = datetime(2026, 7, 30, 18, 0, tzinfo=UTC)
    assert normalize_provider_status("  pEnDiNg \n", observed_kickoff_utc=kickoff, observed_at_utc=now_utc) == CanonicalEventStatus.SCHEDULED
    assert normalize_provider_status("\tFiNiShEd  ") == CanonicalEventStatus.FINISHED


# C2_REQUIREMENT_03_UNKNOWN_FAIL_CLOSED
def test_req03_unknown_fail_closed():
    assert normalize_provider_status("INVALID_XYZ_STATUS") == CanonicalEventStatus.UNKNOWN
    assert normalize_provider_status(None) == CanonicalEventStatus.UNKNOWN
    assert normalize_provider_status("") == CanonicalEventStatus.UNKNOWN


# C2_REQUIREMENT_04_PENDING_VALID_LEAD
def test_req04_pending_valid_lead():
    now_utc = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)
    future_kickoff = datetime(2026, 7, 30, 15, 0, tzinfo=UTC)
    res = normalize_provider_status(
        "PENDING",
        observed_kickoff_utc=future_kickoff,
        observed_at_utc=now_utc,
        minimum_lead=timedelta(minutes=30),
    )
    assert res == CanonicalEventStatus.SCHEDULED


# C2_REQUIREMENT_05_PENDING_AFTER_KICKOFF
def test_req05_pending_after_kickoff():
    now_utc = datetime(2026, 7, 30, 16, 0, tzinfo=UTC)
    past_kickoff = datetime(2026, 7, 30, 15, 0, tzinfo=UTC)
    res = normalize_provider_status(
        "PENDING",
        observed_kickoff_utc=past_kickoff,
        observed_at_utc=now_utc,
    )
    assert res == CanonicalEventStatus.UNKNOWN


# C2_REQUIREMENT_06_NS_INSUFFICIENT_LEAD
def test_req06_ns_insufficient_lead():
    now_utc = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)
    tight_kickoff = datetime(2026, 7, 30, 12, 10, tzinfo=UTC)
    res = normalize_provider_status(
        "NS",
        observed_kickoff_utc=tight_kickoff,
        observed_at_utc=now_utc,
        minimum_lead=timedelta(minutes=30),
    )
    assert res == CanonicalEventStatus.UNKNOWN


# C2_REQUIREMENT_07_POST_PST
@pytest.mark.parametrize("post_raw", ["POST", "pst", "POSTP", "postponed", "STATUS_POSTPONED"])
def test_req07_post_pst(post_raw):
    assert normalize_provider_status(post_raw) == CanonicalEventStatus.POSTPONED


# C2_REQUIREMENT_08_AWD
def test_req08_awd():
    assert normalize_provider_status("AWD") == CanonicalEventStatus.AWARDED_TERMINAL
    assert normalize_provider_status("awarded") == CanonicalEventStatus.AWARDED_TERMINAL


# C2_REQUIREMENT_09_WO
def test_req09_wo():
    assert normalize_provider_status("WO") == CanonicalEventStatus.WALKOVER
    assert normalize_provider_status("walkover") == CanonicalEventStatus.WALKOVER


# C2_REQUIREMENT_10_LIVE_STATUSES
@pytest.mark.parametrize("live_raw", ["LIVE", "IN_PLAY", "IN_PROGRESS", "1H", "HT", "2H", "ET", "BT", "Q1", "Q2", "Q3", "Q4", "OT"])
def test_req10_live_statuses(live_raw):
    assert normalize_provider_status(live_raw) == CanonicalEventStatus.LIVE


# C2_REQUIREMENT_11_FINISHED_STATUSES
@pytest.mark.parametrize("fin_raw", ["FINISHED", "FINAL", "FT", "AET", "PEN", "AOT", "ended"])
def test_req11_finished_statuses(fin_raw):
    assert normalize_provider_status(fin_raw) == CanonicalEventStatus.FINISHED


# C2_REQUIREMENT_12_WARSAW_SUMMER_BOUNDARY
def test_req12_warsaw_summer_boundary():
    start_utc, end_utc = betting_day_utc_bounds(date(2026, 7, 30), timezone_name="Europe/Warsaw")
    assert start_utc.isoformat() == "2026-07-29T22:00:00+00:00"
    assert end_utc.isoformat() == "2026-07-30T22:00:00+00:00"


# C2_REQUIREMENT_13_WARSAW_WINTER_BOUNDARY
def test_req13_warsaw_winter_boundary():
    start_utc, end_utc = betting_day_utc_bounds(date(2026, 1, 15), timezone_name="Europe/Warsaw")
    assert start_utc.isoformat() == "2026-01-14T23:00:00+00:00"
    assert end_utc.isoformat() == "2026-01-15T23:00:00+00:00"


# C2_REQUIREMENT_14_HALF_OPEN_INTERVAL
def test_req14_half_open_interval():
    start_utc, end_utc = betting_day_utc_bounds(date(2026, 7, 30), timezone_name="Europe/Warsaw")
    inside_dt = datetime(2026, 7, 29, 22, 0, 0, tzinfo=UTC)
    outside_dt = datetime(2026, 7, 30, 22, 0, 0, tzinfo=UTC)
    assert start_utc <= inside_dt < end_utc
    assert not (start_utc <= outside_dt < end_utc)


# C2_REQUIREMENT_15_DST_SPRING
def test_req15_dst_spring():
    start_utc, end_utc = betting_day_utc_bounds(date(2026, 3, 29), timezone_name="Europe/Warsaw")
    assert start_utc.isoformat() == "2026-03-28T23:00:00+00:00"
    assert end_utc.isoformat() == "2026-03-29T22:00:00+00:00"


# C2_REQUIREMENT_16_DST_AUTUMN
def test_req16_dst_autumn():
    start_utc, end_utc = betting_day_utc_bounds(date(2026, 10, 25), timezone_name="Europe/Warsaw")
    assert start_utc.isoformat() == "2026-10-24T22:00:00+00:00"
    assert end_utc.isoformat() == "2026-10-25T23:00:00+00:00"


# C2_REQUIREMENT_17_NAIVE_DATETIME_REJECTED
def test_req17_naive_datetime_rejected():
    naive_dt = datetime(2026, 7, 30, 15, 0)
    with pytest.raises(NaiveDatetimeError):
        parse_utc_timestamp(naive_dt)

    naive_str = "2026-07-30T15:00:00"
    with pytest.raises(NaiveDatetimeError):
        parse_utc_timestamp(naive_str)


# C2_REQUIREMENT_18_EQUIVALENT_ISO_INSTANTS
def test_req18_equivalent_iso_instants():
    dt1 = parse_utc_timestamp("2026-07-30T15:00:00Z")
    dt2 = parse_utc_timestamp("2026-07-30T15:00:00+00:00")
    dt3 = parse_utc_timestamp("2026-07-30T17:00:00+02:00")
    assert dt1 == dt2 == dt3
    assert ProviderEventRevalidationRegistry.timestamps_equal("2026-07-30T15:00:00Z", "2026-07-30T17:00:00+02:00")


# C2_REQUIREMENT_19_SPECIAL_CHARACTERS
def test_req19_special_characters():
    p1 = build_participant_identity("Łukasz Piszczek", " Wisła Kraków ")
    assert p1.home_normalized == "lukasz piszczek"
    assert p1.away_normalized == "wisla krakow"

    p2 = build_participant_identity(" Bodø/Glimt ", " Đa Nẵng / Großaspach ")
    assert "bodo" in p2.home_normalized
    assert "grossaspach" in p2.away_normalized or "gross" in p2.away_normalized or "gros" in p2.away_normalized


# C2_REQUIREMENT_20_HOME_AWAY_ORDER
def test_req20_home_away_order():
    p_ha = build_participant_identity("Arsenal", "Chelsea")
    p_ah = build_participant_identity("Chelsea", "Arsenal")
    assert p_ha.identity_sha256 != p_ah.identity_sha256


# C2_REQUIREMENT_21_TEAM_QUALIFIERS
def test_req21_team_qualifiers():
    p_main = build_participant_identity("Arsenal FC", "Chelsea FC")
    p_women = build_participant_identity("Arsenal Women", "Chelsea Women")
    p_youth = build_participant_identity("Arsenal U21", "Chelsea U21")
    p_res = build_participant_identity("Arsenal II", "Chelsea B")

    assert p_main.identity_sha256 != p_women.identity_sha256
    assert p_main.identity_sha256 != p_youth.identity_sha256
    assert p_main.identity_sha256 != p_res.identity_sha256


# C2_REQUIREMENT_22_VALID_EVIDENCE_HASH
def test_req22_valid_evidence_hash(tmp_path):
    ev_file = tmp_path / "evidence.json"
    ev_file.write_bytes(b'{"status": "NS"}')
    correct_sha = sha256_file(ev_file)

    is_valid, msg = verify_evidence_file(ev_file, correct_sha)
    assert is_valid
    assert msg == "EVIDENCE_VERIFIED"


# C2_REQUIREMENT_23_MISSING_EVIDENCE
def test_req23_missing_evidence(tmp_path):
    missing_file = tmp_path / "missing.json"
    is_valid, msg = verify_evidence_file(missing_file, "0" * 64)
    assert not is_valid


# C2_REQUIREMENT_24_TAMPERED_EVIDENCE
def test_req24_tampered_evidence(tmp_path):
    ev_file = tmp_path / "evidence.json"
    ev_file.write_bytes(b'{"status": "NS"}')
    is_valid, msg = verify_evidence_file(ev_file, "f" * 64)
    assert not is_valid
    assert "SHA256_MISMATCH" in msg


# C2_REQUIREMENT_25_INCOMPLETE_SUCCESS
def test_req25_incomplete_success():
    obs = ProviderObservationRecord(
        canonical_event_id="evt_1",
        fixture_id=1,
        provider="api_football",
        provider_event_id=None,
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
    is_valid, reason = validate_provider_observation(obs)
    assert not is_valid
    assert "INCOMPLETE_OBSERVATION" in reason


# C2_REQUIREMENT_26_DETERMINISTIC_FINGERPRINT
def test_req26_deterministic_fingerprint():
    p1 = {"a": 1, "b": [1, 2], "c": "val"}
    p2 = {"c": "val", "a": 1, "b": [1, 2]}
    fp1 = compute_runtime_input_fingerprint(p1)
    fp2 = compute_runtime_input_fingerprint(p2)
    assert fp1 == fp2


# C2_REQUIREMENT_27_EACH_FIELD_CHANGES_DIGEST
def test_req27_each_field_changes_digest():
    base = {
        "canonical_event_id": "e1",
        "fixture_id": 1,
        "provider": "p1",
        "provider_event_id": "pe1",
        "canonical_status": "SCHEDULED",
        "observed_kickoff_utc": "2026-07-30T15:00:00Z",
        "home_participant": "Arsenal",
        "away_participant": "Chelsea",
        "provider_evidence_sha256": "a" * 64,
        "stage_contract_version": "v1",
        "config_digest": "b" * 64,
    }
    fp_base = compute_runtime_input_fingerprint(base)

    for field, new_val in [
        ("canonical_event_id", "e2"),
        ("fixture_id", 2),
        ("provider", "p2"),
        ("provider_event_id", "pe2"),
        ("canonical_status", "LIVE"),
        ("observed_kickoff_utc", "2026-07-30T16:00:00Z"),
        ("home_participant", "Arsenal FC"),
        ("away_participant", "Chelsea FC"),
        ("provider_evidence_sha256", "c" * 64),
        ("stage_contract_version", "v2"),
        ("config_digest", "d" * 64),
    ]:
        alt = dict(base, **{field: new_val})
        assert compute_runtime_input_fingerprint(alt) != fp_base, f"Digest did not change for field {field}"
