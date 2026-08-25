#!/usr/bin/env python3
"""S7 — pure, source-bound hard approval gate.

The historical filename is retained because it is the manifest entrypoint.
The implementation consumes only the canonical S6 output and never invokes a
second decision script or reconstructs candidates from earlier stages.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bet.pipeline.artifact_io import publish_run_artifact
from bet.pipeline.hard_approval_gate import evaluate_s7_hard_gate
from bet.pipeline.integration_artifacts import resolve_manifest_step_output
from bet.pipeline.manifest import load_pipeline_manifest
from bet.pipeline.run_evidence import sha256_file
from bet.pipeline.runtime_modes import RuntimeMode, parse_runtime_mode
from bet.pipeline.runtime_paths import is_safe_run_path
from scripts.pipeline_steps._runner import resolve_child_runtime_env
from scripts.pipeline_steps._script_evidence import write_terminal_script_evidence_or_fail


SCRIPTS: list[str] = []


def _load_json(path: Path) -> Any | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _extract_candidate_entries(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    inner = payload.get("payload")
    if isinstance(inner, dict):
        nested = _extract_candidate_entries(inner)
        if nested:
            return nested
    for key in ("analyses", "candidates", "results", "valuations", "events", "accepted"):
        values = payload.get(key)
        if isinstance(values, list):
            return [
                item.get("original_candidate", item)
                for item in values
                if isinstance(item, dict)
            ]
    return []


def _inspect_input_path(path: Path | None) -> dict[str, bool]:
    entries = _extract_candidate_entries(_load_json(path)) if path else []
    return {
        "contains_odds": any(
            (isinstance(item.get("odds"), dict) and bool(item["odds"]))
            or item.get("best_odds") is not None
            or item.get("odds_decimal") is not None
            for item in entries
        ),
        "contains_ev": any(item.get("ev") is not None for item in entries),
        "contains_safety": any(
            item.get("safety_score") is not None or bool(item.get("risk_flags"))
            for item in entries
        ),
        "contains_market_count": any(
            any(key in item for key in ("market_count", "markets_evaluated", "total_markets_available"))
            for item in entries
        ),
        "is_candidate_universe": bool(entries),
    }


def _build_input_resolution(
    path: Path | None,
    *,
    source_step: str,
    source_kind: str,
    blocked_reason: str | None = None,
) -> dict[str, Any]:
    return {
        "path": path,
        "source_step": source_step,
        "source_kind": source_kind,
        "blocked_reason": blocked_reason,
        **_inspect_input_path(path),
    }


def _input_payload_fields(resolution: dict[str, Any] | None) -> dict[str, Any]:
    resolution = resolution or {}
    path = resolution.get("path")
    return {
        "s7_input_path": str(path) if path else None,
        "s7_input_sha256": sha256_file(path) if isinstance(path, Path) and path.is_file() else None,
        "s7_input_source_step": resolution.get("source_step", "UNKNOWN"),
        "s7_input_source_kind": resolution.get("source_kind", "unknown"),
        "s7_input_contains_odds": bool(resolution.get("contains_odds")),
        "s7_input_contains_ev": bool(resolution.get("contains_ev")),
        "s7_input_contains_safety": bool(resolution.get("contains_safety")),
        "s7_input_contains_market_count": bool(resolution.get("contains_market_count")),
    }


def _resolve_s6_input(
    child_env: dict[str, str], date: str | None, run_id: str | None
) -> dict[str, Any]:
    try:
        path, data = resolve_manifest_step_output(
            manifest=load_pipeline_manifest(ROOT / "config" / "pipeline_manifest.json"),
            run_root=child_env["BET_PIPELINE_RUN_ROOT"],
            step_id="S6",
            betting_day=str(date),
            run_id=str(run_id),
            expected_artifact_type="S6_PORTFOLIO_REPEAT_GUARD_V2",
        )
        return {"path": path, "source_step": "S6", "source_kind": "s6_evidence_payload", "data": data}
    except Exception as exc:
        print(f"BLOCKED_S7_S6_INPUT_MISSING:{exc}", file=sys.stderr)
        return {
            "path": None,
            "source_step": "UNKNOWN",
            "source_kind": "missing_expected_s6",
            "blocked_reason": "BLOCKED_S7_S6_INPUT_MISSING",
        }


def resolve_s7_input(
    child_env: dict[str, str],
    date: str | None,
    run_id: str | None,
    explicit_input: Path | None = None,
) -> dict[str, Any]:
    if explicit_input is not None:
        return _build_input_resolution(
            explicit_input.resolve(), source_step="S6", source_kind="certification_override"
        )
    resolved = _resolve_s6_input(child_env, date, run_id)
    path = resolved.get("path")
    if isinstance(path, Path):
        result = _build_input_resolution(path, source_step="S6", source_kind="s6_evidence_payload")
        result["data"] = resolved.get("data")
        return result
    return _build_input_resolution(
        None,
        source_step="UNKNOWN",
        source_kind="missing",
        blocked_reason=str(resolved.get("blocked_reason") or "BLOCKED_S7_S6_INPUT_MISSING"),
    )


def _base_payload(
    *,
    child_env: dict[str, str],
    mode: RuntimeMode,
    runtime_path_source: str,
    resolution: dict[str, Any],
    output: Path,
    args: argparse.Namespace,
) -> dict[str, Any]:
    return {
        "step_id": "S7",
        "wrapper_scripts": [],
        "runtime_mode": mode.value,
        "dry_run": bool(args.dry_run),
        "allow_write": bool(args.allow_write),
        "allow_live_network": bool(args.allow_live_network),
        "production_write": False,
        "runtime_path_source": runtime_path_source,
        "child_run_root": child_env["BET_PIPELINE_RUN_ROOT"],
        "child_artifact_dir": child_env["BET_PIPELINE_ARTIFACT_DIR"],
        "s7_json_output": str(output),
        **_input_payload_fields(resolution),
        "production_selectable": False,
        "betting_decisions_enabled": False,
        "no_pick_edge_stake_coupon_emitted": True,
        "ready_for_manual_placement": False,
    }


def _block(
    reason: str,
    *,
    payload: dict[str, Any],
    child_env: dict[str, str],
) -> None:
    payload.update({"wrapper_rc": 5, "status": reason})
    print(reason)
    write_terminal_script_evidence_or_fail(
        step_id="S7",
        status="BLOCK",
        payload=payload,
        sources=(),
        child_env=child_env,
        blocked_reasons=(reason,),
        no_pick_edge_stake_coupon_emitted=True,
    )
    raise SystemExit(5)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", "--betting-day", dest="date", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--runtime-mode", default="DRY_RUN")
    parser.add_argument("--allow-live-network", action="store_true", default=False)
    parser.add_argument("--allow-write", action="store_true", default=False)
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--input-hash")
    args = parser.parse_args()

    mode = parse_runtime_mode(args.runtime_mode)
    child_env, runtime_path_source = resolve_child_runtime_env(
        os.environ,
        runtime_mode=mode,
        betting_day=args.date,
        run_id=args.run_id,
        run_root=None,
    )
    run_root = Path(child_env["BET_PIPELINE_RUN_ROOT"])
    output = Path(child_env["BET_PIPELINE_DATA_DIR"]) / f"{args.date}_s7_gate_results.json"
    empty_resolution = _build_input_resolution(None, source_step="UNKNOWN", source_kind="missing")

    if args.input is not None:
        if mode != RuntimeMode.CERTIFICATION:
            payload = _base_payload(
                child_env=child_env, mode=mode, runtime_path_source=runtime_path_source,
                resolution=empty_resolution, output=output, args=args,
            )
            _block("BLOCKED_S7_INPUT_OVERRIDE_FORBIDDEN", payload=payload, child_env=child_env)
        expected_hash = args.input_hash or os.environ.get("BET_PIPELINE_CERTIFICATION_INPUT_HASH")
        if (
            os.environ.get("BET_PIPELINE_CERTIFICATION_ACK")
            not in {"I_AM_CERTIFYING_THE_CANONICAL_REPLAY", "I_UNDERSTAND_CERTIFICATION_BYPASS"}
            or not is_safe_run_path(args.input, run_root)
            or not args.input.is_file()
            or not expected_hash
            or sha256_file(args.input) != expected_hash
        ):
            payload = _base_payload(
                child_env=child_env, mode=mode, runtime_path_source=runtime_path_source,
                resolution=empty_resolution, output=output, args=args,
            )
            _block("BLOCKED_S7_CERTIFICATION_OVERRIDE_INVALID", payload=payload, child_env=child_env)

    resolution = resolve_s7_input(child_env, args.date, args.run_id, args.input)
    payload = _base_payload(
        child_env=child_env,
        mode=mode,
        runtime_path_source=runtime_path_source,
        resolution=resolution,
        output=output,
        args=args,
    )
    input_path = resolution.get("path")
    if resolution.get("blocked_reason") or not isinstance(input_path, Path):
        _block("BLOCKED_S7_S6_INPUT_MISSING", payload=payload, child_env=child_env)
    if not is_safe_run_path(input_path, run_root) or not is_safe_run_path(output, run_root):
        _block("BLOCKED_S7_GATE_INPUT_PROTECTED_PATH", payload=payload, child_env=child_env)

    try:
        s6_data = resolution.get("data") or _load_json(input_path)
        if not isinstance(s6_data, dict):
            raise ValueError("S7_SOURCE_S6_JSON_INVALID")
        result = evaluate_s7_hard_gate(
            s6_data,
            source_s6_path=input_path,
            betting_day=args.date,
            run_id=args.run_id,
        )
        receipt = publish_run_artifact(
            run_root=run_root,
            target=output,
            payload=result,
            betting_day=args.date,
            run_id=args.run_id,
            artifact_type="S7_ANALYTICAL_APPROVAL_SET_V2",
            immutable=True,
        )
    except Exception as exc:
        payload["contract_error"] = f"{type(exc).__name__}:{exc}"
        _block("BLOCKED_S7_S6_CONTRACT_INVALID", payload=payload, child_env=child_env)

    approved_count = len(result["priced_approved"]) + len(result["analytical_approved"])
    payload.update(
        {
            "wrapper_rc": 0,
            "s7_output_sha256": receipt.sha256,
            "total_candidates": result["input_candidate_count"],
            "approved_count": approved_count,
            "extended_count": len(result["analytical_approved"]),
            "rejected_count": len(result["rejected"]),
            "ready_for_manual_operator_quote_review": approved_count > 0,
            "status": result["outcome"],
            "accounting": result["accounting"],
        }
    )
    write_terminal_script_evidence_or_fail(
        step_id="S7",
        status="PASS",
        payload=payload,
        sources=(f"{input_path}#{result['source_s6_sha256']}",),
        child_env=child_env,
        no_pick_edge_stake_coupon_emitted=True,
    )
    raise SystemExit(0)


if __name__ == "__main__":
    main()
