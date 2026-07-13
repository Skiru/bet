#!/usr/bin/env python3
"""Build an independent production reachability and tracked-file inventory."""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import tomllib
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
RUNTIME_MODULES = {
    "analysis_status.py",
    "artifact_gate.py",
    "artifact_io.py",
    "event_accounting.py",
    "integration_artifacts.py",
    "manifest.py",
    "orchestrator.py",
    "readiness_contracts.py",
    "run_coordination.py",
    "runtime_modes.py",
    "runtime_paths.py",
}
GENERATED_ROOTS = (
    ".kilo/artifacts/",
    "betting/coupons/",
    "reports/",
)
ROOT_CONFIGURATION = {
    ".env.example",
    ".gitattributes",
    ".gitignore",
    ".kilocodeignore",
    "AGENTS.md",
    "pyproject.toml",
    "uv.lock",
}
LEGACY_LANES = {
    "docs/pipeline/Daily Manual Session Runbook.md",
    "docs/pipeline/Full Pipeline Shadow Acceptance Runbook.md",
    "docs/pipeline/Live Session Universe Runbook.md",
    "docs/pipeline/Manual Low Stake Pilot Runbook.md",
    "docs/pipeline/Paper Trading Readiness Runbook.md",
    "docs/pipeline/Rich Coupon Package Runbook.md",
    "scripts/pipeline_daily_manual_session.py",
    "scripts/pipeline_full_shadow_acceptance.py",
    "scripts/pipeline_live_session_universe.py",
    "scripts/pipeline_manual_low_stake_pilot.py",
    "scripts/pipeline_paper_trading_readiness.py",
    "scripts/pipeline_rich_coupon_package.py",
    "scripts/run_unified_live_analyst_session.py",
    "src/bet/pipeline/daily_manual_session.py",
    "src/bet/pipeline/full_shadow_acceptance.py",
    "src/bet/pipeline/manual_low_stake_pilot.py",
    "src/bet/pipeline/paper_trading.py",
    "src/bet/pipeline/rich_coupon_package.py",
    "tests/test_mock_odds_production_safety.py",
    "tests/test_pipeline_daily_manual_session.py",
    "tests/test_pipeline_full_shadow_acceptance.py",
    "tests/test_pipeline_manual_low_stake_pilot.py",
    "tests/test_pipeline_paper_trading_readiness.py",
    "tests/test_pipeline_rich_coupon_package.py",
}


def tracked_files() -> list[str]:
    raw = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    ).stdout
    return sorted(
        path
        for item in raw.split(b"\0")
        if item
        and (ROOT / (path := item.decode("utf-8"))).exists()
    )


