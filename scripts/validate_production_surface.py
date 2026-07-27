#!/usr/bin/env python3
"""Fail-closed validation of the repository's real production surface."""

from __future__ import annotations

import ast
import json
import re
import tomllib
from collections import Counter
from pathlib import Path
import sys
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.validate_reachability_graph import (
    PRODUCTION_AGENTS,
    PRODUCTION_SKILLS,
    ROOT,
    tracked_files,
)
from scripts.validate_reachability_graph import (
    build as build_reachability,
)

CONFIG = ROOT / "config/production_surface.json"
EXPECTED_KEYS = {
    "$schema",
    "schema_version",
    "manifest",
    "canonical_entrypoints",
    "runtime_infrastructure",
    "domain_and_analytics",
    "providers",
    "database_runtime",
    "historical_migrations",
    "configuration",
    "betting_agents",
    "betting_skills",
    "engineering_tools",
    "validators",
    "tests",
    "fixtures",
    "documentation",
    "generated_ignored_roots",
    "forbidden_active_patterns",
    "forbidden_tracked_patterns",
}


def _expand(paths: list[str], tracked: set[str]) -> set[str]:
    expanded: set[str] = set()
    for path in paths:
        target = ROOT / path
        if target.is_file():
            expanded.add(path)
        elif target.is_dir():
            prefix = path.rstrip("/") + "/"
            expanded.update(item for item in tracked if item.startswith(prefix))
    return expanded


def _frontmatter(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n") or "\n---\n" not in text:
        return {}
    header = text.split("\n---\n", 1)[0][4:]
    result: dict[str, Any] = {}
    current: dict[str, str] | None = None
    for raw in header.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip())
        key, separator, value = raw.strip().partition(":")
        if not separator:
            continue
        if indent == 0:
            if value.strip():
                result[key] = value.strip().strip("\"'")
                current = None
            else:
                current = {}
                result[key] = current
        elif current is not None:
            current[key.strip("\"'")] = value.strip().strip("\"'")
    return result


def _direct_sqlite_access(active_python: set[str]) -> list[str]:
    allowed = {"src/bet/db/connection.py"}
    findings: list[str] = []
    for path in sorted(active_python - allowed):
        if path.startswith("tests/"):
            continue
        text = (ROOT / path).read_text(encoding="utf-8", errors="ignore")
        if re.search(r"\bsqlite3\.connect\s*\(", text):
            findings.append(path)
    return findings


