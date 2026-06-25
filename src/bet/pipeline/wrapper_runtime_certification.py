"""Runtime certification for manifest-declared pipeline wrappers.

This module performs static certification of wrapper safety for a future
manifest-driven orchestrator without executing live provider code.
"""
from __future__ import annotations

import ast
import py_compile
from pathlib import Path
from typing import Any

from bet.pipeline.artifact_gate import required_artifacts_before_step
from bet.pipeline.manifest import load_pipeline_manifest


SCHEMA_VERSION = 1
VERIFIER_ID = "pipeline_wrapper_runtime_certification_a"
WRITE_ACK_VALUE = "I_UNDERSTAND_PRODUCTION_WRITE"
LIVE_ONLY_TARGETS = {
    "scripts/discover_events.py",
    "scripts/fetch_odds_multi.py",
    "scripts/settle_on_finish.py",
    "scripts/tipster_aggregator.py",
    "scripts/validate_betclic_markets.py",
}
WRITE_SURFACE_PATTERNS = (
    "atomic_json_write(",
    ".write_text(",
    "json.dump(",
    "write_csv(",
    "save_to_db(",
    "save_odds(",
    "upsert(",
    "find_or_create(",
)
PATH_SURFACE_PATTERNS = (
    "betting/data",
    "betting/coupons",
    '"betting" / "data"',
    '"betting" / "coupons"',
    "data_dir =",
    "coupon_dir =",
)


def _compile_python_file(path: Path) -> tuple[bool, str]:
    try:
        py_compile.compile(str(path), doraise=True)
        return True, ""
    except py_compile.PyCompileError as exc:
        return False, str(exc)
    except Exception as exc:  # pragma: no cover - defensive fallback
        return False, f"Unexpected compilation error: {exc}"


def _literal_string_list(node: ast.AST | None, scope: dict[str, list[str]]) -> list[str] | None:
    if node is None:
        return None
    if isinstance(node, ast.Name):
        return list(scope.get(node.id, [])) if node.id in scope else None
    if isinstance(node, (ast.List, ast.Tuple)):
        values: list[str] = []
        for elt in node.elts:
            if not isinstance(elt, ast.Constant) or not isinstance(elt.value, str):
                return None
            values.append(elt.value)
        return values
    return None


def _record_assignment(stmt: ast.stmt, scope: dict[str, list[str]]) -> None:
    value: ast.AST | None = None
    targets: list[ast.expr] = []
    if isinstance(stmt, ast.Assign):
        value = stmt.value
        targets = list(stmt.targets)
    elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
        value = stmt.value
        targets = [stmt.target]
    if value is None:
        return
    resolved = _literal_string_list(value, scope)
    if resolved is None:
        return
    for target in targets:
        if isinstance(target, ast.Name):
            scope[target.id] = resolved


def _extract_run_scripts_from_call(call: ast.Call, scope: dict[str, list[str]]) -> list[str]:
    func = call.func
    is_run_scripts = (
        isinstance(func, ast.Name) and func.id == "run_scripts"
    ) or (
        isinstance(func, ast.Attribute) and func.attr == "run_scripts"
    )
    if not is_run_scripts:
        return []

    candidate: ast.AST | None = call.args[0] if call.args else None
    if candidate is None:
        for keyword in call.keywords:
            if keyword.arg == "scripts":
                candidate = keyword.value
                break
    discovered = _literal_string_list(candidate, scope) or []
    return [f"scripts/{name}" for name in discovered]


def _discover_in_statements(statements: list[ast.stmt], initial_scope: dict[str, list[str]]) -> list[str]:
    scope = dict(initial_scope)
    discovered: list[str] = []

    def visit_node(node: ast.AST) -> None:
        if isinstance(node, ast.Call):
            discovered.extend(_extract_run_scripts_from_call(node, scope))
        for child in ast.iter_child_nodes(node):
            if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
                visit_node(child)

    for stmt in statements:
        _record_assignment(stmt, scope)
        visit_node(stmt)
    return discovered