def classify(path: str) -> str:
    item = Path(path)
    suffix = item.suffix.lower()
    if path in LEGACY_LANES:
        return "LEGACY_UNREACHABLE"
    if path.startswith(GENERATED_ROOTS):
        return "GENERATED_TRACKED_ERROR"
    if item.parent == Path("."):
        if path in ROOT_CONFIGURATION:
            return "ACTIVE_CONFIGURATION"
        if path in {"ARCHITECTURE.md", "README.md"}:
            return "ACTIVE_DOCUMENTATION"
        if (
            suffix in {".zip", ".log"}
            or "backup" in path.lower()
            or path.startswith(".tmp")
        ):
            return "GENERATED_TRACKED_ERROR"
        if suffix in {".md", ".txt", ".json"}:
            return "LEGACY_UNREACHABLE"
    if path.startswith("config/"):
        return "ACTIVE_CONFIGURATION"
    if path.startswith("configs/"):
        return "LEGACY_UNREACHABLE"
    if path.startswith(".github/") or path.startswith(".kilo/commands/"):
        return "ACTIVE_CONFIGURATION"
    if path.startswith(".kilo/agents/"):
        return (
            "ACTIVE_AGENT" if item.stem in PRODUCTION_AGENTS else "LEGACY_UNREACHABLE"
        )
    if path.startswith(".kilo/skills/"):
        parts = item.parts
        return (
            "ACTIVE_SKILL"
            if len(parts) > 2 and parts[2] in PRODUCTION_SKILLS
            else "LEGACY_UNREACHABLE"
        )
    if (
        path.startswith(".kilo/rules/")
        or path.startswith(".kilo/shared/")
        or path.startswith(".kilo/state/")
        or path == ".kilo/CONTEXT_POLICY.md"
    ):
        return "ACTIVE_CONFIGURATION"
    if path.startswith(".kilo/docs/"):
        return "ACTIVE_DOCUMENTATION"
    if (
        path.startswith(".kilo/")
        or path.startswith(".implementation/")
        or path.startswith("archive/")
    ):
        return "LEGACY_UNREACHABLE"
    if path.startswith("tests/fixtures/") or "/fixtures/" in path:
        return "ACTIVE_FIXTURE"
    if path.startswith("tests/") or path == "conftest.py":
        return "ACTIVE_TEST"
    if path.startswith("docs/"):
        return "ACTIVE_DOCUMENTATION"
    if path.startswith("src/bet/db/"):
        return "ACTIVE_DATABASE"
    if path.startswith("src/bet/pipeline/") and item.name in RUNTIME_MODULES:
        return "ACTIVE_RUNTIME_INFRASTRUCTURE"
    if path.startswith("src/bet/api_clients/") or path.startswith("src/bet/scrapers/"):
        return "ACTIVE_PROVIDER"
    if path in {"src/bet/provider_runtime.py", "src/bet/odds_provider_access.py"}:
        return "ACTIVE_PROVIDER"
    if path.startswith("src/bet/"):
        return "ACTIVE_DOMAIN_OR_ANALYTICS"
    if path.startswith("src/"):
        return "LEGACY_UNREACHABLE"
    if path.startswith("scripts/pipeline_steps/"):
        return "ACTIVE_RUNTIME_INFRASTRUCTURE"
    if path.startswith("scripts/odds_sources/") or "provider" in item.name.lower():
        return "ACTIVE_PROVIDER"
    if path.startswith("scripts/"):
        if item.name.startswith(("pipeline_", "run_unified_")):
            return "LEGACY_UNREACHABLE"
        return "ACTIVE_ENGINEERING_TOOL"
    if path.startswith("betting/"):
        return "GENERATED_TRACKED_ERROR"
    if suffix in {".md", ".rst"}:
        return "ACTIVE_DOCUMENTATION"
    if suffix in {".json", ".yaml", ".yml", ".toml"}:
        return "ACTIVE_CONFIGURATION"
    return "UNKNOWN"


def module_path(module: str, files: set[str]) -> str | None:
    parts = module.split(".")
    candidates = [
        Path("src", *parts).with_suffix(".py").as_posix(),
        Path("src", *parts, "__init__.py").as_posix(),
        Path(*parts).with_suffix(".py").as_posix(),
        Path(*parts, "__init__.py").as_posix(),
    ]
    return next((candidate for candidate in candidates if candidate in files), None)


def literal_strings(node: ast.AST) -> list[str]:
    if isinstance(node, (ast.List, ast.Tuple)):
        return [
            value.value
            for value in node.elts
            if isinstance(value, ast.Constant) and isinstance(value.value, str)
        ]
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    return []


def python_edges(path: str, files: set[str]) -> tuple[set[str], list[str]]:
    edges: set[str] = set()
    dynamic: list[str] = []
    try:
        tree = ast.parse((ROOT / path).read_text(encoding="utf-8"), filename=path)
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
                if not isinstance(value, ast.Constant) or not isinstance(value.value, str):
                    continue
                literal = value.value.removeprefix("./")
                if not literal.endswith(".py"):
                    continue
                candidates = (
                    literal,
                    f"scripts/{literal}",
                    (Path(path).parent / literal).as_posix(),
                )
                target = next((candidate for candidate in candidates if candidate in files), None)
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
        if not isinstance(node, ast.Call):
            continue
        name = ""
        if isinstance(node.func, ast.Attribute) and isinstance(
            node.func.value, ast.Name
        ):
            name = f"{node.func.value.id}.{node.func.attr}"
        elif isinstance(node.func, ast.Name):
            name = node.func.id
        if (
            name in {"import_module", "importlib.import_module", "__import__"}
            and node.args
        ):
            values = literal_strings(node.args[0])
            if values:
                target = module_path(values[0], files)
                if target:
                    edges.add(target)
                dynamic.append(f"{path}:{name}:{values[0]}")
        if (
            name
            in {
                "subprocess.run",
                "subprocess.Popen",
                "subprocess.call",
                "subprocess.check_call",
                "subprocess.check_output",
            }
            and node.args
        ):
            for literal_value in literal_strings(node.args[0]):
                normalized = literal_value.removeprefix("./")
                if normalized in files:
                    edges.add(normalized)
                    dynamic.append(f"{path}:{name}:{normalized}")
    return edges, dynamic


