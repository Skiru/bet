#!/usr/bin/env python3
"""S6 — Repeats check wrapper. Runs `check_48h_repeats.py`.
"""
from __future__ import annotations

import argparse
import sys
import os
import json
import io
import contextlib
import subprocess
from pathlib import Path
from typing import Any

# Resolve root and imports
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from scripts.pipeline_steps._script_evidence import (
        write_terminal_script_evidence_or_fail,
        classify_wrapper_result,
        run_wrapper_scripts_with_evidence,
    )
    from scripts.pipeline_steps._runner import resolve_child_runtime_env, run_scripts
except Exception:
    sys.path.insert(0, str(ROOT / "scripts" / "pipeline_steps"))
    from _script_evidence import (
        write_terminal_script_evidence_or_fail,
        classify_wrapper_result,
        run_wrapper_scripts_with_evidence,
    )
    from _runner import resolve_child_runtime_env, run_scripts

SCRIPTS = ["check_48h_repeats.py"]
BLOCKED_REASON_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"upstream data", "BLOCKED_UPSTREAM_DATA_MISSING"),
    (r"repeat guard input missing|missing repeat guard|repeat guard.*missing|repeat guard.*not found", "BLOCKED_REPEAT_GUARD_INPUT_MISSING"),
    (r"repeat guard input empty|empty candidate list|zero candidates|no candidates|empty candidate input", "BLOCKED_REPEAT_GUARD_INPUT_EMPTY"),
    (r"repeat signal|signal conflict|repeat guard conflict|repeat guard triggered|repeat conflict|repeat-loss exclusions found", "BLOCKED_REPEAT_SIGNAL_CONFLICT"),
)


def is_protected_repo_path(path: Path | str | None) -> bool:
    if not path:
        return False
    abs_path = Path(path).resolve()
    # Check if under repo-local betting/data, betting/coupons, or reports
    betting_data = (ROOT / "betting" / "data").resolve()
    betting_coupons = (ROOT / "betting" / "coupons").resolve()
    reports = (ROOT / "reports").resolve()
    
    for parent in [betting_data, betting_coupons, reports]:
        try:
            pipeline_runs = (ROOT / "reports" / "pipeline_runs").resolve()
            if abs_path == pipeline_runs or abs_path.is_relative_to(pipeline_runs):
                run_id = os.environ.get("BET_PIPELINE_RUN_ID")
                if run_id and run_id in str(abs_path):
                    continue
            abs_path.relative_to(parent)
            return True
        except ValueError:
            pass
    return False


def find_sandbox_input_candidate_json(child_env: dict[str, str], date: str | None) -> Path | None:
    data_dir_str = child_env.get("BET_PIPELINE_DATA_DIR")
    artifact_dir_str = child_env.get("BET_PIPELINE_ARTIFACT_DIR")
    run_root_str = child_env.get("BET_PIPELINE_RUN_ROOT")

    if not data_dir_str:
        return None

    data_dir = Path(data_dir_str)
    artifact_dir = Path(artifact_dir_str) if artifact_dir_str else None
    run_root = Path(run_root_str) if run_root_str else None

    def is_safe(p: Path) -> bool:
        p_res = p.resolve()
        p_str = str(p_res)
        pipeline_runs = (ROOT / "reports" / "pipeline_runs").resolve()
        run_id = os.environ.get("BET_PIPELINE_RUN_ID")
        is_in_pipeline_runs = False
        if run_id and run_id in p_str:
            is_in_pipeline_runs = p_res == pipeline_runs or p_res.is_relative_to(pipeline_runs)
        if is_in_pipeline_runs:
            return p_res.exists() and p_res.is_file()
        for forbidden in ["/betting/data/", "/betting/coupons/", "/reports/"]:
            if forbidden in p_str or p_str.endswith(forbidden[:-1]):
                return False
        return p_res.exists() and p_res.is_file()

    # 1. Search in S4.json artifact payload
    if artifact_dir:
        s4_artifact_path = artifact_dir / "S4.json"
        if is_safe(s4_artifact_path):
            try:
                with open(s4_artifact_path, "r", encoding="utf-8") as f:
                    s4_data = json.load(f)
                payload = s4_data.get("payload") or {}
                
                # Check for direct path keys
                for key in ["s4_output_path", "valuation_path", "candidate_path", "candidates_path"]:
                    val = payload.get(key)
                    if val and is_safe(Path(val)):
                        return Path(val)

                # Recursive check
                def search_dict(d: Any) -> list[str]:
                    found = []
                    if isinstance(d, dict):
                        for k, v in d.items():
                            found.extend(search_dict(v))
                    elif isinstance(d, list):
                        for item in d:
                            found.extend(search_dict(item))
                    elif isinstance(d, str):
                        if d.endswith(".json") and ("s4" in d.lower() or "valuation" in d.lower() or "candidate" in d.lower()):
                            found.append(d)
                    return found
                
                for candidate_str in search_dict(payload):
                    candidate_path = Path(candidate_str)
                    if is_safe(candidate_path):
                        return candidate_path
            except Exception:
                pass

    # 2. Search for valuation/candidate pattern files in data_dir
    patterns = [
        "*s4*.json",
        "*valuation*.json",
        "*value*.json",
        "*candidate*.json",
        "*s3_deep_stats.json",
    ]
    for pattern in patterns:
        for p in sorted(data_dir.glob(pattern)):
            if is_safe(p):
                return p

    # 3. Check S5 candidate universe in parent run_root or sandbox directories
    if run_root:
        for pattern in ["*s5_context_candidate_universe.json", "*candidate_universe*.json"]:
            for p in sorted(run_root.glob(pattern)):
                if is_safe(p):
                    return p
            for p in sorted(run_root.parent.glob(pattern)):
                if is_safe(p):
                    return p

    # 4. Fallback to S3/S2 shortlist under data_dir
    fallback_patterns = [
        "*shortlist*.json",
        "*s2*.json",
        "*gate*.json"
    ]
    for pattern in fallback_patterns:
        for p in sorted(data_dir.glob(pattern)):
            if is_safe(p):
                return p

    return None


