from bet.enrichment.football_data_foundation.worldcup_20260624_live_shadow.sanitizer import (
    sanitize_json_body,
    compute_body_sha256
)

def test_sanitizer_removes_headers_secrets_cookies() -> None:
    # TEST-005: sanitizer removes headers/secrets/cookies.
    raw_payload = {
        "x-api-key": "secret_key_123",
        "cookie": "user_session_abc",
        "authorization": "Bearer token123",
        "some_secure_token": "token_xyz",
        "normal_key": "safe_value",
        "selectable_for_production": True
    }

    sanitized = sanitize_json_body(raw_payload)

    # Assert secrets are redacted
    assert sanitized["x-api-key"] == "[REDACTED_SECRET]"
    assert sanitized["cookie"] == "[REDACTED_SECRET]"
    assert sanitized["authorization"] == "[REDACTED_SECRET]"
    assert sanitized["some_secure_token"] == "[REDACTED_SECRET]"
    assert sanitized["normal_key"] == "safe_value"

    # Assert selectable_for_production is forced to False
    assert sanitized["selectable_for_production"] is False


def test_body_sha256_computed() -> None:
    # TEST-006: cache envelopes include body_sha256.
    body = {"teams": {"home": "Switzerland", "away": "Canada"}}
    sha = compute_body_sha256(body)
    assert isinstance(sha, str)
    assert len(sha) == 64

    # Determinism check
    assert sha == compute_body_sha256(body)
