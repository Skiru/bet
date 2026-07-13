from __future__ import annotations

import json
from unittest.mock import patch
from bet.provider_registry import load_provider_registry, missing_provider_modules
from scripts.validate_provider_registry import validate, validate_provider


def test_provider_registry_is_complete_and_loadable() -> None:
    registry = load_provider_registry()

    assert set(registry) == {
        "api-football-odds",
        "odds-api-io",
        "oddspapi",
        "the-odds-api",
    }
    assert missing_provider_modules() == []
    for registration in registry.values():
        policy = registration.policy
        assert policy["total_deadline_seconds"] >= policy["read_timeout_seconds"]
        assert policy["retry_count"] <= 3
        assert policy["stale_cache_behavior"] == "STALE_CACHE"
        assert policy["redaction_policy"] == "credential_values_never_serialized"


def test_registry_and_active_adapter_map_are_identical() -> None:
    result = validate()
    assert result["status"] == "PASS"
    for provider in result["providers"]:
        assert provider["registry_valid"] is True
        assert provider["module_importable"] is True
        assert provider["transport_policy_bound"] is True
        assert provider["deadline_policy"] == "PASS"
        assert provider["retry_policy"] == "PASS"
        assert provider["cache_policy"] == "PASS"
        assert provider["secret_redaction"] == "PASS"


def test_validator_fails_on_deadline_defects() -> None:
    # 1. Deadline is absent
    item = {
        "provider_id": "test-prov",
        "module": "scripts.odds_sources.oddspapi",
        "sports_supported": ["football"],
        "transport": "https_json",
        "configuration_schema": {},
        "required_credential_names": ["KEY"],
        "base_url": "https://api.test.io",
        "connect_timeout_seconds": 3,
        "read_timeout_seconds": 10,
        "retry_count": 1,
        "retryable_conditions": ["ERROR"],
        "retry_after": "yes",
        "backoff": "exp",
        "cache_policy": "sha",
        "cache_ttl_seconds": 300,
        "stale_cache_behavior": "STALE_CACHE",
        "pagination": "yes",
        "parser_schema_version": "v1",
        "identity_fields": ["id"],
        "compliance_terms_status": "OK",
        "redaction_policy": "credential_values_never_serialized",
        "health_check": "ok",
        "fallback_priority": 1,
    }
    # absent total_deadline_seconds
    res = validate_provider("test-prov", item)
    assert res["deadline_policy"] == "FAIL"

    # 2. Deadline is shorter than required
    item["total_deadline_seconds"] = 5  # connect (3) + read (10) = 13 > 5
    res = validate_provider("test-prov", item)
    assert res["deadline_policy"] == "FAIL"


def test_validator_fails_on_retry_defects() -> None:
    item = {
        "provider_id": "test-prov",
        "module": "scripts.odds_sources.oddspapi",
        "sports_supported": ["football"],
        "transport": "https_json",
        "configuration_schema": {},
        "required_credential_names": ["KEY"],
        "base_url": "https://api.test.io",
        "connect_timeout_seconds": 3,
        "read_timeout_seconds": 10,
        "total_deadline_seconds": 15,
        "retry_count": 10,  # excessive retry count (max is 3)
        "retryable_conditions": ["ERROR"],
        "retry_after": "yes",
        "backoff": "exp",
        "cache_policy": "sha",
        "cache_ttl_seconds": 300,
        "stale_cache_behavior": "STALE_CACHE",
        "pagination": "yes",
        "parser_schema_version": "v1",
        "identity_fields": ["id"],
        "compliance_terms_status": "OK",
        "redaction_policy": "credential_values_never_serialized",
        "health_check": "ok",
        "fallback_priority": 1,
    }
    res = validate_provider("test-prov", item)
    assert res["retry_policy"] == "FAIL"

    # Retry-After is omitted
    item["retry_count"] = 1
    item["retry_after"] = ""
    res = validate_provider("test-prov", item)
    assert res["retry_policy"] == "FAIL"


