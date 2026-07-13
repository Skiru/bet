from __future__ import annotations

from bet.provider_registry import load_provider_registry, missing_provider_modules
from scripts.validate_provider_registry import validate


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

    assert result["status"] == "PASS", result
    assert result["unregistered_provider_adapters"] == []
    assert result["dead_provider_registrations"] == []