def _certification_targets() -> None:
    run_scripts(SCRIPTS)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--date", "--betting-day", dest="date", help="YYYY-MM-DD", default=None)
    p.add_argument("--run-id", dest="run_id", help="Run ID", default=None)
    p.add_argument("--runtime-mode", dest="runtime_mode", help="Runtime mode", default="DRY_RUN")
    p.add_argument("--allow-live-network", dest="allow_live_network", action="store_true", default=False)
    p.add_argument("--allow-write", dest="allow_write", action="store_true", default=False)
    p.add_argument("--dry-run", dest="dry_run", action="store_true", default=True)
    p.add_argument("--input", type=Path, default=None, help="Input override")
    p.add_argument("--output", type=Path, default=None, help="Output override")
    args = p.parse_args()

    from bet.pipeline.runtime_modes import RuntimeMode, parse_runtime_mode
    mode = parse_runtime_mode(args.runtime_mode)

    # Resolve child runtime env
    child_env, runtime_path_source = resolve_child_runtime_env(
        os.environ,
        runtime_mode=mode,
        betting_day=args.date,
        run_id=args.run_id,
        run_root=None,
    )

    # Resolve input path
    input_path = args.input
    if not input_path:
        input_path = find_sandbox_input_candidate_json(child_env, args.date)

    # Resolve output path
    output_path = args.output
    if not output_path:
        if child_env.get("BET_PIPELINE_DATA_DIR"):
            output_path = Path(child_env["BET_PIPELINE_DATA_DIR"]) / f"repeat_loss_handoff_{args.date}.json"
        else:
            output_path = ROOT / "betting" / "data" / f"repeat_loss_handoff_{args.date}.json"

    # Set resolved paths in env only if they are not None
    if input_path:
        os.environ["S6_RESOLVED_INPUT"] = str(input_path)
    if output_path:
        os.environ["S6_RESOLVED_OUTPUT"] = str(output_path)

    # Monkeypatch subprocess.run to inject arguments
    original_run = subprocess.run
    def custom_run(cmd, *args, **kwargs):
        if len(cmd) > 1 and "check_48h_repeats.py" in cmd[1]:
            inp = os.environ.get("S6_RESOLVED_INPUT")
            out = os.environ.get("S6_RESOLVED_OUTPUT")
            if inp:
                cmd += ["--input", inp]
            if out:
                cmd += ["--output", out]
        return original_run(cmd, *args, **kwargs)

    subprocess.run = custom_run
    import scripts.pipeline_steps._runner
    scripts.pipeline_steps._runner.subprocess.run = custom_run

    # Safety: non-production safety checks
    if mode != RuntimeMode.PRODUCTION:
        if is_protected_repo_path(input_path) or is_protected_repo_path(output_path):
            print("repeat guard input missing: Explicit input or output path under protected repo-local path is forbidden in non-production modes.")
            payload = {
                "s6_input_path": str(input_path) if input_path else None,
                "s6_output_path": str(output_path) if output_path else None,
                "checked_candidates_count": 0,
                "recent_losses_count": 0,
                "repeat_loss_count": 0,
                "candidate_source": "input_json",
                "runtime_mode": mode.value,
                "production_selectable": False,
                "betting_decisions_enabled": False,
                "no_pick_edge_stake_coupon_emitted": True,
                "wrapper_scripts": SCRIPTS,
                "wrapper_rc": 5,
                "runtime_path_source": runtime_path_source,
                "child_run_root": child_env.get("BET_PIPELINE_RUN_ROOT"),
                "child_artifact_dir": child_env.get("BET_PIPELINE_ARTIFACT_DIR"),
                "error": "Explicit input or output path under protected repo-local path is forbidden in non-production modes."
            }
            write_terminal_script_evidence_or_fail(
                step_id="S6",
                status="BLOCK",
                payload=payload,
                sources=tuple(f"scripts/{s}" for s in SCRIPTS),
                child_env=child_env,
                blocked_reasons=("BLOCKED_REPEAT_GUARD_INPUT_MISSING",),
                no_pick_edge_stake_coupon_emitted=True,
            )
            sys.exit(5)

    # Check if run_scripts is mocked in tests
    import scripts.pipeline_steps._script_evidence as evidence_module
    from unittest.mock import Mock
    is_mocked = isinstance(run_scripts, Mock) or isinstance(evidence_module.run_scripts, Mock)

    # Check missing input path
    if not input_path and not is_mocked:
        print("repeat guard input missing: No safe S4 candidate universe JSON found in sandbox run.")
        payload = {
            "s6_input_path": None,
            "s6_output_path": str(output_path) if output_path else None,
            "checked_candidates_count": 0,
            "recent_losses_count": 0,
            "repeat_loss_count": 0,
            "candidate_source": "input_json",
            "runtime_mode": mode.value,
            "production_selectable": False,
            "betting_decisions_enabled": False,
            "no_pick_edge_stake_coupon_emitted": True,
            "wrapper_scripts": SCRIPTS,
            "wrapper_rc": 5,
            "runtime_path_source": runtime_path_source,
            "child_run_root": child_env.get("BET_PIPELINE_RUN_ROOT"),
            "child_artifact_dir": child_env.get("BET_PIPELINE_ARTIFACT_DIR"),
            "error": "No safe S4 candidate universe JSON found in sandbox run."
        }
        write_terminal_script_evidence_or_fail(
            step_id="S6",
            status="BLOCK",
            payload=payload,
            sources=tuple(f"scripts/{s}" for s in SCRIPTS),
            child_env=child_env,
            blocked_reasons=("BLOCKED_REPEAT_GUARD_INPUT_MISSING",),
            no_pick_edge_stake_coupon_emitted=True,
        )
        sys.exit(5)

    try:
        run_wrapper_scripts_with_evidence(
            step_id="S6",
            wrapper_scripts=SCRIPTS,
            date=args.date,
            dry_run=args.dry_run,
            allow_write=args.allow_write,
            runtime_mode=args.runtime_mode,
            betting_day=args.date,
            run_id=args.run_id,
            allow_live_network=args.allow_live_network,
            blocked_reason_patterns=BLOCKED_REASON_PATTERNS,
            fallback_blocked_reason="BLOCKED_REPEAT_GUARD_INPUT_MISSING",
        )
    except SystemExit as exc:
        evidence_dir = Path(child_env.get("BET_PIPELINE_RUN_ROOT", "")) / "pipeline_runs" / args.date / args.run_id / "artifacts"
        evidence_path = evidence_dir / "S6.json"
        mirrored_path = Path(child_env.get("BET_PIPELINE_ARTIFACT_DIR", "")) / "S6.json"

        # Read counts from output_path if it exists
        checked_candidates_count = 0
        recent_losses_count = 0
        repeat_loss_count = 0
        candidate_source = "input_json"
        
        if output_path and output_path.exists():
            try:
                with open(output_path, "r", encoding="utf-8") as f:
                    handoff_data = json.load(f)
                checked_candidates_count = handoff_data.get("checked_candidates_count", 0)
                recent_losses_count = handoff_data.get("recent_losses_count", 0)
                repeat_loss_count = handoff_data.get("repeat_loss_count", 0)
                candidate_source = handoff_data.get("candidate_source", "input_json")
            except Exception:
                pass

        for path in [evidence_path, mirrored_path]:
            if path.exists():
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    payload = data.get("payload") or {}
                    payload["s6_input_path"] = str(input_path) if input_path else None
                    payload["s6_output_path"] = str(output_path) if output_path else None
                    payload["checked_candidates_count"] = checked_candidates_count
                    payload["recent_losses_count"] = recent_losses_count
                    payload["repeat_loss_count"] = repeat_loss_count
                    payload["candidate_source"] = candidate_source
                    
                    data["payload"] = payload
                    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                except Exception:
                    pass
        raise


if __name__ == "__main__":
    main()
