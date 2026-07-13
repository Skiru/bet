#!/usr/bin/env python3
"""Validate that production-reachable SQLite access uses the canonical layer."""
from __future__ import annotations

import ast
import json
from typing import Any

from scripts.validate_reachability_graph import ROOT, build, tracked_files

CANONICAL_FACTORY = "src/bet/db/connection.py"
MIGRATION_INTERNAL = "src/bet/db/schema.py"


def _calls(path: str) -> list[dict[str, Any]]:
    try:
        tree = ast.parse((ROOT / path).read_text(encoding="utf-8"), filename=path)
    except (OSError, SyntaxError, UnicodeError):
        return []
    findings: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = ""
        if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
            name = f"{node.func.value.id}.{node.func.attr}"
        elif isinstance(node.func, ast.Name):
            name = node.func.id
        if name not in {"sqlite3.connect", "aiosqlite.connect"}:
            continue
        findings.append(
            {
                "path": path,
                "caller": name,
                "line": node.lineno,
                "mode": "DECLARED_BY_CALLER",
                "transaction_owner": "caller",
                "connection_factory": path,
            }
        )
    return findings


def validate() -> dict[str, Any]:
    graph, _classification = build()
    runtime = set(graph["runtime_reachable_files"])
    inventory = [
        {**entry, "production_reachable": path in runtime}
        for path in tracked_files()
        if path.endswith(".py")
        for entry in _calls(path)
    ]
    for entry in inventory:
        path = entry["path"]
        if path == CANONICAL_FACTORY:
            category = "CANONICAL_CONNECTION_FACTORY"
        elif path == MIGRATION_INTERNAL:
            category = "MIGRATION_RUNNER_INTERNAL"
        elif path.startswith("tests/"):
            category = "ISOLATED_TEST_INFRASTRUCTURE"
        elif not entry["production_reachable"]:
            category = "OFFLINE_MAINTENANCE_UTILITY"
        else:
            category = "UNAUTHORIZED_RUNTIME_ACCESS"
        entry["allowed_exception_category"] = category
        entry["replacement"] = (
            CANONICAL_FACTORY if category == "UNAUTHORIZED_RUNTIME_ACCESS" else None
        )
    unauthorized = sorted(
        f"{entry['path']}:{entry['line']}"
        for entry in inventory
        if entry["allowed_exception_category"] == "UNAUTHORIZED_RUNTIME_ACCESS"
    )
    duplicate_factories = sorted(
        {
            str(entry["path"])
            for entry in inventory
            if entry["production_reachable"]
            and entry["path"] not in {CANONICAL_FACTORY, MIGRATION_INTERNAL}
        }
    )
    return {
        "status": "PASS" if not unauthorized and not duplicate_factories else "FAIL",
        "canonical_connection_factory": CANONICAL_FACTORY,
        "inventory": inventory,
        "unauthorized_direct_sqlite_access": unauthorized,
        "duplicate_db_factories": duplicate_factories,
    }


def main() -> int:
    result = validate()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
