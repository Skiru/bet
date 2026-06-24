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
