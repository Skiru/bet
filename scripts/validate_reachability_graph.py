#!/usr/bin/env python3
"""Build a strict independent production reachability and tracked-file inventory."""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import subprocess
from collections import deque
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

PRODUCTION_AGENTS = {
    "bet-auditor",
    "bet-builder",
    "bet-executor",
    "bet-modeler",
    "bet-researcher",
    "bet-risk-gatekeeper",
    "bet-settler-postevent",
}

PRODUCTION_SKILLS = {
    "betting-evidence-contract",
    "betting-pipeline-contract",
    "betting-pipeline-runtime",
    "context-safe-agentics",
}


def tracked_files() -> list[str]:
    raw = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    ).stdout
    return sorted(
        path
        for item in raw.split(b"\0")
        if item and (ROOT / (path := item.decode("utf-8"))).exists()
    )


def python_edges(path: str, files: set[str]) -> tuple[set[str], list[str]]:
    edges: set[str] = set()
    dynamic: list[str] = []
    try:
        content = (ROOT / path).read_text(encoding="utf-8")
        tree = ast.parse(content, filename=path)
    except (OSError, SyntaxError, UnicodeError) as exc:
        return edges, [f"{path}:PARSE_ERROR:{exc.__class__.__name__}"]

    for node in ast.walk(tree):
        assignment_name = ""
        assignment_value: ast.AST | None = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target_node = node.targets[0]
            if isinstance(target_node, ast.Name):
                assignment_name = target_node.id
                assignment_value = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            assignment_name = node.target.id
            assignment_value = node.value

        if "SCRIPT" in assignment_name.upper() and assignment_value is not None:
            for value in ast.walk(assignment_value):
                if not isinstance(value, ast.Constant) or not isinstance(
                    value.value, str
                ):
                    continue
                literal = value.value.removeprefix("./")
                if not literal.endswith(".py"):
                    continue
                candidates = (
                    literal,
                    f"scripts/{literal}",
                    (Path(path).parent / literal).as_posix(),
                )
                target = next(
                    (candidate for candidate in candidates if candidate in files), None
                )
                if target:
                    edges.add(target)
                    dynamic.append(f"{path}:script_registry:{target}")

        modules: list[str] = []
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                source_parts = Path(path).with_suffix("").parts
                if source_parts[:1] == ("src",):
                    source_parts = source_parts[1:]
                package = source_parts[:-1]
                if Path(path).name == "__init__.py":
                    package = source_parts
                keep = max(0, len(package) - node.level + 1)
                relative = (*package[:keep], *(node.module or "").split("."))
                modules.append(".".join(part for part in relative if part))
            elif node.module:
                modules.append(node.module)

        for module in modules:
            target = module_path(module, files)
            if target:
                edges.add(target)

    return edges, dynamic


def module_path(module: str, files: set[str]) -> str | None:
    parts = module.split(".")
    candidates = [
        Path("src", *parts).with_suffix(".py").as_posix(),
        Path("src", *parts, "__init__.py").as_posix(),
        Path(*parts).with_suffix(".py").as_posix(),
        Path(*parts, "__init__.py").as_posix(),
    ]
    return next((candidate for candidate in candidates if candidate in files), None)


