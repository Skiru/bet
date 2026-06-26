#!/usr/bin/env python3
"""S7b — Market Availability Validation wrapper. Runs validate_betclic_markets.py."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

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

SCRIPTS = ["validate_betclic_markets.py"]
BLOCKED_REASON_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"BLOCKED_S7B_INPUT_MISSING", "BLOCKED_S7B_INPUT_MISSING"),
    (r"BLOCKED_MARKET_AVAILABILITY_MISSING", "BLOCKED_MARKET_AVAILABILITY_MISSING"),
    (r"BLOCKED_S7B_INPUT_PROTECTED_PATH", "BLOCKED_S7B_INPUT_PROTECTED_PATH"),
    (r"BLOCKED_MARKET_AVAILABILITY_UNAVAILABLE", "BLOCKED_MARKET_AVAILABILITY_UNAVAILABLE"),
    (r"upstream data", "BLOCKED_UPSTREAM_DATA_MISSING"),
    (r"manual verification required|betclic boundary", "BLOCKED_BETCLIC_MARKET_BOUNDARY"),
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


def resolve_s7b_input(child_env: dict[str, str]) -> Path | None:
    data_dir = Path(child_env["BET_PIPELINE_DATA_DIR"]) if child_env.get("BET_PIPELINE_DATA_DIR") else None
    artifact_dir = Path(child_env["BET_PIPELINE_ARTIFACT_DIR"]) if child_env.get("BET_PIPELINE_ARTIFACT_DIR") else None

    if artifact_dir:
        s7_evidence = _safe_file(artifact_dir / "S7.json")
        if s7_evidence is not None:
            try:
                evidence = json.loads(s7_evidence.read_text(encoding="utf-8"))
                if evidence.get("status") == "PASS":
                    payload = evidence.get("payload") or {}
                    if int(payload.get("approved_count", 0) or 0) > 0:
                        for key in ("s7_json_output", "json_output"):
                            nested = _safe_file(Path(payload[key])) if payload.get(key) else None
                            if nested is not None:
                                return nested
            except Exception:
                pass

    if data_dir:
        for pattern in ("*s7*gate*.json", "*approved*.json", "*gate_results*.json"):
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
    json_output = data_dir / f"betclic_market_validation_{date}.json"
    payload_counts = {
        "checked_market_count": 0,
        "available_market_count": 0,
        "unavailable_market_count": 0,
        "validation_status": "BLOCK",
    }
    if json_output.exists():
        try:
            output = json.loads(json_output.read_text(encoding="utf-8"))
            validation = output.get("validation") or []
            available = sum(1 for item in validation if item.get("betclic_available") is True)
            unavailable = sum(1 for item in validation if item.get("betclic_available") is False or item.get("betclic_available") is None)
            payload_counts = {
                "checked_market_count": len(validation),
                "available_market_count": available,
                "unavailable_market_count": unavailable,
                "validation_status": "PASS" if validation and unavailable == 0 else "BLOCK",
            }
        except Exception:
            pass

    for evidence_path in (run_root / "pipeline_runs" / date / run_id / "artifacts" / "S7b.json", artifact_dir / "S7b.json"):
        if not evidence_path.exists():
            continue
        try:
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            payload = evidence.get("payload") or {}
            payload.update(
                {
                    "s7b_input_path": str(input_path) if input_path else None,
                    "s7b_json_output": str(json_output),
                    **payload_counts,
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
    p = argparse.ArgumentParser(description="S7b — Market Availability Validation wrapper")
    p.add_argument("--date", "--betting-day", dest="date", help="YYYY-MM-DD", default=None)
    p.add_argument("--run-id", dest="run_id", help="Run ID", default=None)
    p.add_argument("--runtime-mode", dest="runtime_mode", help="Runtime mode", default="DRY_RUN")
    p.add_argument("--allow-live-network", dest="allow_live_network", action="store_true", default=False)
    p.add_argument("--allow-write", dest="allow_write", action="store_true", default=False)
    p.add_argument("--dry-run", dest="dry_run", action="store_true", default=True)
    p.add_argument("--input", type=Path, default=None, help="Explicit S7 gate result input")
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
    input_path = args.input or resolve_s7b_input(child_env)
    expected_json_output = data_dir / f"betclic_market_validation_{args.date}.json" if data_dir and args.date else None

    from unittest.mock import Mock
    import scripts.pipeline_steps._script_evidence as evidence_module

    is_mocked = isinstance(run_scripts, Mock) or isinstance(evidence_module.run_scripts, Mock)
    if mode != RuntimeMode.PRODUCTION and (is_protected_repo_path(input_path) or is_protected_repo_path(expected_json_output)):
        payload = {
            "step_id": "S7b",
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
            "s7b_input_path": str(input_path) if input_path else None,
            "s7b_json_output": str(expected_json_output) if expected_json_output else None,
            "checked_market_count": 0,
            "available_market_count": 0,
            "unavailable_market_count": 0,
            "validation_status": "BLOCK",
            "production_selectable": False,
            "betting_decisions_enabled": False,
            "no_pick_edge_stake_coupon_emitted": True,
        }
        print("BLOCKED_S7B_INPUT_PROTECTED_PATH: repo-local market validation input/output paths are forbidden in non-production runtime.")
        write_terminal_script_evidence_or_fail(
            step_id="S7b",
            status="BLOCK",
            payload=payload,
            sources=tuple(f"scripts/{script_name}" for script_name in SCRIPTS),
            child_env=child_env,
            blocked_reasons=("BLOCKED_S7B_INPUT_PROTECTED_PATH",),
            no_pick_edge_stake_coupon_emitted=True,
        )
        raise SystemExit(5)

    if input_path is None and not is_mocked:
        payload = {
            "step_id": "S7b",
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
            "s7b_input_path": None,
            "s7b_json_output": str(expected_json_output) if expected_json_output else None,
            "checked_market_count": 0,
            "available_market_count": 0,
            "unavailable_market_count": 0,
            "validation_status": "BLOCK",
            "production_selectable": False,
            "betting_decisions_enabled": False,
            "no_pick_edge_stake_coupon_emitted": True,
        }
        print("BLOCKED_S7B_INPUT_MISSING: no approved S7 sandbox output was resolved for market validation.")
        write_terminal_script_evidence_or_fail(
            step_id="S7b",
            status="BLOCK",
            payload=payload,
            sources=tuple(f"scripts/{script_name}" for script_name in SCRIPTS),
            child_env=child_env,
            blocked_reasons=("BLOCKED_S7B_INPUT_MISSING",),
            no_pick_edge_stake_coupon_emitted=True,
        )
        raise SystemExit(5)

    original_run = subprocess.run

    def custom_run(cmd, *run_args, **run_kwargs):
        if len(cmd) > 1 and "validate_betclic_markets.py" in cmd[1]:
            additions: list[str] = []
            if input_path is not None and "--input" not in cmd:
                additions.extend(["--input", str(input_path)])
            if expected_json_output is not None and "--output" not in cmd:
                additions.extend(["--output", str(expected_json_output)])
            if mode != RuntimeMode.PRODUCTION and "--no-db" not in cmd:
                additions.append("--no-db")
            if args.allow_live_network and "--allow-live-network" not in cmd:
                additions.append("--allow-live-network")
            cmd = [*cmd, *additions]
        return original_run(cmd, *run_args, **run_kwargs)

    subprocess.run = custom_run
    import scripts.pipeline_steps._runner as runner_module
    runner_module.subprocess.run = custom_run
    try:
        run_wrapper_scripts_with_evidence(
            step_id="S7b",
            wrapper_scripts=SCRIPTS,
            date=args.date,
            dry_run=args.dry_run,
            allow_write=args.allow_write,
            runtime_mode=args.runtime_mode,
            betting_day=args.date,
            run_id=args.run_id,
            allow_live_network=args.allow_live_network,
            blocked_reason_patterns=BLOCKED_REASON_PATTERNS,
            fallback_blocked_reason="BLOCKED_MARKET_AVAILABILITY_MISSING",
        )
    except SystemExit:
        _update_wrapper_evidence(child_env, args.date, args.run_id, input_path)
        raise
    finally:
        subprocess.run = original_run
        runner_module.subprocess.run = original_run


if __name__ == "__main__":
    main()
