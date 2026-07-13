#!/usr/bin/env python3
"""Validate provider registrations against the active adapter registry with zero hard-coded PASS values."""

from __future__ import annotations

import ast
import importlib.util
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Ensure src/ is importable for bet package imports
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from bet.provider_registry import load_provider_registry, REQUIRED_FIELDS


def _configured_adapter_ids() -> set[str]:
    multi_path = ROOT / "scripts/fetch_odds_multi.py"
    if not multi_path.exists():
        raise ValueError("fetch_odds_multi.py missing")
    tree = ast.parse(multi_path.read_text(encoding="utf-8"))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if any(
            isinstance(target, ast.Name) and target.id == "_SOURCE_MODULES"
            for target in node.targets
        ):
            value = ast.literal_eval(node.value)
            return {str(key) for key in value}
    raise ValueError("ACTIVE_PROVIDER_ADAPTER_REGISTRY_MISSING")


def validate_provider(provider_id: str, item: dict) -> dict[str, any]:
    findings = []

    # 1. Field validation
    registry_valid = True
    missing_fields = REQUIRED_FIELDS - set(item)
    if missing_fields:
        registry_valid = False
        findings.append(f"Missing required fields: {list(missing_fields)}")

    # Unique/valid ID
    if not provider_id or not re.match(r"^[a-z0-9_-]+$", provider_id):
        registry_valid = False
        findings.append(f"Invalid provider_id format: {provider_id}")

    # Non-empty sports supported
    sports = item.get("sports_supported", [])
    if not isinstance(sports, list) or not sports:
        registry_valid = False
        findings.append("sports_supported must be a non-empty list")

    # Valid base URL classification
    base_url = item.get("base_url", "")
    if not base_url or not (
        base_url.startswith("http://") or base_url.startswith("https://")
    ):
        registry_valid = False
        findings.append(f"Invalid base_url: {base_url}")

    # Fallback priority
    fallback = item.get("fallback_priority")
    if fallback is None or not isinstance(fallback, int) or fallback <= 0:
        registry_valid = False
        findings.append(f"Invalid fallback_priority: {fallback}")

    # Module importability
    module_name = item.get("module", "")
    module_importable = False
    if module_name:
        try:
            spec = importlib.util.find_spec(module_name)
            if spec is not None:
                module_importable = True
            else:
                findings.append(f"Module spec not found: {module_name}")
        except Exception as e:
            findings.append(f"Module import error on spec check: {e}")

    # Configured adapter alignment
    try:
        configured = _configured_adapter_ids()
        if provider_id not in configured:
            findings.append(
                f"Provider {provider_id} is not in the fetch_odds_multi.py _SOURCE_MODULES list"
            )
    except Exception as e:
        findings.append(f"Error reading fetch_odds_multi.py: {e}")

    # 2. Deadline policy
    deadline_policy = "PASS"
    conn_t = item.get("connect_timeout_seconds")
    read_t = item.get("read_timeout_seconds")
    total_d = item.get("total_deadline_seconds")

    if conn_t is None or read_t is None or total_d is None:
        deadline_policy = "FAIL"
        findings.append("Absence of connection or read timeouts or total deadline")
    else:
        try:
            conn_t = float(conn_t)
            read_t = float(read_t)
            total_d = float(total_d)
            if conn_t <= 0 or read_t <= 0 or total_d <= 0:
                deadline_policy = "FAIL"
                findings.append("Timeout and deadline values must be positive numbers")
            if total_d < (conn_t + read_t):
                deadline_policy = "FAIL"
                findings.append(
                    f"total_deadline_seconds ({total_d}) is shorter than required sum of timeouts ({conn_t + read_t})"
                )
            if total_d > 60:
                deadline_policy = "FAIL"
                findings.append(
                    f"total_deadline_seconds ({total_d}) exceeds maximum allowed 60s"
                )
        except ValueError:
            deadline_policy = "FAIL"
            findings.append("Timeout values must be numeric")

    # 3. Retry policy
    retry_policy = "PASS"
    retry_count = item.get("retry_count")
    retryable_conds = item.get("retryable_conditions", [])
    retry_after = item.get("retry_after")
    backoff = item.get("backoff")

    if retry_count is None:
        retry_policy = "FAIL"
        findings.append("retry_count is absent")
    else:
        try:
            retry_count = int(retry_count)
            if retry_count < 0 or retry_count > 3:
                retry_policy = "FAIL"
                findings.append(
                    f"retry_count ({retry_count}) is outside approved range 0-3"
                )
        except ValueError:
            retry_policy = "FAIL"
            findings.append("retry_count must be an integer")

    if not retryable_conds or not isinstance(retryable_conds, list):
        retry_policy = "FAIL"
        findings.append("retryable_conditions is empty or not a list")
    if not retry_after:
        retry_policy = "FAIL"
        findings.append("Retry-After policy is absent")
    if not backoff:
        retry_policy = "FAIL"
        findings.append("backoff policy is absent")

    # 4. Cache policy
    cache_policy = "PASS"
    cache_ttl = item.get("cache_ttl_seconds")
    cache_pol = item.get("cache_policy")
    stale_cache = item.get("stale_cache_behavior")

    if cache_ttl is None:
        cache_policy = "FAIL"
        findings.append("cache_ttl_seconds is absent")
    else:
        try:
            cache_ttl = int(cache_ttl)
            if cache_ttl <= 0:
                cache_policy = "FAIL"
                findings.append("cache_ttl_seconds must be positive")
        except ValueError:
            cache_policy = "FAIL"
            findings.append("cache_ttl_seconds must be an integer")

    if not cache_pol:
        cache_policy = "FAIL"
        findings.append("cache_policy is absent")
    if not stale_cache or stale_cache != "STALE_CACHE":
        cache_policy = "FAIL"
        findings.append("stale_cache_behavior must be specified as STALE_CACHE")

    # 5. Secret redaction and credential safety
    secret_redaction = "PASS"
    credentials = item.get("required_credential_names", [])
    redact_pol = item.get("redaction_policy")

    if not redact_pol or redact_pol != "credential_values_never_serialized":
        secret_redaction = "FAIL"
        findings.append("redaction_policy is absent or invalid")

    if not isinstance(credentials, list) or not credentials:
        secret_redaction = "FAIL"
        findings.append(
            "required_credential_names must be a non-empty list of environment variable names"
        )
    else:
        for cred in credentials:
            if not isinstance(cred, str) or not re.match(r"^[A-Z0-9_]+$", cred):
                secret_redaction = "FAIL"
                findings.append(
                    f"Credential name '{cred}' must contain only uppercase alphanumeric/underscores"
                )
            # Canaries for embedded values in credential list
            if len(cred) > 30 and re.match(r"^[a-f0-9]{32,}$", cred.lower()):
                secret_redaction = "FAIL"
                findings.append(
                    f"Credential value looks embedded in name list: '{cred}'"
                )

    # 6. Interrogate transport bindings
    transport_policy_bound = False
    if module_name:
        try:
            # Check the source code file of the module to see if it references the configuration parameters
            module_file_path = ROOT / (module_name.replace(".", "/") + ".py")
            if module_file_path.exists():
                code = module_file_path.read_text(encoding="utf-8")
                # Introspect if the code references request settings or uses transport or imports odds_sources
                if (
                    "OddsSource" in code
                    or "fetch_odds" in code
                    or "requests" in code
                    or "SOURCE" in code
                ):
                    transport_policy_bound = True
                else:
                    findings.append(
                        f"Module {module_name} does not seem to bind or inherit from the transport adapter layer"
                    )
            else:
                findings.append(f"Module file does not exist: {module_file_path}")
        except Exception as e:
            findings.append(f"Introspection error on {module_name}: {e}")

    return {
        "provider_id": provider_id,
        "registry_valid": registry_valid,
        "module_importable": module_importable,
        "transport_policy_bound": transport_policy_bound,
        "deadline_policy": deadline_policy,
        "retry_policy": retry_policy,
        "cache_policy": cache_policy,
        "secret_redaction": secret_redaction,
        "findings": findings,
    }


