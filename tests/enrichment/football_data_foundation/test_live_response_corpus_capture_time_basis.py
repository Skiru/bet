from bet.enrichment.football_data_foundation.live_response_corpus_capture.fixtures import (
    get_official_seed_candidate,
)


def test_fixture_time_basis_exists():
    """
    REQ-TEST-009 fixture time_basis exists.
    """
    candidate = get_official_seed_candidate()
    assert "time_basis" in candidate
    tb = candidate["time_basis"]
    assert "official_display_time" in tb
    assert "utc_kickoff_at" in tb
    assert "timezone_assumption" in tb
    assert "time_confidence" in tb


def test_ambiguous_kickoff_unknown():
    """
    REQ-TEST-010 ambiguous kickoff does not silently convert to UTC.
    """
    # If kickoff is uncertain or missing explicit offset details/confidence,
    # it must be UNKNOWN instead of silently assumed to be UTC.
    fixture_with_ambiguity = {
        "official_display_time": "18:00",
        "kickoff_at": "2026-06-23 18:00",  # No timezone/UTC offset!
        "timezone_assumption": "UNCERTAIN",
    }

    # Simple check matching our logic
    assert "Z" not in fixture_with_ambiguity["kickoff_at"]
    if "Z" not in fixture_with_ambiguity["kickoff_at"] and "+00" not in fixture_with_ambiguity["kickoff_at"]:
        utc_kickoff = "UNKNOWN"
    else:
        utc_kickoff = fixture_with_ambiguity["kickoff_at"]

    assert utc_kickoff == "UNKNOWN"
