from __future__ import annotations

import pytest
from unittest.mock import patch
from bet.tipsters.source_registry import SOURCES
from bet.tipsters.source_certification import (
    build_source_certification_matrix,
    check_source_robots_compliance,
    Classification,
    STATIC_RESCUE_MATRIX,
)


def test_every_registry_source_is_covered_in_rescue_matrix():
    matrix = build_source_certification_matrix(run_robots_probe=False)

    # Check that all SOURCES in source_registry are present in the static matrix keys
    assert len(matrix) == len(SOURCES)

    matrix_ids = {entry["source_id"] for entry in matrix}
    for source_id in SOURCES:
        assert source_id in matrix_ids


def test_zawodtyper_remains_certified_shadow_live():
    matrix = build_source_certification_matrix(run_robots_probe=False)
    zawodtyper_entry = next(entry for entry in matrix if entry["source_id"] == "zawodtyper")

    assert zawodtyper_entry["classification"] == Classification.CERTIFIED_SHADOW_LIVE
    assert zawodtyper_entry["priority"] == "P0"
    assert "stealth" in zawodtyper_entry["disallowed_methods"]
    assert "login" in zawodtyper_entry["disallowed_methods"]


def test_robots_compliance_handles_exceptions_safely():
    # Force urllib.robotparser.RobotFileParser to throw an exception to simulate network offline / timeout
    with patch("urllib.robotparser.RobotFileParser.read", side_effect=Exception("Timeout / DNS error")):
        allowed, detail = check_source_robots_compliance("sportsgambler")
        # Should return None (unknown) instead of raising error or hard-blocking
        assert allowed is None
        assert "robots_fetch_failed_or_timeout" in detail


def test_matrix_generation_with_failed_robots_probes():
    # If robots.txt fetch fails, the classification must become UNKNOWN_NEEDS_DEEP_REVIEW
    with patch("urllib.robotparser.RobotFileParser.read", side_effect=Exception("Offline")):
        matrix = build_source_certification_matrix(run_robots_probe=True)
        for entry in matrix:
            if SOURCES[entry["source_id"]].robots_required:
                assert entry["classification"] == Classification.UNKNOWN_NEEDS_DEEP_REVIEW
                assert entry["robots_allowed_probe"] is None
