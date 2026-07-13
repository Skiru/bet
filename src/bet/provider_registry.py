"""Validated configuration authority for active odds providers."""
from __future__ import annotations

import importlib.util
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PACKAGED_REGISTRY_PATH = Path(__file__).with_name("config") / "provider_registry.json"
SOURCE_REGISTRY_PATH = Path(__file__).resolve().parents[2] / "config" / "provider_registry.json"
REGISTRY_PATH = (
    PACKAGED_REGISTRY_PATH if PACKAGED_REGISTRY_PATH.exists() else SOURCE_REGISTRY_PATH
)
REQUIRED_FIELDS = {
    "provider_id",
    "module",
    "sports_supported",
    "transport",
    "configuration_schema",
    "required_credential_names",
    "base_url",
    "connect_timeout_seconds",
    "read_timeout_seconds",
    "total_deadline_seconds",
    "retry_count",
    "retryable_conditions",
    "retry_after",
    "backoff",
    "cache_policy",
    "cache_ttl_seconds",
    "stale_cache_behavior",
    "pagination",
    "parser_schema_version",
    "identity_fields",
    "compliance_terms_status",
    "redaction_policy",
    "health_check",
    "fallback_priority",
}


@dataclass(frozen=True)
class ProviderRegistration:
    provider_id: str
    module: str
    policy: dict[str, Any]


def load_provider_registry(path: Path = REGISTRY_PATH) -> dict[str, ProviderRegistration]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("schema_version") != 1 or not isinstance(raw.get("providers"), list):
        raise ValueError("PROVIDER_REGISTRY_SCHEMA_INVALID")
    registry: dict[str, ProviderRegistration] = {}
    for item in raw["providers"]:
        if not isinstance(item, dict) or set(item) != REQUIRED_FIELDS:
            raise ValueError("PROVIDER_REGISTRATION_FIELDS_INVALID")
        provider_id = str(item["provider_id"])
        if provider_id in registry:
            raise ValueError("PROVIDER_ID_DUPLICATED")
        if min(
            float(item["connect_timeout_seconds"]),
            float(item["read_timeout_seconds"]),
            float(item["total_deadline_seconds"]),
        ) <= 0:
            raise ValueError("PROVIDER_DEADLINE_INVALID")
        if int(item["retry_count"]) < 0 or int(item["retry_count"]) > 3:
            raise ValueError("PROVIDER_RETRY_POLICY_INVALID")
        module = str(item["module"])
        registry[provider_id] = ProviderRegistration(provider_id, module, dict(item))
    return registry


def missing_provider_modules() -> list[str]:
    return sorted(
        registration.provider_id
        for registration in load_provider_registry().values()
        if importlib.util.find_spec(registration.module) is None
    )
