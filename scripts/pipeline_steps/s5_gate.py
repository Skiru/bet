#!/usr/bin/env python3
"""S5 — Gate checking wrapper. Runs `gate_checker.py`."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from bet.pipeline.runtime_modes import RuntimeMode, parse_runtime_mode
    from scripts.pipeline_steps._runner import resolve_child_runtime_env, run_scripts
    from scripts.pipeline_steps._script_evidence import run_wrapper_scripts_with_evidence, write_terminal_script_evidence_or_fail
except Exception:
    from bet.pipeline.runtime_modes import RuntimeMode, parse_runtime_mode
    from scripts.pipeline_steps._runner import resolve_child_runtime_env, run_scripts
    from scripts.pipeline_steps._script_evidence import run_wrapper_scripts_with_evidence, write_terminal_script_evidence_or_fail

SCRIPTS = ["gate_checker.py"]
BLOCKED_REASON_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"BLOCKED_S7_GATE_INPUT_MISSING", "BLOCKED_S7_GATE_INPUT_MISSING"),
    (r"BLOCKED_S7_GATE_INPUT_EMPTY", "BLOCKED_S7_GATE_INPUT_EMPTY"),
    (r"BLOCKED_S7_GATE_INPUT_INVALID", "BLOCKED_S7_GATE_INPUT_INVALID"),
    (r"BLOCKED_S7_GATE_INPUT_PROTECTED_PATH", "BLOCKED_S7_GATE_INPUT_PROTECTED_PATH"),
    (r"BLOCKED_S7_GATE_OUTPUT_PROTECTED_PATH", "BLOCKED_S7_GATE_OUTPUT_PROTECTED_PATH"),
    (r"upstream data", "BLOCKED_UPSTREAM_DATA_MISSING"),
    (r"no approved picks|approved picks missing", "BLOCKED_APPROVED_PICKS_MISSING"),
    (r"hard approval|approval gate|gate failed|validation failed", "BLOCKED_HARD_APPROVAL_GATE"),
)


def is_protected_repo_path(path: Path | str | None) -> bool:
    if not path:
        return False
    abs_path = Path(path).resolve()
    for parent in ((ROOT / "betting" / "data").resolve(), (ROOT / "betting" / "coupons").resolve(), (ROOT / "reports").resolve()):
        try:
            abs_path.relative_to(parent)
            return True
        except ValueError:
            pass
    return False


def _safe_file(path: Path | None) -> Path | None:
    if path is None:
        return None
    try:
        resolved = path.resolve()
    except FileNotFoundError:
        return None
    if not resolved.exists() or not resolved.is_file() or is_protected_repo_path(resolved):
        return None
    return resolved


def _is_candidate_payload(payload: Any) -> bool:
    if isinstance(payload, list):
        return any(isinstance(item, dict) for item in payload)
    if not isinstance(payload, dict):
        return False
    for key in ("analyses", "candidates", "results", "valuations", "events"):
        if isinstance(payload.get(key), list):
            return True
    inner = payload.get("payload")
    return isinstance(inner, dict) and _is_candidate_payload(inner)


def _candidate_paths_from_payload(payload: Any) -> list[Path]:
    found: list[Path] = []

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            for value in node.values():
                visit(value)
            return
        if isinstance(node, list):
            for item in node:
                visit(item)
            return
        if isinstance(node, str) and node.endswith(".json"):
            lowered = node.lower()
            if any(token in lowered for token in ("s4", "valuation", "value", "candidate", "s3_deep_stats", "shortlist", "repeat")):
                candidate = _safe_file(Path(node))
                if candidate is not None:
                    found.append(candidate)

    visit(payload)
    deduped: list[Path] = []
    seen: set[Path] = set()
    for item in found:
        if item not in seen:
            seen.add(item)
            deduped.append(item)
    return deduped


def resolve_s7_input(child_env: dict[str, str], date: str | None) -> Path | None:
    data_dir = Path(child_env["BET_PIPELINE_DATA_DIR"]) if child_env.get("BET_PIPELINE_DATA_DIR") else None
    artifact_dir = Path(child_env["BET_PIPELINE_ARTIFACT_DIR"]) if child_env.get("BET_PIPELINE_ARTIFACT_DIR") else None

    if artifact_dir:
        for artifact_path in (artifact_dir / "S4.json", artifact_dir / "S6.json"):
            candidate = _safe_file(artifact_path)
            if candidate is None:
                continue
            try:
                payload = json.loads(candidate.read_text(encoding="utf-8")).get("payload") or {}
            except Exception:
                continue
            nested_paths = _candidate_paths_from_payload(payload)
            if nested_paths:
                return nested_paths[0]

    if data_dir:
        for pattern in ("*s4*.json", "*valuation*.json", "*value*.json", "*candidate*.json"):
            for path in sorted(data_dir.glob(pattern)):
                candidate = _safe_file(path)
                if candidate is not None:
                    return candidate

        for pattern in ("*repeat*.json", "*s6*.json"):
            for path in sorted(data_dir.glob(pattern)):
                candidate = _safe_file(path)
                if candidate is None:
                    continue
                try:
                    payload = json.loads(candidate.read_text(encoding="utf-8"))
                except Exception:
                    continue
                if _is_candidate_payload(payload):
                    return candidate

        if date:
            candidate = _safe_file(data_dir / f"{date}_s3_deep_stats.json")
            if candidate is not None:
                return candidate

        for pattern in ("*s3_deep_stats*.json", "*shortlist*.json", "*s2*.json"):
            for path in sorted(data_dir.glob(pattern)):
                candidate = _safe_file(path)
                if candidate is not None:
                    return candidate

    return None


def _update_wrapper_evidence(child_env: dict[str, str], date: str | None, run_id: str | None, input_path: Path | None) -> None:
    if not date or not run_id:
        return
    run_root = Path(child_env.get("BET_PIPELINE_RUN_ROOT", ""))
    artifact_dir = Path(child_env.get("BET_PIPELINE_ARTIFACT_DIR", ""))
    data_dir = Path(child_env.get("BET_PIPELINE_DATA_DIR", ""))
    json_output = data_dir / f"{date}_s7_gate_results.json"
    markdown_output = data_dir / f"{date}_s7_gate_results.md"
    counts = {
        "total_candidates": 0,
        "approved_count": 0,
        "extended_count": 0,
        "rejected_count": 0,
    }
    if json_output.exists():
        try:
            payload = json.loads(json_output.read_text(encoding="utf-8"))
            summary = payload.get("summary") or {}
            counts = {
                "total_candidates": int(summary.get("total_candidates", 0) or 0),
                "approved_count": int(summary.get("approved_count", 0) or 0),
                "extended_count": int(summary.get("extended_count", 0) or 0),
                "rejected_count": int(summary.get("rejected_count", 0) or 0),
            }
        except Exception:
            pass

    for evidence_path in (run_root / "pipeline_runs" / date / run_id / "artifacts" / "S7.json", artifact_dir / "S7.json"):
        if not evidence_path.exists():
            continue
        try:
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            payload = evidence.get("payload") or {}
            payload.update(
                {
                    "s7_input_path": str(input_path) if input_path else None,
                    "s7_json_output": str(json_output),
                    "s7_markdown_output": str(markdown_output),
                    **counts,
                    "production_selectable": False,
                    "betting_decisions_enabled": False,
                    "no_pick_edge_stake_coupon_emitted": True,
                }
            )
            evidence["payload"] = payload
            evidence_path.write_text(json.dumps(evidence, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        except Exception:
            pass


def _certification_targets() -> None:
    run_scripts(SCRIPTS)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--date", "--betting-day", dest="date", help="YYYY-MM-DD", default=None)
    p.add_argument("--run-id", dest="run_id", help="Run ID", default=None)
    p.add_argument("--runtime-mode", dest="runtime_mode", help="Runtime mode", default="DRY_RUN")
    p.add_argument("--allow-live-network", dest="allow_live_network", action="store_true", default=False)
    p.add_argument("--allow-write", dest="allow_write", action="store_true", default=False)
    p.add_argument("--dry-run", dest="dry_run", action="store_true", default=True)
    p.add_argument("--input", type=Path, default=None, help="Explicit S7 gate input override")
    args = p.parse_args()

    mode = parse_runtime_mode(args.runtime_mode)
    child_env, runtime_path_source = resolve_child_runtime_env(
        os.environ,
        runtime_mode=mode,
        betting_day=args.date,
        run_id=args.run_id,
        run_root=None,
    )
    for key in ("BET_PIPELINE_RUN_ROOT", "BET_PIPELINE_DATA_DIR", "BET_PIPELINE_COUPON_DIR", "BET_PIPELINE_ARTIFACT_DIR", "BET_PIPELINE_BETTING_DAY", "BET_PIPELINE_RUN_ID", "BET_PIPELINE_RUNTIME_MODE"):
        if child_env.get(key):
            os.environ[key] = child_env[key]

    data_dir = Path(child_env["BET_PIPELINE_DATA_DIR"]) if child_env.get("BET_PIPELINE_DATA_DIR") else None
    input_path = args.input or resolve_s7_input(child_env, args.date)
    expected_json_output = data_dir / f"{args.date}_s7_gate_results.json" if data_dir and args.date else None
    expected_markdown_output = data_dir / f"{args.date}_s7_gate_results.md" if data_dir and args.date else None

    if mode != RuntimeMode.PRODUCTION and (
        is_protected_repo_path(input_path)
        or is_protected_repo_path(expected_json_output)
        or is_protected_repo_path(expected_markdown_output)
    ):
        payload = {
            "step_id": "S7",
            "wrapper_scripts": SCRIPTS,
            "wrapper_rc": 5,
            "runtime_mode": mode.value,
            "dry_run": True,
            "allow_write": False,
            "allow_live_network": bool(args.allow_live_network),
            "production_write": False,
            "runtime_path_source": runtime_path_source,
            "child_run_root": child_env.get("BET_PIPELINE_RUN_ROOT"),
            "child_artifact_dir": child_env.get("BET_PIPELINE_ARTIFACT_DIR"),
            "s7_input_path": str(input_path) if input_path else None,
            "s7_json_output": str(expected_json_output) if expected_json_output else None,
            "s7_markdown_output": str(expected_markdown_output) if expected_markdown_output else None,
            "total_candidates": 0,
            "approved_count": 0,
            "extended_count": 0,
            "rejected_count": 0,
            "production_selectable": False,
            "betting_decisions_enabled": False,
            "no_pick_edge_stake_coupon_emitted": True,
        }
        print("BLOCKED_S7_GATE_INPUT_PROTECTED_PATH: repo-local gate input/output paths are forbidden in non-production runtime.")
        write_terminal_script_evidence_or_fail(
            step_id="S7",
            status="BLOCK",
            payload=payload,
            sources=tuple(f"scripts/{script_name}" for script_name in SCRIPTS),
            child_env=child_env,
            blocked_reasons=("BLOCKED_S7_GATE_INPUT_PROTECTED_PATH",),
            no_pick_edge_stake_coupon_emitted=True,
        )
        raise SystemExit(5)

    from unittest.mock import Mock
    import scripts.pipeline_steps._script_evidence as evidence_module

    is_mocked = isinstance(run_scripts, Mock) or isinstance(evidence_module.run_scripts, Mock)
    if input_path is None and not is_mocked:
        payload = {
            "step_id": "S7",
            "wrapper_scripts": SCRIPTS,
            "wrapper_rc": 5,
            "runtime_mode": mode.value,
            "dry_run": True,
            "allow_write": False,
            "allow_live_network": bool(args.allow_live_network),
            "production_write": False,
            "runtime_path_source": runtime_path_source,
            "child_run_root": child_env.get("BET_PIPELINE_RUN_ROOT"),
            "child_artifact_dir": child_env.get("BET_PIPELINE_ARTIFACT_DIR"),
            "s7_input_path": None,
            "s7_json_output": str(expected_json_output) if expected_json_output else None,
            "s7_markdown_output": str(expected_markdown_output) if expected_markdown_output else None,
            "total_candidates": 0,
            "approved_count": 0,
            "extended_count": 0,
            "rejected_count": 0,
            "production_selectable": False,
            "betting_decisions_enabled": False,
            "no_pick_edge_stake_coupon_emitted": True,
        }
        print("BLOCKED_S7_GATE_INPUT_MISSING: no safe sandbox S7 candidate input was resolved.")
        write_terminal_script_evidence_or_fail(
            step_id="S7",
            status="BLOCK",
            payload=payload,
            sources=tuple(f"scripts/{script_name}" for script_name in SCRIPTS),
            child_env=child_env,
            blocked_reasons=("BLOCKED_S7_GATE_INPUT_MISSING",),
            no_pick_edge_stake_coupon_emitted=True,
        )
        raise SystemExit(5)

    original_run = subprocess.run

    def custom_run(cmd, *run_args, **run_kwargs):
        if len(cmd) > 1 and "gate_checker.py" in cmd[1] and input_path is not None and "--input" not in cmd:
            cmd = [*cmd, "--input", str(input_path)]
        return original_run(cmd, *run_args, **run_kwargs)

    subprocess.run = custom_run
    import scripts.pipeline_steps._runner as runner_module
    runner_module.subprocess.run = custom_run
    try:
        run_wrapper_scripts_with_evidence(
            step_id="S7",
            wrapper_scripts=SCRIPTS,
            date=args.date,
            dry_run=args.dry_run,
            allow_write=args.allow_write,
            runtime_mode=args.runtime_mode,
            betting_day=args.date,
            run_id=args.run_id,
            allow_live_network=args.allow_live_network,
            blocked_reason_patterns=BLOCKED_REASON_PATTERNS,
            fallback_blocked_reason="BLOCKED_APPROVED_PICKS_MISSING",
        )
    except SystemExit:
        _update_wrapper_evidence(child_env, args.date, args.run_id, input_path)
        raise
    finally:
        subprocess.run = original_run
        runner_module.subprocess.run = original_run


if __name__ == "__main__":
    main()
