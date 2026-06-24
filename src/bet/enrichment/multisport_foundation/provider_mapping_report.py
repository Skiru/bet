from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .provider_mapping import (
    TARGET_SPORTS,
    ProviderMappingStatus,
    build_provider_mapping_plan,
    validate_mapping_plan,
)

def write_provider_mapping_plan(path: str | Path, env: dict[str, str] | None = None) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if env is None:
        # Use only presence of keys in os.environ, mock values for safety,
        # never actual secrets in env.
        env = {k: "present" for k in os.environ if os.environ.get(k)}
    
    plan = build_provider_mapping_plan(env=env)
    errors = validate_mapping_plan(plan)
    if errors:
        raise ValueError(f"Mapping plan validation failed: {errors}")
        
    target.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")

def write_pass_e_summary(path: str | Path, env: dict[str, str] | None = None) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if env is None:
        env = {k: "present" for k in os.environ if os.environ.get(k)}
        
    plan = build_provider_mapping_plan(env=env)
    
    statuses: dict[str, str] = {}
    metrics = {
        "total_target_sports": len(TARGET_SPORTS),
        "mapping_ready_for_sanitized_probe_count": 0,
        "blocked_no_credentials_count": 0,
        "blocked_provider_terms_or_scope_count": 0,
        "blocked_provider_mapping_not_found_count": 0,
        "blocked_provider_access_count": 0,
        "live_calls_allowed": False,
        "production_activation": False,
        "betting_decisions": False,
    }
    
    mapping_by_sport = plan.get("provider_mapping_by_sport", {})
    for sport in TARGET_SPORTS:
        items = mapping_by_sport.get(sport, [])
        if items:
            # We take the status of the primary route
            primary_status = items[0]["status"]
            statuses[sport] = primary_status
        else:
            statuses[sport] = "BLOCKED_PROVIDER_MAPPING_NOT_FOUND"
            
        # Accumulate metrics
        for item in items:
            status = item["status"]
            if status == ProviderMappingStatus.MAPPING_READY_FOR_SANITIZED_PROBE:
                metrics["mapping_ready_for_sanitized_probe_count"] += 1
            elif status == ProviderMappingStatus.BLOCKED_NO_CREDENTIALS:
                metrics["blocked_no_credentials_count"] += 1
            elif status == ProviderMappingStatus.BLOCKED_PROVIDER_TERMS_OR_SCOPE:
                metrics["blocked_provider_terms_or_scope_count"] += 1
            elif status == ProviderMappingStatus.BLOCKED_PROVIDER_MAPPING_NOT_FOUND:
                metrics["blocked_provider_mapping_not_found_count"] += 1
            elif status == ProviderMappingStatus.BLOCKED_PROVIDER_ACCESS:
                metrics["blocked_provider_access_count"] += 1

    summary = {
        "summary_version": "ms-e-summary-v1",
        "target_sports": list(TARGET_SPORTS),
        "provider_mapping_statuses": statuses,
        "metrics": metrics,
    }
    
    target.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