def _database_factories(active_python: set[str]) -> list[str]:
    factories: list[str] = []
    for path in sorted(active_python):
        if path.startswith("tests/"):
            continue
        try:
            tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
        except (OSError, SyntaxError, UnicodeError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and re.search(
                r"(?:connect|connection|get_.*db|open_.*db)", node.name
            ):
                source = (
                    ast.get_source_segment(
                        (ROOT / path).read_text(encoding="utf-8"), node
                    )
                    or ""
                )
                if "sqlite" in source.lower():
                    factories.append(f"{path}:{node.name}")
    return factories


def _artifact_producer_conflicts(active_python: set[str]) -> list[str]:
    literal_targets: dict[str, set[str]] = {}
    for path in sorted(active_python):
        try:
            tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
        except (OSError, SyntaxError, UnicodeError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            function_name = ""
            if isinstance(node.func, ast.Name):
                function_name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                function_name = node.func.attr
            if function_name != "publish_run_artifact":
                continue
            target = next(
                (keyword.value for keyword in node.keywords if keyword.arg == "target"),
                None,
            )
            if isinstance(target, ast.Constant) and isinstance(target.value, str):
                literal_targets.setdefault(target.value, set()).add(path)
    return sorted(
        f"{target}:{','.join(sorted(paths))}"
        for target, paths in literal_targets.items()
        if len(paths) > 1
    )


def _agent_findings() -> dict[str, list[str]]:
    paths = sorted((ROOT / ".kilo/agents").glob("*.md"))
    extras = sorted(path.stem for path in paths if path.stem not in PRODUCTION_AGENTS)
    model_pins: list[str] = []
    recursive: list[str] = []
    excessive: list[str] = []
    for path in paths:
        if path.stem not in PRODUCTION_AGENTS:
            continue
        data = _frontmatter(path)
        if "model" in data or "provider" in data:
            model_pins.append(path.stem)
        permissions = data.get("permission", {})
        if not isinstance(permissions, dict):
            excessive.append(f"{path.stem}:permission")
            continue
        if path.stem != "bet-executor" and permissions.get("task") not in {
            None,
            "deny",
        }:
            recursive.append(path.stem)
        for mutation in ("edit", "write", "apply_patch"):
            if permissions.get(mutation) != "deny":
                excessive.append(f"{path.stem}:{mutation}")
        expected_bash = (
            "allow" if path.stem in {"bet-executor", "bet-auditor"} else "deny"
        )
        if permissions.get("bash") != expected_bash:
            excessive.append(f"{path.stem}:bash")
    return {
        "extra_agents": extras,
        "model_pins": sorted(model_pins),
        "recursive_delegation": sorted(recursive),
        "excessive_permissions": sorted(excessive),
    }


def validate() -> dict[str, object]:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    tracked = set(tracked_files())
    graph, classification = build_reachability()
    manifest = json.loads((ROOT / config["manifest"]).read_text(encoding="utf-8"))
    schema_errors: list[str] = []
    if set(config) != EXPECTED_KEYS:
        schema_errors.append("PRODUCTION_SURFACE_SCHEMA_KEYS_INVALID")
    if config.get("schema_version") != 2:
        schema_errors.append("PRODUCTION_SURFACE_SCHEMA_VERSION_INVALID")
    if any(
        not isinstance(config.get(key), list)
        for key in EXPECTED_KEYS - {"$schema", "schema_version", "manifest"}
    ):
        schema_errors.append("PRODUCTION_SURFACE_SCHEMA_VALUE_INVALID")

    category_keys = EXPECTED_KEYS - {
        "$schema",
        "schema_version",
        "manifest",
        "generated_ignored_roots",
        "forbidden_active_patterns",
        "forbidden_tracked_patterns",
    }
    declared = set().union(*(_expand(config[key], tracked) for key in category_keys))
    configured_paths = {path for key in category_keys for path in config[key]}
    missing_classified = sorted(
        path for path in configured_paths if not (ROOT / path).exists()
    )
    wrappers = {
        step["wrapper"]
        for step in manifest["steps"]
        if step.get("execution_mode") == "script" and step.get("wrapper")
    }
    missing_wrappers = sorted(path for path in wrappers if path not in tracked)
    unclassified_wrappers = sorted(wrappers - declared)

    runtime_reachable = set(graph["runtime_reachable_files"])
    active_python = {
        path for path in declared & runtime_reachable if path.endswith(".py")
    }
    historical = _expand(config["historical_migrations"], tracked)
    historical_runtime = {"src/bet/db/schema.py"}
    validation_only = _expand(config["validators"], tracked)
    active_scan = {
        path
        for path in declared & runtime_reachable
        if Path(path).suffix in {".json", ".py", ".sql", ".toml", ".yaml", ".yml"}
        and not path.startswith("tests/")
        and path not in historical
        and path not in historical_runtime
        and path not in validation_only
        and path != "config/production_surface.json"
    }
    active_betclic = sorted(
        path
        for path in active_scan
        if re.search(
            r"betclic",
            (ROOT / path).read_text(encoding="utf-8", errors="ignore"),
            re.IGNORECASE,
        )
    )
    active_schema_betclic = sorted(
        path
        for path in _expand(config["database_runtime"], tracked) - historical
        if Path(path).suffix == ".sql"
        and re.search(
            r"betclic",
            (ROOT / path).read_text(encoding="utf-8", errors="ignore"),
            re.IGNORECASE,
        )
    )
    generated_tracked = sorted(
        path
        for path, category in classification["files"].items()
        if category == "GENERATED_TRACKED_ERROR"
    )
    legacy_tracked = sorted(
        path
        for path, category in classification["files"].items()
        if category == "LEGACY_UNREACHABLE"
    )
    forbidden_tracked = sorted(
        path
        for path in tracked
        if any(
            re.search(pattern, path) for pattern in config["forbidden_tracked_patterns"]
        )
    )
    root_clutter = sorted(
        path
        for path in tracked
        if "/" not in path
        and (Path(path).suffix.lower() in {".zip", ".log"} or "backup" in path.lower())
    )
    config_duplicates = sorted(path for path in tracked if path.startswith("configs/"))

    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project_scripts = project.get("project", {}).get("scripts", {})
    missing_project_scripts = sorted(
        name
        for name, target in project_scripts.items()
        if not any(
            candidate in tracked
            for candidate in (
                "src/" + str(target).split(":", 1)[0].replace(".", "/") + ".py",
                "src/"
                + str(target).split(":", 1)[0].replace(".", "/")
                + "/__init__.py",
            )
        )
    )
    alternate_entrypoints = sorted(
        path
        for path in tracked
        if (
            re.fullmatch(r"scripts/pipeline_(?!steps/).+\.py", path)
            or re.fullmatch(r"scripts/run_.+session\.py", path)
        )
        and path not in config["canonical_entrypoints"]
    )
    database_factories = _database_factories(active_python)
    duplicate_database_factories = sorted(
        factory
        for factory in database_factories
        if not factory.startswith("src/bet/db/connection.py:")
    )

    agent_findings = _agent_findings()
    actual_skills = {
        path.parent.name for path in (ROOT / ".kilo/skills").glob("*/SKILL.md")
    }
    extra_skills = sorted(actual_skills - PRODUCTION_SKILLS)
    missing_skills = sorted(PRODUCTION_SKILLS - actual_skills)
    stale_docs = sorted(
        path
        for path in _expand(config["documentation"], tracked)
        if re.search(
            r"(?i)betting pipeline with langgraph orchestration|"
            r"active betclic (?:runtime|operator|integration)",
            (ROOT / path).read_text(encoding="utf-8", errors="ignore"),
        )
    )

    result: dict[str, object] = {
        "canonical_entrypoint": config["canonical_entrypoints"][0],
        "active_graph_complete": not missing_wrappers and not unclassified_wrappers,
        "unknown_reachable_files": classification["unknown_files"],
        "imports_escaping_surface": graph["runtime_classification_escapes"],
        "root_classification_violations": graph["root_classification_violations"],
        "missing_manifest_wrappers": missing_wrappers,
        "unclassified_manifest_wrappers": unclassified_wrappers,
        "missing_classified_files": missing_classified,
        "missing_project_scripts": missing_project_scripts,
        "duplicate_entrypoints": alternate_entrypoints,
        "alternate_production_entrypoints": alternate_entrypoints,
        "duplicate_artifact_producers": _artifact_producer_conflicts(active_python),
        "database_connection_factories": database_factories,
        "duplicate_database_connection_factories": duplicate_database_factories,
        "direct_unclassified_sqlite_access": _direct_sqlite_access(active_python),
        "active_betclic_references": active_betclic,
        "active_schema_betclic_references": active_schema_betclic,
        "historical_migration_references": sorted(historical | historical_runtime),
        "legacy_active_references": graph["runtime_classification_escapes"],
        "extra_production_agents": agent_findings["extra_agents"],
        "agent_model_pins": agent_findings["model_pins"],
        "recursive_delegation": agent_findings["recursive_delegation"],
        "excessive_agent_permissions": agent_findings["excessive_permissions"],
        "extra_production_skills": extra_skills,
        "missing_production_skills": missing_skills,
        "generated_tracked_files": sorted(set(generated_tracked + forbidden_tracked)),
        "legacy_tracked_files": legacy_tracked,
        "duplicate_configuration_authorities": config_duplicates,
        "root_clutter": root_clutter,
        "stale_documentation": stale_docs,
        "unsafe_deletions": [],
        "schema_errors": schema_errors,
    }
    blocking_keys = {
        "unknown_reachable_files",
        "imports_escaping_surface",
        "root_classification_violations",
        "missing_manifest_wrappers",
        "unclassified_manifest_wrappers",
        "missing_classified_files",
        "missing_project_scripts",
        "duplicate_entrypoints",
        "duplicate_artifact_producers",
        "duplicate_database_connection_factories",
        "direct_unclassified_sqlite_access",
        "active_betclic_references",
        "active_schema_betclic_references",
        "extra_production_agents",
        "agent_model_pins",
        "recursive_delegation",
        "excessive_agent_permissions",
        "extra_production_skills",
        "missing_production_skills",
        "generated_tracked_files",
        "legacy_tracked_files",
        "duplicate_configuration_authorities",
        "root_clutter",
        "stale_documentation",
        "schema_errors",
    }
    failures = sorted(key for key in blocking_keys if result[key])
    result["errors"] = failures
    result["status"] = "PASS" if not failures else "BLOCK"
    result["metrics"] = {
        "tracked_files": len(tracked),
        "declared_files": len(declared),
        "classification_counts": dict(Counter(classification["files"].values())),
    }
    return result


def main() -> int:
    result = validate()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
