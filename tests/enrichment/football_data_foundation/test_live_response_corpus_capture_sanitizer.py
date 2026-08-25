import pytest
from pathlib import Path
from bet.enrichment.football_data_foundation.live_response_corpus_capture.sanitizer import (
    sanitize_json_body,
    compute_body_sha256,
    write_json,
    is_html,
)


def test_sanitize_json_body_secrets():
    body = {
        "api_key": "secret-123",
        "X-Auth-Token": "secret-456",
        "nested": {
            "password": "pass",
            "normal_field": "ok_value",
        },
        "list_field": [
            {"cookie": "yummy"},
            "normal_string"
        ]
    }
    sanitized = sanitize_json_body(body)
    assert sanitized["api_key"] == "[REDACTED_SECRET]"
    assert sanitized["X-Auth-Token"] == "[REDACTED_SECRET]"
    assert sanitized["nested"]["password"] == "[REDACTED_SECRET]"
    assert sanitized["nested"]["normal_field"] == "ok_value"
    assert sanitized["list_field"][0]["cookie"] == "[REDACTED_SECRET]"
    assert sanitized["list_field"][1] == "normal_string"


def test_sanitize_json_body_selectable_for_production():
    body = {
        "selectable_for_production": True,
        "nested": {
            "selectable_for_production": True
        }
    }
    sanitized = sanitize_json_body(body)
    assert sanitized["selectable_for_production"] is False
    assert sanitized["nested"]["selectable_for_production"] is False


def test_blocks_html_content():
    with pytest.raises(ValueError, match="HTML content"):
        sanitize_json_body("<html><body>Hello</body></html>")

    with pytest.raises(ValueError, match="HTML content"):
        sanitize_json_body("<!DOCTYPE html><div>test</div>")


def test_compute_body_sha256_stable():
    body1 = {"b": 2, "a": 1}
    body2 = {"a": 1, "b": 2}

    sha1 = compute_body_sha256(body1)
    sha2 = compute_body_sha256(body2)

    assert sha1 == sha2
    assert len(sha1) == 64


def test_write_json_deterministic(tmp_path):
    path = tmp_path / "test.json"
    data = {"b": 2, "a": 1}
    write_json(path, data)

    content = path.read_text(encoding="utf-8")
    expected = '{\n  "a": 1,\n  "b": 2\n}\n'
    assert content == expected
