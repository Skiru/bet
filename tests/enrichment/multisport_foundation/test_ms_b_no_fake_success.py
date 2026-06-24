from __future__ import annotations
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import pytest
from bet.enrichment.multisport_foundation.fail_closed import assert_no_forbidden_success_text, is_valid_pass_b_status
from bet.enrichment.multisport_foundation.provider_corpus import build_blocked_corpus_record, sanitize_headers, contains_raw_secret
from bet.enrichment.multisport_foundation.verifier import verify_provider_corpus


def test_no_fake_success_status_for_unmapped_sources() -> None:
    record = build_blocked_corpus_record("sportdb", "basketball", "BLOCKED_NO_CREDENTIALS", "fixtures", "missing SPORTDB_API_KEY")
    result = verify_provider_corpus([record])
    assert result.verdict == "PASS", result.to_json()
    assert is_valid_pass_b_status(record.status)


def test_shadow_ready_requires_participant_evidence() -> None:
    record = build_blocked_corpus_record("sportdb", "basketball", "SOURCE_BOUND_SHADOW_READY", "fixtures", "invalid ready state")
    result = verify_provider_corpus([record])
    assert result.verdict == "FAIL"
    assert any("shadow_ready_without_participant_evidence" in item for item in result.failed_requirements)


def test_no_raw_headers_secrets_tokens_cookies() -> None:
    headers = {"Authorization": "Bearer abcdefghijklmnopqrstuvwxyz1234567890", "User-Agent": "bet-tests"}
    redacted = sanitize_headers(headers)
    assert redacted["Authorization"] == "<redacted>"
    assert not contains_raw_secret({"headers": redacted})


def test_forbidden_success_text_fails_fast() -> None:
    with pytest.raises(AssertionError):
        assert_no_forbidden_success_text({"note": "fallback provider id accepted"})


def test_no_accidental_promotion_of_blocked_statuses() -> None:
    from bet.enrichment.multisport_foundation.source_bound_shadow import build_source_bound_shadow
    from bet.enrichment.multisport_foundation.provider_corpus import build_blocked_corpus_record

    # Test that BLOCKED_NO_CREDENTIALS is preserved and NOT promoted to REAL_PROVIDER_ACCESS_OBSERVED_BUT_MAPPING_INSUFFICIENT
    rec = build_blocked_corpus_record("pandascore", "cs2", "BLOCKED_NO_CREDENTIALS", "matches", "missing PANDASCORE_API_KEY")
    art = build_source_bound_shadow("cs2", [rec], ("fixture_identity", "participants"))
    assert art.status == "BLOCKED_NO_CREDENTIALS"
    assert art.status != "REAL_PROVIDER_ACCESS_OBSERVED_BUT_MAPPING_INSUFFICIENT"

    # Test that BLOCKED_PROVIDER_TERMS_OR_SCOPE is preserved
    rec2 = build_blocked_corpus_record("pandascore", "cs2", "BLOCKED_PROVIDER_TERMS_OR_SCOPE", "matches", "scope limitation")
    art2 = build_source_bound_shadow("cs2", [rec2], ("fixture_identity", "participants"))
    assert art2.status == "BLOCKED_PROVIDER_TERMS_OR_SCOPE"
    assert art2.status != "REAL_PROVIDER_ACCESS_OBSERVED_BUT_MAPPING_INSUFFICIENT"

    # Test that BLOCKED_PROVIDER_ACCESS is preserved
    rec3 = build_blocked_corpus_record("pandascore", "cs2", "BLOCKED_PROVIDER_ACCESS", "matches", "ip blocked")
    art3 = build_source_bound_shadow("cs2", [rec3], ("fixture_identity", "participants"))
    assert art3.status == "BLOCKED_PROVIDER_ACCESS"
    assert art3.status != "REAL_PROVIDER_ACCESS_OBSERVED_BUT_MAPPING_INSUFFICIENT"

    # Only when record explicitly has REAL_PROVIDER_ACCESS_OBSERVED_BUT_MAPPING_INSUFFICIENT is it produced
    rec4 = build_blocked_corpus_record("pandascore", "cs2", "REAL_PROVIDER_ACCESS_OBSERVED_BUT_MAPPING_INSUFFICIENT", "matches", "mapping missing")
    art4 = build_source_bound_shadow("cs2", [rec4], ("fixture_identity", "participants"))
    assert art4.status == "REAL_PROVIDER_ACCESS_OBSERVED_BUT_MAPPING_INSUFFICIENT"
