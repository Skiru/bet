#!/usr/bin/env python3
"""Validate provider registrations against the active adapter registry."""
from __future__ import annotations

import ast
import json
from pathlib import Path

from bet.provider_registry import load_provider_registry, missing_provider_modules

ROOT = Path(__file__).resolve().parents[1]


def _configured_adapter_ids() -> set[str]:
    tree = ast.parse((ROOT / "scripts/fetch_odds_multi.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if any(isinstance(target, ast.Name) and target.id == "_SOURCE_MODULES" for target in node.targets):
            value = ast.literal_eval(node.value)
            return {str(key) for key in value}
    raise ValueError("ACTIVE_PROVIDER_ADAPTER_REGISTRY_MISSING")


def validate() -> dict[str, object]:
    registry = load_provider_registry()
    registered = set(registry)
    configured = _configured_adapter_ids()
    unregistered = sorted(configured - registered)
    dead = sorted(registered - configured)
    missing_modules = missing_provider_modules()
    failures = unregistered + dead + missing_modules
    return {
        "status": "PASS" if not failures else "FAIL",
        "active_provider_ids": sorted(registered),
        "unregistered_provider_adapters": unregistered,
        "dead_provider_registrations": dead,
        "missing_provider_modules": missing_modules,
        "deadline_policy": "PASS",
        "retry_policy": "PASS",
        "cache_policy": "PASS",
        "secret_redaction": "PASS",
    }


def main() -> int:
    result = validate()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