def discover_wrapper_targets(wrapper_path: Path) -> list[str]:
    """Discover real target scripts from wrapper source by parsing run_scripts calls."""
    source = Path(wrapper_path).read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(wrapper_path))

    module_scope: dict[str, list[str]] = {}
    discovered: list[str] = []
    for stmt in tree.body:
        _record_assignment(stmt, module_scope)
        if isinstance(stmt, ast.FunctionDef):
            discovered.extend(_discover_in_statements(stmt.body, module_scope))
        else:
            discovered.extend(_discover_in_statements([stmt], module_scope))

    ordered: list[str] = []
    seen: set[str] = set()
    for target in discovered:
        if target not in seen:
            ordered.append(target)
            seen.add(target)
    return ordered


def _wrapper_accepts_date_cli(source: str) -> bool:
    return "--date" in source or "--betting-day" in source


def _wrapper_dry_run_default(source: str) -> bool:
    return '"--dry-run"' in source and "default=True" in source


def _wrapper_allows_partial(source: str) -> bool:
    return "continue_on_codes=[0, 1]" in source or "continue_on_codes=(0, 1)" in source


def _target_source(repo_root: Path, target: str) -> str:
    return (repo_root / target).read_text(encoding="utf-8")


def _target_has_machine_readable_evidence(source: str) -> str:
    if "AGENT_SUMMARY" in source:
        return "AGENT_SUMMARY"
    lowered = source.lower()
    if any(token in lowered for token in WRITE_SURFACE_PATTERNS) and "json" in lowered:
        return "JSON"
    return "MISSING"


def _target_writes_forbidden_paths(source: str) -> bool:
    lowered = source.lower()
    touches_forbidden_path = any(pattern in lowered for pattern in PATH_SURFACE_PATTERNS)
    write_surface = any(pattern in lowered for pattern in WRITE_SURFACE_PATTERNS)
    return touches_forbidden_path and write_surface


def _target_may_write_production_db(source: str) -> bool:
    lowered = source.lower()
    return any(
        token in lowered
        for token in (
            "save_to_db(",
            "save_odds(",
            "upsert(",
            "find_or_create(",
            "insert into ",
            "update ",
        )
    )


def _runner_contracts(repo_root: Path) -> dict[str, bool]:
    runner_source = (repo_root / "scripts/pipeline_steps/_runner.py").read_text(encoding="utf-8")
    return {
        "write_ack_guard": WRITE_ACK_VALUE in runner_source and "BLOCKED_WRITE_ACK_MISSING" in runner_source,
        "force_allow_guard": "BLOCKED_FORCE_ALLOW_WRITE_UNSAFE" in runner_source,
        "deterministic_subprocess": "cmd = [python, str(script_path)]" in runner_source and "subprocess.run(cmd" in runner_source,
        "exit_code_propagation": "return res.returncode" in runner_source and "return res2.returncode" in runner_source,
    }


def classify_wrapper_runtime_status(
    *,
    targets: list[str],
    wrapper_compiles: bool,
    targets_exist: bool,
    targets_compile: bool,
    dry_run_default: bool,
    write_safe: bool,
    date_cli_compatible: bool,
    partial_exit_allowed: bool,
    evidence_contract: str,
    live_only: bool,
    step_id: str,
) -> str:
    """Classify wrapper runtime safety for orchestrator use."""
    if not targets:
        return "BLOCK"
    if not wrapper_compiles or not targets_exist or not targets_compile:
        return "BLOCK"
    if not dry_run_default or not write_safe or not date_cli_compatible:
        return "BLOCK"
    if partial_exit_allowed and step_id != "S1":
        return "BLOCK"
    if live_only or evidence_contract == "BLOCKED_FOR_ORCHESTRATOR":
        return "BLOCK"
    if evidence_contract == "MISSING":
        return "WARN"
    return "PASS"


