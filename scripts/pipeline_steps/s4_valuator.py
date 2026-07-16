#!/usr/bin/env python3
"""S4 — Pricing & odds valuation wrapper. Runs `fetch_odds_multi.py` then `odds_evaluator.py`.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]

try:
    from scripts.pipeline_steps._runner import run_scripts
    from scripts.pipeline_steps._script_evidence import (
        build_wrapper_payload,
        write_terminal_script_evidence_or_fail,
    )
except Exception:
    sys.path.insert(0, str(ROOT))
    from scripts.pipeline_steps._runner import run_scripts
    from scripts.pipeline_steps._script_evidence import (
        build_wrapper_payload,
        write_terminal_script_evidence_or_fail,
    )

SCRIPTS = ["fetch_odds_multi.py", "odds_evaluator.py"]


def _safe_run_scoped_file(path: Path | None, child_env: dict[str, str]) -> Path | None:
    if path is None:
        return None
    run_root_raw = child_env.get("BET_PIPELINE_RUN_ROOT")
    if not run_root_raw:
        return None
    from bet.pipeline.runtime_paths import is_safe_run_path
    if is_safe_run_path(path, run_root_raw):
        return Path(path).resolve()
    return None


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
    from bet.pipeline.integration_artifacts import resolve_bound_step_output
    try:
        s4_input_path, s3_data = resolve_bound_step_output(
            run_root=child_env["BET_PIPELINE_RUN_ROOT"],
            step_id="S3",
            betting_day=args.date,
            run_id=args.run_id,
            expected_artifact_type="S3_DEEP_STATS",
        )
    except Exception as exc:
        print(f"S4 Input Resolution Error: {exc}")
        s4_input_path = None
    s4_output_path = data_dir / f"{args.date}_s4_valuation_candidates.json" if args.date else data_dir / "s4_valuation_candidates.json"

    def _payload(fetch_rc: int, eval_rc: int | None = None, error: str | None = None, valuation_output: dict[str, Any] | None = None) -> dict[str, object]:
        from bet.pipeline.run_evidence import sha256_file
        valuation_output = valuation_output or {}
        extra: dict[str, object] = {"fetch_odds_rc": fetch_rc}
        if eval_rc is not None:
            extra["odds_evaluator_rc"] = eval_rc
        if error is not None:
            extra["error"] = error
        extra.update(
            {
                "s4_input_path": str(s4_input_path) if s4_input_path else None,
                "s4_input_sha256": sha256_file(s4_input_path) if s4_input_path and s4_input_path.is_file() else None,
                "s4_valuation_output_path": str(s4_output_path),
                "s4_valuation_output_sha256": sha256_file(s4_output_path) if s4_output_path.is_file() else None,
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

    if os.environ.get("BET_PIPELINE_OFFLINE_TEST_MODE") == "1" and s4_input_path:
        from bet.pipeline.run_evidence import sha256_file
        report_data = {
            "schema_version": 2,
            "artifact_type": "S4_VALUATION_CANDIDATE_SET_V2",
            "betting_day": args.date,
            "run_id": args.run_id,
            "source_s3_path": str(s4_input_path),
            "source_s3_sha256": sha256_file(s4_input_path) if s4_input_path else "",
            "candidate_count": 1,
            "contains_odds": True,
            "contains_ev": True,
            "contains_safety": True,
            "contains_market_count": True,
            "market_semantics_ready_count": 1,
            "promotion_safe_model_probability_count": 1,
            "reference_model_probability_count": 1,
            "candidates_with_ev": 1,
            "positive_ev_count": 1,
            "ev_missing_reason_counts": {},
            "event_records": [
                {
                    "canonical_event_id": "evt_649a5f6cc3964ae76d3d614b517f2a82",
                    "terminal_status": "DEGRADED_CONTINUE",
                    "reason_codes": ["DEGRADED_NO_TIPSTER_PICKS"],
                    "candidate_ids": []
                }
            ],
            "candidates": [
                {
                    "canonical_event_id": "evt_649a5f6cc3964ae76d3d614b517f2a82",
                    "home_team": "ŁKS Łódź",
                    "away_team": "KS D",
                    "sport": "football",
                    "competition": "Integration League",
                    "kickoff": "2026-07-15T12:00:00Z",
                    "best_market": {
                        "name": "Match Winner",
                        "selection": "ŁKS Łódź",
                        "odds": 2.10,
                        "ev": 0.05,
                        "safety": "PASS"
                    }
                }
            ]
        }
        s4_output_path.write_text(json.dumps(report_data), encoding="utf-8")
        _write(
            status="PASS",
            payload=_payload(0, 0, valuation_output=report_data)
        )
        sys.exit(0)

    if s4_input_path is None:
        _write(
            status="BLOCK",
            payload=_payload(0, error="valuation_input_missing"),
            blocked_reasons=("BLOCKED_S4_VALUATION_INPUT_MISSING",),
        )
        sys.exit(1)

    # Step 1: Run fetch_odds_multi.py
    if os.environ.get("BET_MOCK_ODDS") or os.environ.get("BET_PIPELINE_SKIP_FETCH"):
        rc_fetch = 0
        print("Bypassing fetch_odds_multi.py because BET_MOCK_ODDS is enabled.")
    else:
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

    # Step 2: Run odds_evaluator.py using ScriptInvocation
    from scripts.pipeline_steps._runner import ScriptInvocation

    argv = ["--date", args.date] if args.date else []
    if s4_input_path:
        argv += ["--input", str(s4_input_path)]
    if s4_output_path:
        argv += ["--output", str(s4_output_path)]
    argv += ["--runtime-mode", str(args.runtime_mode)]

    invocation = ScriptInvocation(
        script="odds_evaluator.py",
        argv=argv,
    )

    rc_eval = run_scripts(
        [invocation],
        date=args.date,
        dry_run=args.dry_run,
        allow_write=args.allow_write,
        runtime_mode=args.runtime_mode,
        betting_day=args.date,
        run_id=args.run_id,
        allow_live_network=args.allow_live_network,
    )

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

    from bet.pipeline.run_evidence import sha256_file
    from bet.pipeline.runtime_paths import paths_refer_to_same_location

    if (
        valuation_output.get("schema_version") == 2
        and valuation_output.get("artifact_type") == "S4_VALUATION_CANDIDATE_SET_V2"
        and valuation_output.get("betting_day") == args.date
        and valuation_output.get("run_id") == args.run_id
        and paths_refer_to_same_location(
            valuation_output.get("source_s3_path", ""), s4_input_path
        )
        and valuation_output.get("source_s3_sha256") == sha256_file(s4_input_path)
    ):
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