def test_validator_fails_on_cache_defects() -> None:
    item = {
        "provider_id": "test-prov",
        "module": "scripts.odds_sources.oddspapi",
        "sports_supported": ["football"],
        "transport": "https_json",
        "configuration_schema": {},
        "required_credential_names": ["KEY"],
        "base_url": "https://api.test.io",
        "connect_timeout_seconds": 3,
        "read_timeout_seconds": 10,
        "total_deadline_seconds": 15,
        "retry_count": 1,
        "retryable_conditions": ["ERROR"],
        "retry_after": "yes",
        "backoff": "exp",
        "cache_policy": "",  # absent/malformed
        "cache_ttl_seconds": 300,
        "stale_cache_behavior": "STALE_CACHE",
        "pagination": "yes",
        "parser_schema_version": "v1",
        "identity_fields": ["id"],
        "compliance_terms_status": "OK",
        "redaction_policy": "credential_values_never_serialized",
        "health_check": "ok",
        "fallback_priority": 1,
    }
    res = validate_provider("test-prov", item)
    assert res["cache_policy"] == "FAIL"

    # Stale status is incorrect
    item["cache_policy"] = "sha"
    item["stale_cache_behavior"] = "DELETE_CACHE"
    res = validate_provider("test-prov", item)
    assert res["cache_policy"] == "FAIL"


def test_validator_fails_on_credential_and_redaction_defects() -> None:
    item = {
        "provider_id": "test-prov",
        "module": "scripts.odds_sources.oddspapi",
        "sports_supported": ["football"],
        "transport": "https_json",
        "configuration_schema": {},
        "required_credential_names": [
            "3ab28ca79f0012bcfe349e19d765fa10"
        ],  # embedded value
        "base_url": "https://api.test.io",
        "connect_timeout_seconds": 3,
        "read_timeout_seconds": 10,
        "total_deadline_seconds": 15,
        "retry_count": 1,
        "retryable_conditions": ["ERROR"],
        "retry_after": "yes",
        "backoff": "exp",
        "cache_policy": "sha",
        "cache_ttl_seconds": 300,
        "stale_cache_behavior": "STALE_CACHE",
        "pagination": "yes",
        "parser_schema_version": "v1",
        "identity_fields": ["id"],
        "compliance_terms_status": "OK",
        "redaction_policy": "credential_values_never_serialized",
        "health_check": "ok",
        "fallback_priority": 1,
    }
    res = validate_provider("test-prov", item)
    assert res["secret_redaction"] == "FAIL"

    # Redaction policy is absent
    item["required_credential_names"] = ["KEY"]
    item["redaction_policy"] = ""
    res = validate_provider("test-prov", item)
    assert res["secret_redaction"] == "FAIL"


def test_validator_fails_on_module_defects() -> None:
    item = {
        "provider_id": "test-prov",
        "module": "scripts.odds_sources.non_existent_module_foo_bar",  # missing module
        "sports_supported": ["football"],
        "transport": "https_json",
        "configuration_schema": {},
        "required_credential_names": ["KEY"],
        "base_url": "https://api.test.io",
        "connect_timeout_seconds": 3,
        "read_timeout_seconds": 10,
        "total_deadline_seconds": 15,
        "retry_count": 1,
        "retryable_conditions": ["ERROR"],
        "retry_after": "yes",
        "backoff": "exp",
        "cache_policy": "sha",
        "cache_ttl_seconds": 300,
        "stale_cache_behavior": "STALE_CACHE",
        "pagination": "yes",
        "parser_schema_version": "v1",
        "identity_fields": ["id"],
        "compliance_terms_status": "OK",
        "redaction_policy": "credential_values_never_serialized",
        "health_check": "ok",
        "fallback_priority": 1,
    }
    res = validate_provider("test-prov", item)
    assert res["module_importable"] is False


def test_validator_fails_on_divergent_adapter() -> None:
    item = {
        "provider_id": "divergent-prov-not-in-source-modules",
        "module": "scripts.odds_sources.oddspapi",
        "sports_supported": ["football"],
        "transport": "https_json",
        "configuration_schema": {},
        "required_credential_names": ["KEY"],
        "base_url": "https://api.test.io",
        "connect_timeout_seconds": 3,
        "read_timeout_seconds": 10,
        "total_deadline_seconds": 15,
        "retry_count": 1,
        "retryable_conditions": ["ERROR"],
        "retry_after": "yes",
        "backoff": "exp",
        "cache_policy": "sha",
        "cache_ttl_seconds": 300,
        "stale_cache_behavior": "STALE_CACHE",
        "pagination": "yes",
        "parser_schema_version": "v1",
        "identity_fields": ["id"],
        "compliance_terms_status": "OK",
        "redaction_policy": "credential_values_never_serialized",
        "health_check": "ok",
        "fallback_priority": 1,
    }
    res = validate_provider("divergent-prov-not-in-source-modules", item)
    # Finding must contain a warning about the fetch_odds_multi.py _SOURCE_MODULES divergence
    assert any(
        "not in the fetch_odds_multi.py _SOURCE_MODULES list" in f
        for f in res["findings"]
    )