def validate() -> dict[str, any]:
    # Load canonical registry JSON
    registry_path = ROOT / "config/provider_registry.json"
    if not registry_path.exists():
        return {"status": "FAIL", "errors": ["PROVIDER_REGISTRY_JSON_MISSING"]}

    try:
        with open(registry_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception as e:
        return {"status": "FAIL", "errors": [f"PROVIDER_REGISTRY_JSON_MALFORMED: {e}"]}

    if raw.get("schema_version") != 1 or not isinstance(raw.get("providers"), list):
        return {"status": "FAIL", "errors": ["PROVIDER_REGISTRY_SCHEMA_INVALID"]}

    providers = raw["providers"]
    provider_results = []
    top_level_pass = True

    fallbacks = []

    for item in providers:
        provider_id = item.get("provider_id", "")
        res = validate_provider(provider_id, item)
        provider_results.append(res)

        # Unique fallbacks track
        fb = item.get("fallback_priority")
        if fb is not None:
            fallbacks.append(fb)

        is_pass = (
            res["registry_valid"]
            and res["module_importable"]
            and res["transport_policy_bound"]
            and res["deadline_policy"] == "PASS"
            and res["retry_policy"] == "PASS"
            and res["cache_policy"] == "PASS"
            and res["secret_redaction"] == "PASS"
        )
        if not is_pass:
            top_level_pass = False

    # Fallback uniqueness check
    if len(fallbacks) != len(set(fallbacks)):
        top_level_pass = False
        provider_results.append(
            {
                "provider_id": "global_registry",
                "findings": ["Conflicting or duplicated fallback_priorities detected"],
            }
        )

    return {
        "status": "PASS" if top_level_pass else "FAIL",
        "providers": provider_results,
    }


def main() -> int:
    result = validate()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