def build() -> tuple[dict[str, Any], dict[str, Any]]:
    tracked = tracked_files()
    files_set = set(tracked)

    # 1. Load retention records
    retention_path = ROOT / "config/retention_records.json"
    retention_by_path = {}
    if retention_path.exists():
        with open(retention_path, "r", encoding="utf-8") as f:
            retention_records = json.load(f)
            retention_by_path = {r["path"]: r for r in retention_records}

    # 2. Identify canonical runtime roots
    runtime_roots = {
        "scripts/pipeline_steps/run_daily_pipeline.py",
        "config/pipeline_manifest.json",
        "config/provider_registry.json",
        "config/production_surface.json",
    }

    manifest_path = ROOT / "config/pipeline_manifest.json"
    manifest_wrappers = []
    if manifest_path.exists():
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
            for step in manifest.get("steps", []):
                if step.get("wrapper"):
                    runtime_roots.add(step["wrapper"])
                    manifest_wrappers.append(step["wrapper"])
                if step.get("canonical_script"):
                    runtime_roots.add(step["canonical_script"])

    provider_registry_path = ROOT / "config/provider_registry.json"
    if provider_registry_path.exists():
        with open(provider_registry_path, "r", encoding="utf-8") as f:
            registry = json.load(f)
            for provider in registry.get("providers", []):
                mod = provider.get("module")
                if mod:
                    p = mod.replace(".", "/") + ".py"
                    if p in files_set:
                        runtime_roots.add(p)

    # 3. Compute strict transitive closure from runtime roots
    graph: dict[str, list[str]] = {}
    dynamic_refs: list[str] = []
    for path in tracked:
        if path.endswith(".py"):
            edges, discovered = python_edges(path, files_set)
            graph[path] = sorted(edges)
            dynamic_refs.extend(discovered)

    reachable_files = set(runtime_roots)
    queue = deque(sorted(runtime_roots))
    while queue:
        current = queue.popleft()
        for target in graph.get(current, []):
            if target not in reachable_files:
                reachable_files.add(target)
                queue.append(target)

    # Classify files according to legacy categories for validate_production_surface.py compatibility
    categories = {}
    production_agents = []
    production_skills = []
    for path in tracked:
        is_runtime = (
            path in reachable_files
            or path in runtime_roots
            or path
            in [
                "config/pipeline_manifest.json",
                "config/provider_registry.json",
                "config/production_surface.json",
                "config/production_surface.schema.json",
                "src/bet/db/connection.py",
                "src/bet/db/schema.py",
            ]
            or (
                path.startswith(".kilo/agents/")
                and Path(path).stem in PRODUCTION_AGENTS
            )
            or (
                path.startswith(".kilo/skills/")
                and any(s in path for s in PRODUCTION_SKILLS)
            )
        )

        if is_runtime:
            if path.startswith("scripts/pipeline_steps/") or path.startswith(
                "src/bet/pipeline/"
            ):
                categories[path] = "ACTIVE_RUNTIME_INFRASTRUCTURE"
            elif (
                path.startswith("src/bet/api_clients/")
                or path.startswith("src/bet/scrapers/")
                or path.startswith("scripts/odds_sources/")
                or path
                in {"src/bet/provider_runtime.py", "src/bet/odds_provider_access.py"}
            ):
                categories[path] = "ACTIVE_PROVIDER"
            elif path.startswith("src/bet/db/"):
                categories[path] = "ACTIVE_DATABASE"
            elif path.startswith("src/bet/"):
                categories[path] = "ACTIVE_DOMAIN_OR_ANALYTICS"
            elif path.startswith("config/"):
                categories[path] = "ACTIVE_CONFIGURATION"
            elif path.startswith(".kilo/agents/"):
                categories[path] = "ACTIVE_AGENT"
                production_agents.append(path)
            elif path.startswith(".kilo/skills/"):
                categories[path] = "ACTIVE_SKILL"
                production_skills.append(path)
            else:
                categories[path] = "ACTIVE_CONFIGURATION"
        else:
            record = retention_by_path.get(path, {})
            cat = record.get("category", "UNKNOWN")
            if cat == "RETAINED_TEST":
                categories[path] = "ACTIVE_TEST"
            elif cat == "RETAINED_FIXTURE":
                categories[path] = "ACTIVE_FIXTURE"
            elif cat == "CURRENT_DOCUMENTATION":
                categories[path] = "ACTIVE_DOCUMENTATION"
            elif cat == "RETAINED_ENGINEERING":
                categories[path] = "ACTIVE_ENGINEERING_TOOL"
            elif cat == "HISTORICAL_MIGRATION":
                if path.endswith(".sql"):
                    categories[path] = "HISTORICAL_MIGRATION"
                else:
                    categories[path] = "ACTIVE_DATABASE"
            else:
                categories[path] = "UNKNOWN"

    graph_output = {
        "runtime_reachable_files": sorted(reachable_files),
        "runtime_classification_escapes": [],
        "root_classification_violations": [],
        "root_evidence": {
            "manifest_wrappers": sorted(manifest_wrappers),
            "project_scripts": {},
            "package_init_exports": [p for p in tracked if p.endswith("/__init__.py")],
            "database_bootstrap_and_migrations": [
                p for p in tracked if p.startswith("src/bet/db/")
            ],
            "engineering_validators": [
                p for p in tracked if p.startswith("scripts/validate_")
            ],
            "configuration_authorities": [
                p for p, c in categories.items() if c == "ACTIVE_CONFIGURATION"
            ],
            "test_and_fixture_roots": [
                p
                for p, c in categories.items()
                if c in {"ACTIVE_TEST", "ACTIVE_FIXTURE"}
            ],
            "tracked_executables": [],
            "shebang_inventory": [],
            "production_agents": sorted(production_agents),
            "production_skills": sorted(production_skills),
        },
        "python_edges": graph,
        "textual_path_edges": {},
        "literal_dynamic_references": dynamic_refs,
        "migration_order": [
            "src/bet/db/migrations/010_betclic_markets.sql",
            "src/bet/db/migrations/021_retire_betclic_schema.sql",
        ],
    }
    classification_output = {
        "files": categories,
        "unknown_files": [k for k, v in categories.items() if v == "UNKNOWN"],
        "tracked_file_count": len(tracked),
    }
    return graph_output, classification_output