def certify_wrapper(step_id: str, wrapper_path: Path, repo_root: Path) -> dict[str, Any]:
    """Certify one manifest wrapper and its discovered target scripts."""
    repo_root = Path(repo_root)
    wrapper_path = Path(wrapper_path)
    manifest = load_pipeline_manifest(repo_root / "config/pipeline_manifest.json")
    manifest_wrappers = {
        step.id: step.wrapper for step in manifest.steps if step.execution_mode == "script" and step.id
    }
    manifest_wrapper = manifest_wrappers.get(step_id)
    wrapper_exists = wrapper_path.exists()
    wrapper_compiles, wrapper_compile_error = _compile_python_file(wrapper_path)
    wrapper_source = wrapper_path.read_text(encoding="utf-8") if wrapper_exists else ""
    targets = discover_wrapper_targets(wrapper_path) if wrapper_exists else []

    target_results: list[tuple[str, bool, bool, str]] = []
    evidence_contract = "MISSING"
    live_only = False
    writes_forbidden_paths = False
    writes_production_db = False
    for target in targets:
        target_path = repo_root / target
        exists = target_path.exists()
        compiles, compile_error = _compile_python_file(target_path) if exists else (False, "missing target")
        target_results.append((target, exists, compiles, compile_error))
        if exists:
            source = _target_source(repo_root, target)
            if target in LIVE_ONLY_TARGETS:
                live_only = True
            writes_forbidden_paths = writes_forbidden_paths or _target_writes_forbidden_paths(source)
            writes_production_db = writes_production_db or _target_may_write_production_db(source)
            target_evidence = _target_has_machine_readable_evidence(source)
            if target_evidence == "AGENT_SUMMARY":
                evidence_contract = "AGENT_SUMMARY"
            elif target_evidence == "JSON" and evidence_contract == "MISSING":
                evidence_contract = "JSON"

    artifact_dependencies = required_artifacts_before_step(step_id)
    if step_id == "S8" and artifact_dependencies != ("S7", "S7b"):
        evidence_contract = "BLOCKED_FOR_ORCHESTRATOR"

    runner_contracts = _runner_contracts(repo_root)
    targets_exist = bool(targets) and all(item[1] for item in target_results)
    targets_compile = bool(targets) and all(item[2] for item in target_results)
    dry_run_default = _wrapper_dry_run_default(wrapper_source)
    date_cli_compatible = _wrapper_accepts_date_cli(wrapper_source)
    partial_exit_allowed = _wrapper_allows_partial(wrapper_source)
    write_safe = (
        runner_contracts["write_ack_guard"]
        and runner_contracts["force_allow_guard"]
        and dry_run_default
        and not writes_forbidden_paths
        and not writes_production_db
    )
    verdict = classify_wrapper_runtime_status(
        targets=targets,
        wrapper_compiles=wrapper_compiles,
        targets_exist=targets_exist,
        targets_compile=targets_compile,
        dry_run_default=dry_run_default,
        write_safe=write_safe,
        date_cli_compatible=date_cli_compatible,
        partial_exit_allowed=partial_exit_allowed,
        evidence_contract=evidence_contract,
        live_only=live_only,
        step_id=step_id,
    )

    warnings: list[str] = []
    failed_requirements: list[str] = []
    if not wrapper_exists:
        failed_requirements.append(f"{step_id}: wrapper missing at {wrapper_path}")
    if manifest_wrapper != str(wrapper_path.relative_to(repo_root)):
        failed_requirements.append(f"{step_id}: manifest wrapper mismatch ({manifest_wrapper!r})")
    if not wrapper_compiles:
        failed_requirements.append(f"{step_id}: wrapper failed to compile ({wrapper_compile_error})")
    if not targets:
        failed_requirements.append(f"{step_id}: no run_scripts targets discovered from wrapper source")
    for target, exists, compiles, compile_error in target_results:
        if not exists:
            failed_requirements.append(f"{step_id}: target missing ({target})")
        elif not compiles:
            failed_requirements.append(f"{step_id}: target failed to compile ({target}: {compile_error})")
    if partial_exit_allowed and step_id != "S1":
        failed_requirements.append(f"{step_id}: partial exit continuation is only allowed for S1")
    if live_only:
        failed_requirements.append(f"{step_id}: wrapper has live-only targets without deterministic offline mode")
    if writes_forbidden_paths:
        failed_requirements.append(f"{step_id}: discovered targets write under betting/data or betting/coupons")
    if writes_production_db:
        failed_requirements.append(f"{step_id}: discovered targets may write production DB state")
    if not runner_contracts["write_ack_guard"]:
        failed_requirements.append(f"{step_id}: _runner missing allow-write acknowledgement guard")
    if not runner_contracts["force_allow_guard"]:
        failed_requirements.append(f"{step_id}: _runner allows FORCE_ALLOW_WRITE without explicit acknowledgement")
    if not runner_contracts["deterministic_subprocess"]:
        failed_requirements.append(f"{step_id}: _runner subprocess construction is not deterministic")
    if not runner_contracts["exit_code_propagation"]:
        failed_requirements.append(f"{step_id}: _runner does not propagate non-zero exit codes")
    if not date_cli_compatible:
        failed_requirements.append(f"{step_id}: wrapper does not accept --date/--betting-day and declares no explicit no-date behavior")
    if not dry_run_default:
        failed_requirements.append(f"{step_id}: wrapper is not dry-run by default")
    if evidence_contract == "MISSING":
        warnings.append(f"{step_id}: no machine-readable evidence contract detected in discovered targets")
    if evidence_contract == "BLOCKED_FOR_ORCHESTRATOR":
        failed_requirements.append(f"{step_id}: S8 missing declared S7/S7b artifact gate dependencies")

    return {
        "wrapper": str(wrapper_path.relative_to(repo_root)) if wrapper_exists else str(wrapper_path),
        "targets": targets,
        "wrapper_exists": wrapper_exists,
        "manifest_mapped": manifest_wrapper == str(wrapper_path.relative_to(repo_root)) if wrapper_exists else False,
        "wrapper_compiles": wrapper_compiles,
        "targets_exist": targets_exist,
        "targets_compile": targets_compile,
        "dry_run_default": dry_run_default,
        "write_safe": write_safe,
        "date_cli_compatible": date_cli_compatible,
        "partial_exit_allowed": partial_exit_allowed,
        "evidence_contract": evidence_contract,
        "verdict": verdict,
        "failed_requirements": failed_requirements,
        "warnings": warnings,
        "artifact_dependencies": list(artifact_dependencies),
        "deterministic_subprocess": runner_contracts["deterministic_subprocess"],
        "exit_code_propagation": runner_contracts["exit_code_propagation"],
    }


def certify_manifest_wrappers(repo_root: Path) -> dict[str, Any]:
    """Certify all manifest-declared script wrappers."""
    repo_root = Path(repo_root)
    manifest = load_pipeline_manifest(repo_root / "config/pipeline_manifest.json")
    wrappers: dict[str, dict[str, Any]] = {}
    failed_requirements: list[str] = []
    warnings: list[str] = []

    for step in manifest.steps:
        if step.execution_mode != "script" or not step.id or not step.wrapper:
            continue
        wrapper_result = certify_wrapper(step.id, repo_root / step.wrapper, repo_root)
        wrappers[step.id] = wrapper_result
        failed_requirements.extend(wrapper_result["failed_requirements"])
        warnings.extend(wrapper_result["warnings"])

    verdict = "PASS" if all(item["verdict"] == "PASS" for item in wrappers.values()) else "BLOCK"
    return {
        "schema_version": SCHEMA_VERSION,
        "verifier_id": VERIFIER_ID,
        "verdict": verdict,
        "wrappers": wrappers,
        "failed_requirements": failed_requirements,
        "warnings": warnings,
    }
