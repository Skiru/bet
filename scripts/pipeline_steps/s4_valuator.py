#!/usr/bin/env python3
"""S4 — Pricing & odds valuation wrapper. Runs `fetch_odds_multi.py` then `odds_evaluator.py`.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]

try:
    from scripts.pipeline_steps._script_evidence import build_wrapper_payload, write_terminal_script_evidence_or_fail
    from scripts.pipeline_steps._runner import run_scripts
except Exception:
    sys.path.insert(0, str(ROOT))
    from scripts.pipeline_steps._script_evidence import build_wrapper_payload, write_terminal_script_evidence_or_fail
    from scripts.pipeline_steps._runner import run_scripts

SCRIPTS = ["fetch_odds_multi.py", "odds_evaluator.py"]


def is_protected_repo_path(path: Path | str | None) -> bool:
    if not path:
        return False
    abs_path = Path(path).resolve()
    for parent in ((ROOT / "betting" / "data").resolve(), (ROOT / "betting" / "coupons").resolve(), (ROOT / "reports").resolve()):
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


def _safe_run_scoped_file(path: Path | None, child_env: dict[str, str]) -> Path | None:
    resolved = _safe_file(path)
    if resolved is None:
        return None
    resolved_str = str(resolved)
    pipeline_runs = (ROOT / "reports" / "pipeline_runs").resolve()
    run_id = os.environ.get("BET_PIPELINE_RUN_ID")
    is_in_pipeline_runs = False
    if run_id and run_id in resolved_str:
        is_in_pipeline_runs = resolved.is_relative_to(pipeline_runs)
    if not (resolved_str.startswith("/tmp/") or resolved_str.startswith("/private/tmp/") or is_in_pipeline_runs):
        return None
    run_root_raw = child_env.get("BET_PIPELINE_RUN_ROOT")
    if not run_root_raw:
        return resolved
    try:
        resolved.relative_to(Path(run_root_raw).resolve())
    except ValueError:
        return None
    return resolved


def _load_json(path: Path) -> Any | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _extract_candidate_entries(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("analyses", "candidates", "results", "valuations", "events"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    inner = payload.get("payload")
    if isinstance(inner, dict):
        return _extract_candidate_entries(inner)
    return []


def _resolve_s4_input_path(child_env: dict[str, str], date: str | None) -> Path | None:
    data_dir = Path(child_env["BET_PIPELINE_DATA_DIR"]) if child_env.get("BET_PIPELINE_DATA_DIR") else None
    if data_dir is None or not date:
        return None
    preferred = (
        data_dir / f"{date}_s3_deep_stats.json",
        data_dir / f"{date}_s2_shortlist.json",
    )
    for path in preferred:
        candidate = _safe_run_scoped_file(path, child_env)
        if candidate is None:
            continue
        payload = _load_json(candidate)
        if _extract_candidate_entries(payload):
            return candidate
    return None


def _odds_snapshot_paths(child_env: dict[str, str]) -> list[str]:
    data_dir = Path(child_env["BET_PIPELINE_DATA_DIR"]) if child_env.get("BET_PIPELINE_DATA_DIR") else None
    if data_dir is None:
        return []
    snapshots: list[str] = []
    for name in ("odds_api_snapshot.json", "odds_api_io_snapshot.json", "odds_multi_sources.json"):
        path = _safe_run_scoped_file(data_dir / name, child_env)
        if path is not None:
            snapshots.append(str(path))
    return snapshots


def _read_valuation_output(path: Path) -> dict[str, Any] | None:
    payload = _load_json(path)
    return payload if isinstance(payload, dict) else None


def main() -> None:
    p = argparse.ArgumentParser(description="S4 Valuator wrapper")
    p.add_argument("--date", "--betting-day", dest="date", help="YYYY-MM-DD", default=None)
    p.add_argument("--run-id", dest="run_id", help="Run ID", default=None)
    p.add_argument("--runtime-mode", dest="runtime_mode", help="Runtime mode", default="DRY_RUN")
    p.add_argument("--allow-live-network", dest="allow_live_network", action="store_true", default=False)
    p.add_argument("--allow-write", dest="allow_write", action="store_true", default=False)
    p.add_argument("--dry-run", dest="dry_run", action="store_true", default=True)
    args = p.parse_args()

    from scripts.pipeline_steps._runner import resolve_child_runtime_env

    child_env, runtime_path_source = resolve_child_runtime_env(
        os.environ,
        runtime_mode=args.runtime_mode,
        betting_day=args.date,
        run_id=args.run_id,
        run_root=None,
    )
    data_dir = Path(child_env.get("BET_PIPELINE_DATA_DIR", str(ROOT / "betting" / "data")))
    s4_input_path = _resolve_s4_input_path(child_env, args.date)
    s4_output_path = data_dir / f"{args.date}_s4_valuation_candidates.json" if args.date else data_dir / "s4_valuation_candidates.json"

    def _payload(fetch_rc: int, eval_rc: int | None = None, error: str | None = None, valuation_output: dict[str, Any] | None = None) -> dict[str, object]:
        valuation_output = valuation_output or {}
        extra: dict[str, object] = {"fetch_odds_rc": fetch_rc}
        if eval_rc is not None:
            extra["odds_evaluator_rc"] = eval_rc
        if error is not None:
            extra["error"] = error
        extra.update(
            {
                "s4_input_path": str(s4_input_path) if s4_input_path else None,
                "s4_valuation_output_path": str(s4_output_path),
                "s4_candidate_count": valuation_output.get("candidate_count"),
                "s4_contains_odds": bool(valuation_output.get("contains_odds", False)),
                "s4_contains_ev": bool(valuation_output.get("contains_ev", False)),
                "s4_contains_safety": bool(valuation_output.get("contains_safety", False)),
                "s4_contains_market_count": bool(valuation_output.get("contains_market_count", False)),
                "s4_market_semantics_ready_count": valuation_output.get("market_semantics_ready_count"),
                "s4_promotion_safe_model_probability_count": valuation_output.get("promotion_safe_model_probability_count"),
                "s4_reference_model_probability_count": valuation_output.get("reference_model_probability_count"),
                "s4_candidates_with_ev": valuation_output.get("candidates_with_ev"),
                "s4_positive_ev_count": valuation_output.get("positive_ev_count"),
                "s4_ev_missing_reason_counts": valuation_output.get("ev_missing_reason_counts"),
                "odds_snapshot_paths": _odds_snapshot_paths(child_env),
            }
        )
        return build_wrapper_payload(
            step_id="S4",
            wrapper_scripts=SCRIPTS,
            wrapper_rc=eval_rc if eval_rc is not None else fetch_rc,
            runtime_mode=args.runtime_mode,
            dry_run=args.dry_run,
            allow_write=args.allow_write,
            allow_live_network=args.allow_live_network,
            child_env=child_env,
            runtime_path_source=runtime_path_source,
            extra=extra,
        )

    def _write(status: str, payload: dict[str, object], blocked_reasons: tuple[str, ...] = ()) -> None:
        write_terminal_script_evidence_or_fail(
            step_id="S4",
            status=status,
            payload=payload,
            sources=tuple(f"scripts/{script_name}" for script_name in SCRIPTS),
            child_env=child_env,
            blocked_reasons=blocked_reasons,
            no_pick_edge_stake_coupon_emitted=True,
        )

    if s4_input_path is None:
        _write(
            status="BLOCK",
            payload=_payload(0, error="valuation_input_missing"),
            blocked_reasons=("BLOCKED_S4_VALUATION_INPUT_MISSING",),
        )
        sys.exit(1)

    # Step 1: Run fetch_odds_multi.py
    rc_fetch = run_scripts(
        ["fetch_odds_multi.py"],
        date=None,
        dry_run=args.dry_run,
        allow_write=args.allow_write,
        runtime_mode=args.runtime_mode,
        betting_day=args.date,
        run_id=args.run_id,
        allow_live_network=args.allow_live_network,
    )

    if rc_fetch not in (0, 1):
        _write(
            status="FAILED",
            payload=_payload(rc_fetch, error=f"fetch_failed_unexpectedly_with_code_{rc_fetch}"),
            blocked_reasons=("FAILED_UNEXPECTED_SUBPROCESS_ERROR",),
        )
        sys.exit(rc_fetch)

    # Step 2: Run odds_evaluator.py
    original_run = subprocess.run

    def custom_run(cmd, *run_args, **run_kwargs):
        if len(cmd) > 1 and "odds_evaluator.py" in cmd[1]:
            injected = list(cmd)
            if "--input" not in injected:
                injected.extend(["--input", str(s4_input_path)])
            if "--output" not in injected:
                injected.extend(["--output", str(s4_output_path)])
            if "--runtime-mode" not in injected:
                injected.extend(["--runtime-mode", str(args.runtime_mode)])
            cmd = injected
        return original_run(cmd, *run_args, **run_kwargs)

    subprocess.run = custom_run
    import scripts.pipeline_steps._runner as runner_module
    runner_module.subprocess.run = custom_run
    try:
        rc_eval = run_scripts(
            ["odds_evaluator.py"],
            date=args.date,
            dry_run=args.dry_run,
            allow_write=args.allow_write,
            runtime_mode=args.runtime_mode,
            betting_day=args.date,
            run_id=args.run_id,
            allow_live_network=args.allow_live_network,
        )
    finally:
        subprocess.run = original_run
        runner_module.subprocess.run = original_run

    if rc_eval != 0:
        if rc_eval == 1:
            _write(
                status="BLOCK",
                payload=_payload(0, rc_eval, "evaluator_failed_no_candidates"),
                blocked_reasons=("BLOCKED_UPSTREAM_DATA_MISSING",),
            )
            sys.exit(rc_eval)
        else:
            _write(
                status="FAILED",
                payload=_payload(0, rc_eval, f"evaluator_failed_unexpectedly_with_code_{rc_eval}"),
                blocked_reasons=("FAILED_UNEXPECTED_SUBPROCESS_ERROR",),
            )
            sys.exit(rc_eval)

    valuation_output = _read_valuation_output(s4_output_path)
    if valuation_output is None:
        _write(
            status="BLOCK",
            payload=_payload(rc_fetch, rc_eval, "valuation_output_missing"),
            blocked_reasons=("BLOCKED_S4_VALUATION_OUTPUT_MISSING",),
        )
        sys.exit(1)

    if int(valuation_output.get("candidate_count", 0) or 0) <= 0:
        _write(
            status="BLOCK",
            payload=_payload(rc_fetch, rc_eval, "valuation_output_empty", valuation_output),
            blocked_reasons=("BLOCKED_S4_VALUATION_OUTPUT_EMPTY",),
        )
        sys.exit(1)

    if valuation_output.get("artifact_type") == "S4_VALUATION_CANDIDATES":
        _write(
            status="PASS",
            payload=_payload(rc_fetch, rc_eval, valuation_output=valuation_output),
        )
        sys.exit(0)

    _write(
        status="BLOCK",
        payload=_payload(rc_fetch, rc_eval, "valuation_output_invalid", valuation_output),
        blocked_reasons=("BLOCKED_S4_VALUATION_OUTPUT_MISSING",),
    )
    sys.exit(1)


if __name__ == "__main__":
    main()