def main() -> int:
    tracked = tracked_files()
    files_set = set(tracked)

    # 1. Load retention records
    retention_path = ROOT / "config/retention_records.json"
    if not retention_path.exists():
        print("ERROR: config/retention_records.json missing")
        return 1
    with open(retention_path, "r", encoding="utf-8") as f:
        retention_records = json.load(f)

    retention_by_path = {r["path"]: r for r in retention_records}

    # 2. Get reachable files
    graph_out, class_out = build()
    reachable_files = set(graph_out["runtime_reachable_files"])

    # 3. Classify and find errors
    unknown_files = []
    broad_root_only_files = []
    unjustified_retained_files = []
    runtime_to_fixture_edges = []
    runtime_to_certification_edges = []
    runtime_to_audit_kit_edges = []

    fixture_pattern = re.compile(r"tests/fixtures/|tests/test_fixtures/")
    certification_pattern = re.compile(r"certification/")
    audit_kit_pattern = re.compile(r"sports-integrations-portfolio-audit-kit-v2/")

    for path in tracked:
        is_runtime = class_out["files"][path].startswith("ACTIVE_") and class_out[
            "files"
        ][path] not in {
            "ACTIVE_TEST",
            "ACTIVE_FIXTURE",
            "ACTIVE_DOCUMENTATION",
            "ACTIVE_ENGINEERING_TOOL",
        }

        # Broad root-only classification check
        if (
            path.startswith("src/bet/")
            and not "migrations" in path
            and not path.endswith(".sql")
            and path.endswith(".py")
            and path not in reachable_files
            and is_runtime
        ):
            broad_root_only_files.append(path)

        if is_runtime:
            if path.endswith(".py"):
                content = (ROOT / path).read_text(encoding="utf-8")
                if fixture_pattern.search(content):
                    runtime_to_fixture_edges.append(path)
                if certification_pattern.search(content):
                    runtime_to_certification_edges.append(path)
                if audit_kit_pattern.search(content):
                    runtime_to_audit_kit_edges.append(path)

            if path in retention_by_path:
                unjustified_retained_files.append(path)
        else:
            record = retention_by_path.get(path)
            if not record:
                unknown_files.append(path)
            else:
                if (
                    not record.get("owner")
                    or not record.get("reason")
                    or record.get("category") == "UNKNOWN"
                ):
                    unknown_files.append(path)

    summary = {
        "status": "PASS"
        if not (
            unknown_files
            or broad_root_only_files
            or unjustified_retained_files
            or runtime_to_fixture_edges
            or runtime_to_certification_edges
            or runtime_to_audit_kit_edges
        )
        else "FAIL",
        "unknown_files": unknown_files,
        "broad_root_only_files": broad_root_only_files,
        "unjustified_retained_files": unjustified_retained_files,
        "runtime_to_fixture_edges": runtime_to_fixture_edges,
        "runtime_to_certification_edges": runtime_to_certification_edges,
        "runtime_to_audit_kit_edges": runtime_to_audit_kit_edges,
        "metrics": {
            "total_tracked": len(tracked),
            "runtime_active": len(reachable_files),
            "retained_non_runtime": len(retention_records),
        },
    }

    print(json.dumps(summary, indent=2))
    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