def text_edges(path: str, files: set[str]) -> set[str]:
    try:
        text = (ROOT / path).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return set()
    candidates = re.findall(
        r"(?:\.kilo|config|configs|scripts|src|tests)/[A-Za-z0-9_./ ()-]+",
        text,
    )
    return {
        candidate.rstrip(".,:;`'\")]")
        for candidate in candidates
        if candidate.rstrip(".,:;`'\")]") in files
    }


def executable_inventory(files: set[str]) -> tuple[list[str], list[str]]:
    stage = subprocess.run(
        ["git", "ls-files", "--stage", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    ).stdout
    executable: list[str] = []
    for record in stage.split(b"\0"):
        if not record:
            continue
        metadata, path = record.decode("utf-8").split("\t", 1)
        if metadata.startswith("100755 "):
            executable.append(path)
    shebangs: list[str] = []
    for path in files:
        target = ROOT / path
        if target.is_file():
            try:
                if target.open("rb").read(2) == b"#!":
                    shebangs.append(path)
            except OSError:
                continue
    return sorted(executable), sorted(shebangs)


def configured_roots(
    files: set[str], categories: dict[str, str]
) -> tuple[set[str], dict[str, Any]]:
    roots = {
        "config/pipeline_manifest.json",
        "pyproject.toml",
        "scripts/validate_production_surface.py",
    }
    evidence: dict[str, Any] = {}
    manifest = json.loads(
        (ROOT / "config/pipeline_manifest.json").read_text(encoding="utf-8")
    )
    wrappers = sorted(
        step["wrapper"]
        for step in manifest["steps"]
        if step.get("execution_mode") == "script" and step.get("wrapper")
    )
    roots.update(wrappers)
    evidence["manifest_wrappers"] = wrappers
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    scripts = project.get("project", {}).get("scripts", {})
    script_targets: dict[str, str | None] = {}
    for name, target in scripts.items():
        module = str(target).split(":", 1)[0]
        resolved = module_path(module, files)
        script_targets[name] = resolved
        if resolved:
            roots.add(resolved)
    evidence["project_scripts"] = script_targets
    package_exports = sorted(
        path
        for path in files
        if path.startswith("src/bet/") and path.endswith("/__init__.py")
    )
    database_bootstrap = sorted(
        path
        for path in files
        if path.startswith("src/bet/db/")
        and (path.endswith(".sql") or Path(path).name in {"connection.py", "schema.py"})
    )
    engineering_validators = sorted(
        path
        for path in files
        if path.startswith("scripts/")
        and categories.get(path) == "ACTIVE_ENGINEERING_TOOL"
        and Path(path).name.startswith(("audit_", "validate_", "validate-", "verify_"))
    )
    configuration = sorted(
        path
        for path, category in categories.items()
        if category == "ACTIVE_CONFIGURATION"
    )
    tests = sorted(
        path
        for path, category in categories.items()
        if category in {"ACTIVE_TEST", "ACTIVE_FIXTURE"}
    )
    executable, shebangs = executable_inventory(files)
    roots.update(package_exports)
    roots.update(database_bootstrap)
    roots.update(engineering_validators)
    roots.update(configuration)
    roots.update(tests)
    evidence["package_init_exports"] = package_exports
    evidence["database_bootstrap_and_migrations"] = database_bootstrap
    evidence["engineering_validators"] = engineering_validators
    evidence["configuration_authorities"] = configuration
    evidence["test_and_fixture_roots"] = tests
    evidence["tracked_executables"] = executable
    evidence["shebang_inventory"] = shebangs
    agents = sorted(
        path
        for path in files
        if path.startswith(".kilo/agents/") and Path(path).stem in PRODUCTION_AGENTS
    )
    skills = sorted(
        path
        for path in files
        if path.startswith(".kilo/skills/")
        and len(Path(path).parts) > 2
        and Path(path).parts[2] in PRODUCTION_SKILLS
    )
    roots.update(agents)
    roots.update(skills)
    evidence["production_agents"] = agents
    evidence["production_skills"] = skills
    return roots, evidence


def build() -> tuple[dict[str, Any], dict[str, Any]]:
    tracked = tracked_files()
    files = set(tracked)
    categories = {path: classify(path) for path in tracked}
    roots, evidence = configured_roots(files, categories)
    graph: dict[str, list[str]] = {}
    dynamic: list[str] = []
    for path in tracked:
        if Path(path).suffix != ".py":
            continue
        edges, discovered = python_edges(path, files)
        graph[path] = sorted(edges)
        dynamic.extend(discovered)
    text_graph = {
        path: sorted(edges)
        for path in tracked
        if Path(path).suffix in {".json", ".md", ".toml", ".yaml", ".yml"}
        and (edges := text_edges(path, files))
    }

    def transitive_closure(selected_roots: set[str]) -> set[str]:
        reachable = set(selected_roots)
        queue = deque(sorted(selected_roots))
        while queue:
            current = queue.popleft()
            for target in [*graph.get(current, []), *text_graph.get(current, [])]:
                if target not in reachable:
                    reachable.add(target)
                    queue.append(target)
        return reachable

    retention_roots = set(roots)
    runtime_roots = retention_roots - set(evidence["test_and_fixture_roots"])
    runtime_roots -= set(evidence["engineering_validators"])
    reachable = transitive_closure(retention_roots)
    runtime_reachable = transitive_closure(runtime_roots)
    escapes = sorted(
        f"{source}->{target}"
        for source in reachable
        for target in [*graph.get(source, []), *text_graph.get(source, [])]
        if categories.get(target)
        in {"GENERATED_TRACKED_ERROR", "LEGACY_UNREACHABLE", "UNKNOWN"}
    )
    root_classification_violations = sorted(
        path
        for path in roots
        if categories.get(path)
        in {"GENERATED_TRACKED_ERROR", "LEGACY_UNREACHABLE", "UNKNOWN"}
    )
    runtime_escapes = sorted(
        f"{source}->{target}"
        for source in runtime_reachable
        for target in [*graph.get(source, []), *text_graph.get(source, [])]
        if categories.get(target)
        in {"GENERATED_TRACKED_ERROR", "LEGACY_UNREACHABLE", "UNKNOWN"}
    )
    migration_paths = sorted(
        path
        for path in tracked
        if path.startswith("src/bet/db/migrations/") and path.endswith(".sql")
    )
    classification = {
        "schema_version": 1,
        "tracked_file_count": len(tracked),
        "files": categories,
        "counts": {
            category: list(categories.values()).count(category)
            for category in sorted(set(categories.values()))
        },
        "unknown_files": sorted(
            path for path, category in categories.items() if category == "UNKNOWN"
        ),
    }
    graph_output = {
        "schema_version": 1,
        "roots": sorted(roots),
        "runtime_roots": sorted(runtime_roots),
        "root_evidence": evidence,
        "python_edges": graph,
        "textual_path_edges": text_graph,
        "literal_dynamic_references": sorted(dynamic),
        "reachable_files": sorted(reachable),
        "runtime_reachable_files": sorted(runtime_reachable),
        "reachable_classification_escapes": escapes,
        "runtime_classification_escapes": runtime_escapes,
        "root_classification_violations": root_classification_violations,
        "migration_order": migration_paths,
        "unknown_files": classification["unknown_files"],
    }
    return graph_output, classification


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--graph", type=Path)
    parser.add_argument("--classification", type=Path)
    args = parser.parse_args()
    graph, classification = build()
    for path, value in ((args.graph, graph), (args.classification, classification)):
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
    summary = {
        "status": "PASS" if not classification["unknown_files"] else "FAIL",
        "tracked_file_count": classification["tracked_file_count"],
        "counts": classification["counts"],
        "unknown_files": classification["unknown_files"],
        "reachable_classification_escapes": graph["reachable_classification_escapes"],
        "root_classification_violations": graph["root_classification_violations"],
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
