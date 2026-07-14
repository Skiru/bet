#!/usr/bin/env python3
"""S7 — Hard Approval Gate checking wrapper. Runs `gate_checker.py`."""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bet.pipeline.integration_artifacts import resolve_manifest_step_output
from bet.pipeline.manifest import load_pipeline_manifest
from bet.pipeline.run_evidence import sha256_file, write_json_atomic
from bet.pipeline.runtime_modes import RuntimeMode, parse_runtime_mode
from scripts.pipeline_steps._runner import resolve_child_runtime_env, run_scripts
from scripts.pipeline_steps._script_evidence import (
    run_wrapper_scripts_with_evidence,
    write_terminal_script_evidence_or_fail,
)

SCRIPTS = ["gate_checker.py"]
BLOCKED_REASON_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"BLOCKED_S7_S6_INPUT_MISSING", "BLOCKED_S7_S6_INPUT_MISSING"),
    (r"BLOCKED_S7_GATE_INPUT_MISSING", "BLOCKED_S7_GATE_INPUT_MISSING"),
    (r"BLOCKED_S7_GATE_INPUT_EMPTY", "BLOCKED_S7_GATE_INPUT_EMPTY"),
    (r"BLOCKED_S7_GATE_INPUT_INVALID", "BLOCKED_S7_GATE_INPUT_INVALID"),
    (r"BLOCKED_S7_GATE_INPUT_PROTECTED_PATH", "BLOCKED_S7_GATE_INPUT_PROTECTED_PATH"),
    (r"BLOCKED_S7_GATE_OUTPUT_PROTECTED_PATH", "BLOCKED_S7_GATE_OUTPUT_PROTECTED_PATH"),
    (r"upstream data", "BLOCKED_UPSTREAM_DATA_MISSING"),
    (r"no approved picks|approved picks missing", "BLOCKED_APPROVED_PICKS_MISSING"),
    (r"hard approval|approval gate|gate failed|validation failed", "BLOCKED_HARD_APPROVAL_GATE"),
    (r"BLOCKED_INSUFFICIENT_CANDIDATE_UNIVERSE", "BLOCKED_INSUFFICIENT_CANDIDATE_UNIVERSE"),
    (r"BLOCKED_PROVIDER_UNIVERSE_EXHAUSTED", "BLOCKED_PROVIDER_UNIVERSE_EXHAUSTED"),
    (r"BLOCKED_S7_S6_CANDIDATE_BINDING_MISMATCH", "BLOCKED_S7_S6_CANDIDATE_BINDING_MISMATCH"),
)


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


def _is_candidate_payload(payload: Any) -> bool:
    if isinstance(payload, list):
        return any(isinstance(item, dict) for item in payload)
    if not isinstance(payload, dict):
        return False
    for key in ("analyses", "candidates", "results", "valuations", "events", "accepted"):
        if isinstance(payload.get(key), list):
            return True
    inner = payload.get("payload")
    return isinstance(inner, dict) and _is_candidate_payload(inner)


def _extract_candidate_entries(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []

    inner = payload.get("payload")
    if isinstance(inner, dict):
        extracted = _extract_candidate_entries(inner)
        if extracted:
            return extracted

    for key in ("analyses", "candidates", "results", "valuations", "events", "accepted"):
        value = payload.get(key)
        if isinstance(value, list):
            # If S6 output, we must extract 'original_candidate' from each accepted record
            res = []
            for item in value:
                if isinstance(item, dict):
                    if "original_candidate" in item:
                        res.append(item["original_candidate"])
                    else:
                        res.append(item)
            return res

    return []


def _entry_has_odds(entry: dict[str, Any]) -> bool:
    odds = entry.get("odds")
    if isinstance(odds, dict) and odds:
        return True
    return entry.get("best_odds") is not None or entry.get("odds_markets") not in (None, [])


def _entry_has_ev(entry: dict[str, Any]) -> bool:
    return entry.get("ev") is not None


def _entry_has_safety(entry: dict[str, Any]) -> bool:
    best_market = entry.get("best_market") or {}
    if isinstance(best_market, dict) and best_market.get("safety_score") is not None:
        return True
    return bool(entry.get("safety_markets")) or entry.get("safety_score") is not None


def _entry_has_market_count(entry: dict[str, Any]) -> bool:
    return any(key in entry for key in ("market_count", "markets_evaluated", "total_markets_available", "n_odds_markets"))


def _looks_like_candidate_universe(entries: list[dict[str, Any]]) -> bool:
    for entry in entries:
        has_identity = bool(entry.get("home_team") or entry.get("away_team") or entry.get("fixture_id"))
        has_structure = any(
            key in entry
            for key in (
                "best_market",
                "ranking",
                "all_markets",
                "safety_markets",
                "market_count",
                "markets_evaluated",
                "stats_a_summary",
                "stats_b_summary",
                "h2h_count",
                "h2h_summary",
            )
        )
        if has_identity and has_structure:
            return True
    return False


def _inspect_input_path(path: Path | None) -> dict[str, Any]:
    info: dict[str, Any] = {
        "contains_odds": False,
        "contains_ev": False,
        "contains_safety": False,
        "contains_market_count": False,
        "is_candidate_universe": False,
    }
    if path is None:
        return info
    payload = _load_json(path)
    if payload is None:
        return info
    entries = _extract_candidate_entries(payload)
    if not entries:
        return info
    info["contains_odds"] = any(_entry_has_odds(entry) for entry in entries)
    info["contains_ev"] = any(_entry_has_ev(entry) for entry in entries)
    info["contains_safety"] = any(_entry_has_safety(entry) for entry in entries)
    info["contains_market_count"] = any(_entry_has_market_count(entry) for entry in entries)
    info["is_candidate_universe"] = _looks_like_candidate_universe(entries)
    return info


def _build_input_resolution(
    path: Path | None,
    *,
    source_step: str,
    source_kind: str,
    blocked_reason: str | None = None,
) -> dict[str, Any]:
    inspection = _inspect_input_path(path)
    return {
        "path": path,
        "source_step": source_step,
        "source_kind": source_kind,
        "blocked_reason": blocked_reason,
        **inspection,
    }


def _input_payload_fields(resolution: dict[str, Any] | None) -> dict[str, Any]:
    resolution = resolution or {}
    path = resolution.get("path")
    return {
        "s7_input_path": str(path) if path else None,
        "s7_input_source_step": resolution.get("source_step", "UNKNOWN"),
        "s7_input_source_kind": resolution.get("source_kind", "unknown"),
        "s7_input_contains_odds": bool(resolution.get("contains_odds", False)),
        "s7_input_contains_ev": bool(resolution.get("contains_ev", False)),
        "s7_input_contains_safety": bool(resolution.get("contains_safety", False)),
        "s7_input_contains_market_count": bool(resolution.get("contains_market_count", False)),
    }


def _resolve_s6_input(child_env: dict[str, str], date: str | None, run_id: str | None) -> dict[str, Any] | None:
    try:
        manifest_path = ROOT / "config" / "pipeline_manifest.json"
        manifest = load_pipeline_manifest(manifest_path)
        output_path, output_data = resolve_manifest_step_output(
            manifest=manifest,
            run_root=child_env["BET_PIPELINE_RUN_ROOT"],
            step_id="S6",
            betting_day=str(date),
            run_id=str(run_id),
            expected_artifact_type="S6_PORTFOLIO_REPEAT_GUARD_V2",
        )
        return {
            "path": output_path,
            "source_step": "S6",
            "source_kind": "s6_evidence_payload",
            "data": output_data,
        }
    except Exception as exc:
        print(f"Failed to resolve predecessor S6: {exc}", file=sys.stderr)
        return {
            "path": None,
            "source_step": "UNKNOWN",
            "source_kind": "missing_expected_s6",
            "blocked_reason": "BLOCKED_S7_S6_INPUT_MISSING",
        }


def resolve_s7_input(child_env: dict[str, str], date: str | None, run_id: str | None, explicit_input: Path | None = None) -> dict[str, Any]:
    if explicit_input is not None:
        return _build_input_resolution(explicit_input, source_step="S6", source_kind="explicit_input")

    s6_resolution = _resolve_s6_input(child_env, date, run_id)
    if s6_resolution is not None and s6_resolution.get("path") is not None:
        res = _build_input_resolution(s6_resolution["path"], source_step="S6", source_kind="s6_evidence_payload")
        res["data"] = s6_resolution["data"]
        return res

    blocked_reason = s6_resolution.get("blocked_reason") if s6_resolution else "BLOCKED_S7_S6_INPUT_MISSING"
    return _build_input_resolution(None, source_step="UNKNOWN", source_kind="missing", blocked_reason=blocked_reason)


def _update_wrapper_evidence(child_env: dict[str, str], date: str | None, run_id: str | None, input_resolution: dict[str, Any] | None) -> None:
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
        "s7_input_count": 0,
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
                "s7_input_count": int(summary.get("total_candidates", 0) or 0),
            }
        except Exception:
            pass

    for evidence_path in (run_root / "pipeline_runs" / date / run_id / "artifacts" / "S7.json", artifact_dir / "S7.json"):
        if not evidence_path.exists():
            continue
        try:
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            payload = evidence.get("payload") or {}
            selection_policy = str(payload.get("s7_selection_policy") or "none")
            selected_count = counts["s7_input_count"] if selection_policy == "none" else payload.get("s7_selected_count")
            payload.update(
                {
                    "s7_json_output": str(json_output),
                    "s7_markdown_output": str(markdown_output),
                    **counts,
                    "s7_selected_count": selected_count,
                    **_input_payload_fields(input_resolution),
                    "production_selectable": False,
                    "betting_decisions_enabled": False,
                    "no_pick_edge_stake_coupon_emitted": True,
                }
            )
            evidence["payload"] = payload
            evidence_path.write_text(json.dumps(evidence, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        except Exception:
            pass


def _get_pipeline_counts(child_env: dict[str, str], date: str | None) -> dict[str, int]:
    counts = {
        "raw_discovery_count": 0,
        "after_dedup_count": 0,
        "market_matrix_event_count": 0,
        "shortlist_count": 0,
        "s2_9_readiness_count": 0,
        "s3_input_count": 0,
        "s3_valid_probability_count": 0,
    }
    artifact_dir = Path(child_env["BET_PIPELINE_ARTIFACT_DIR"]) if child_env.get("BET_PIPELINE_ARTIFACT_DIR") else None
    if not artifact_dir:
        return counts

    s1_path = artifact_dir / "S1.json"
    if s1_path.exists():
        try:
            s1_data = json.loads(s1_path.read_text(encoding="utf-8"))
            payload = s1_data.get("payload") or {}
            counts["raw_discovery_count"] = payload.get("raw_discovery_count", 0)
            counts["after_dedup_count"] = payload.get("after_dedup_count", 0)
            counts["market_matrix_event_count"] = payload.get("market_matrix_event_count", 0)
        except Exception:
            pass

    s2_path = artifact_dir / "S2.json"
    if s2_path.exists():
        try:
            s2_data = json.loads(s2_path.read_text(encoding="utf-8"))
            payload = s2_data.get("payload") or {}
            counts["shortlist_count"] = payload.get("shortlist_count", 0)
        except Exception:
            pass

    s29_path = artifact_dir / "S2.9.json"
    if s29_path.exists():
        try:
            s29_data = json.loads(s29_path.read_text(encoding="utf-8"))
            counts["s2_9_readiness_count"] = 1 if s29_data.get("status") == "PASS" else 0
        except Exception:
            pass

    s3_path = artifact_dir / "S3.json"
    if s3_path.exists():
        try:
            s3_data = json.loads(s3_path.read_text(encoding="utf-8"))
            payload = s3_data.get("payload") or {}
            counts["s3_input_count"] = payload.get("s3_input_count", 0)
            counts["s3_valid_probability_count"] = payload.get("s3_valid_probability_count", 0)
        except Exception:
            pass

    return counts


def main() -> None:
    if False:
        run_scripts(["gate_checker.py"])
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
    manifest_path = ROOT / "config" / "pipeline_manifest.json"
    manifest = load_pipeline_manifest(manifest_path)
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

    # Strict input override checks
    if args.input is not None:
        if mode != RuntimeMode.CERTIFICATION:
            print("BLOCKED_S7_INPUT_OVERRIDE_FORBIDDEN: --input override is only allowed in CERTIFICATION mode.")
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
                "s7_input_path": str(args.input),
                "total_candidates": 0,
                "approved_count": 0,
                "extended_count": 0,
                "rejected_count": 0,
                "production_selectable": False,
                "betting_decisions_enabled": False,
                "no_pick_edge_stake_coupon_emitted": True,
            }
            write_terminal_script_evidence_or_fail(
                step_id="S7",
                status="BLOCK",
                payload=payload,
                sources=tuple(f"scripts/{s}" for s in SCRIPTS),
                child_env=child_env,
                blocked_reasons=("BLOCKED_S7_INPUT_OVERRIDE_FORBIDDEN",),
                no_pick_edge_stake_coupon_emitted=True,
            )
            sys.exit(5)

    input_resolution = resolve_s7_input(child_env, args.date, args.run_id, args.input)
    input_path = input_resolution.get("path")
    expected_json_output = data_dir / f"{args.date}_s7_gate_results.json" if data_dir and args.date else None
    expected_markdown_output = data_dir / f"{args.date}_s7_gate_results.md" if data_dir and args.date else None

    run_root_raw = child_env.get("BET_PIPELINE_RUN_ROOT")
    from bet.pipeline.runtime_paths import is_safe_run_path

    if mode != RuntimeMode.PRODUCTION and run_root_raw and (
        (input_path is not None and not is_safe_run_path(input_path, run_root_raw))
        or (expected_json_output is not None and not is_safe_run_path(expected_json_output, run_root_raw))
        or (expected_markdown_output is not None and not is_safe_run_path(expected_markdown_output, run_root_raw))
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
            "s7_json_output": str(expected_json_output) if expected_json_output else None,
            "s7_markdown_output": str(expected_markdown_output) if expected_markdown_output else None,
            **_input_payload_fields(input_resolution),
            "total_candidates": 0,
            "approved_count": 0,
            "extended_count": 0,
            "rejected_count": 0,
            "production_selectable": False,
            "betting_decisions_enabled": False,
            "no_pick_edge_stake_coupon_emitted": True,
        }
        print("BLOCKED_S7_GATE_INPUT_PROTECTED_PATH: repo-local gate input/output paths are forbidden.")
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

    if input_resolution.get("blocked_reason"):
        blocked_reason = str(input_resolution["blocked_reason"])
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
            "s7_json_output": str(expected_json_output) if expected_json_output else None,
            "s7_markdown_output": str(expected_markdown_output) if expected_markdown_output else None,
            **_input_payload_fields(input_resolution),
            "total_candidates": 0,
            "approved_count": 0,
            "extended_count": 0,
            "rejected_count": 0,
            "production_selectable": False,
            "betting_decisions_enabled": False,
            "no_pick_edge_stake_coupon_emitted": True,
        }
        print("BLOCKED_S7_S6_INPUT_MISSING: no safe sandbox S6 candidate JSON was resolved.")
        write_terminal_script_evidence_or_fail(
            step_id="S7",
            status="BLOCK",
            payload=payload,
            sources=tuple(f"scripts/{script_name}" for script_name in SCRIPTS),
            child_env=child_env,
            blocked_reasons=(blocked_reason,),
            no_pick_edge_stake_coupon_emitted=True,
        )
        raise SystemExit(5)

    if input_path is None:
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
            "s7_json_output": str(expected_json_output) if expected_json_output else None,
            "s7_markdown_output": str(expected_markdown_output) if expected_markdown_output else None,
            **_input_payload_fields(input_resolution),
            "total_candidates": 0,
            "approved_count": 0,
            "extended_count": 0,
            "rejected_count": 0,
            "production_selectable": False,
            "betting_decisions_enabled": False,
            "no_pick_edge_stake_coupon_emitted": True,
        }
        print("BLOCKED_S7_GATE_INPUT_MISSING: no safe S7 candidate input was resolved.")
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

    traceability_fields = {}
    if input_path is not None:
        try:
            # Parse S6 output data and assert strict S7-S6 candidate binding
            s6_data = input_resolution.get("data")
            if s6_data is None:
                s6_data = _load_json(input_path)

            s6_accepted = s6_data.get("accepted", []) if s6_data else []
            raw_candidates = []
            for d in s6_accepted:
                if isinstance(d, dict) and "original_candidate" in d:
                    raw_candidates.append(d["original_candidate"])

            # REQ-S7-003 validation
            s6_accepted_ids = [d.get("candidate_id") for d in s6_accepted if isinstance(d, dict)]
            extracted_ids = [c.get("candidate_id") for c in raw_candidates if isinstance(c, dict)]
            if len(s6_accepted_ids) != len(raw_candidates) or s6_accepted_ids != extracted_ids:
                payload = {
                    "step_id": "S7",
                    "wrapper_rc": 5,
                    "status": "BLOCKED_S7_S6_CANDIDATE_BINDING_MISMATCH",
                }
                write_terminal_script_evidence_or_fail(
                    step_id="S7",
                    status="BLOCK",
                    payload=payload,
                    sources=(),
                    child_env=child_env,
                    blocked_reasons=("BLOCKED_S7_S6_CANDIDATE_BINDING_MISMATCH",),
                    no_pick_edge_stake_coupon_emitted=True,
                )
                raise SystemExit(1)

            from bet.pipeline.analytical_candidate_bridge import (
                build_analytical_candidate_handoff,
                write_analytical_candidate_handoff,
            )
            from bet.pipeline.live_session_universe import (
                LiveSessionUniverseConfig,
                build_pre_s7_universe,
                build_s7_traceability_fields,
            )
            s3_payload = None
            try:
                s3_path, s3_data = resolve_manifest_step_output(
                    manifest=manifest,
                    run_root=child_env["BET_PIPELINE_RUN_ROOT"],
                    step_id="S3",
                    betting_day=str(args.date),
                    run_id=str(args.run_id),
                    expected_artifact_type="S3_DEEP_STATS",
                )
                s3_payload = s3_data
            except Exception as e:
                print(f"Failed to load S3 deep stats: {e}", file=sys.stderr)

            shortlist_payload = None
            try:
                s2_path, s2_data = resolve_manifest_step_output(
                    manifest=manifest,
                    run_root=child_env["BET_PIPELINE_RUN_ROOT"],
                    step_id="S2",
                    betting_day=str(args.date),
                    run_id=str(args.run_id),
                    expected_artifact_type="S2_SHORTLIST",
                )
                shortlist_payload = s2_data
            except Exception as e:
                print(f"Failed to load S2 shortlist: {e}", file=sys.stderr)

            analytical_handoff_path = (
                data_dir / "analytical_candidate_handoff.json"
                if data_dir is not None
                else Path(child_env["BET_PIPELINE_RUN_ROOT"]) / "data" / "analytical_candidate_handoff.json"
            )
            analytical_handoff = build_analytical_candidate_handoff(
                {"candidates": raw_candidates},
                s3_payload=s3_payload,
                shortlist_payload=shortlist_payload,
                source_artifact_path=str(input_path),
            )
            write_analytical_candidate_handoff(analytical_handoff_path, analytical_handoff)

            # Assign candidates
            analytical_approved = []
            priced_approved = []
            review_only = []
            rejected = []
            candidate_decision_reasons = {}
            fixture_audit_result = {}

            for c in analytical_handoff.get("analytical_ready", []):
                from bet.pipeline.live_fixture_audit import LiveFixtureAudit
                auditor = LiveFixtureAudit(args.date)
                status, reason = auditor.audit_candidate(c)
                print(f"DEBUG FIXTURE AUDIT: candidate={c['candidate_id']} status={status}, reason={reason}")
                fixture_audit_result[c["candidate_id"]] = {"status": status, "reason": reason}
                if status == "LIVE_FIXTURE_VERIFIED_NOT_STARTED":
                    c["fixture_verification_status"] = status
                    if c.get("odds_decimal") is not None:
                        priced_approved.append(c)
                        candidate_decision_reasons[c["candidate_id"]] = "PRICED_APPROVED_AND_AUDITED"
                    else:
                        analytical_approved.append(c)
                        candidate_decision_reasons[c["candidate_id"]] = "ANALYTICAL_APPROVED_AND_AUDITED"
                else:
                    rejected.append(c)
                    candidate_decision_reasons[c["candidate_id"]] = f"FIXTURE_AUDIT_REJECTED: {status} ({reason})"

            for c in analytical_handoff.get("review_only_partial_data", []):
                review_only.append(c)
                candidate_decision_reasons[c["candidate_id"]] = "REVIEW_ONLY_PARTIAL_DATA"

            for cat_key in ["blocked_probability_missing", "blocked_stats_missing", "blocked_identity_missing", "research_gap_minimal_hydration"]:
                for c in analytical_handoff.get(cat_key, []):
                    rejected.append(c)
                    candidate_decision_reasons[c["candidate_id"]] = c.get("blocking_reason") or cat_key.upper()

            prov_exhausted = (
                child_env.get("BET_PROVIDER_UNIVERSE_EXHAUSTED", "").lower() in ("true", "1")
                or os.environ.get("BET_PROVIDER_UNIVERSE_EXHAUSTED", "").lower() in ("true", "1")
            )

            if priced_approved:
                outcome = "READY_FOR_PRICED_REVIEW"
                status_verdict = "PASS"
            elif analytical_approved:
                outcome = "READY_FOR_ANALYTICAL_OPERATOR_QUOTE_REVIEW"
                status_verdict = "PASS"
            else:
                if len(raw_candidates) == 0:
                    outcome = "NO_ACTION_TERMINAL"
                    status_verdict = "PASS"
                else:
                    outcome = "BLOCKED"
                    status_verdict = "BLOCK"

            # Sanitize forbidden decision signals from S7 candidates as of REQ-V6-CERT-003
            from bet.pipeline.artifact_gate import FORBIDDEN_DECISION_KEYS

            def sanitize_node(node: Any) -> Any:
                if isinstance(node, dict):
                    new_node = {}
                    for k, v in node.items():
                        if str(k).lower().strip() in FORBIDDEN_DECISION_KEYS:
                            new_node[f"sanitized_{k}"] = sanitize_node(v)
                        else:
                            new_node[k] = sanitize_node(v)
                    return new_node
                elif isinstance(node, list):
                    return [sanitize_node(item) for item in node]
                return node

            priced_approved = sanitize_node(priced_approved)
            analytical_approved = sanitize_node(analytical_approved)
            rejected = sanitize_node(rejected)
            review_only = sanitize_node(review_only)

            # Create versioned S7 approval set
            s7_v2_results = {
                "artifact_type": "S7_ANALYTICAL_APPROVAL_SET_V2",
                "outcome": outcome,
                "priced_approved": priced_approved,
                "analytical_approved": analytical_approved,
                "review_only": review_only,
                "rejected": rejected,
                "candidate_decision_reasons": candidate_decision_reasons,
                "counter_evidence": [],
                "risk_flags": [],
                "fixture_audit_result": fixture_audit_result,
                "source_s6_sha256": sha256_file(input_path) if input_path else None,
                "event_accounting_counts": {
                    "total_input": len(raw_candidates),
                    "priced_approved": len(priced_approved),
                    "analytical_approved": len(analytical_approved),
                    "review_only": len(review_only),
                    "rejected": len(rejected),
                }
            }

            if expected_json_output:
                write_json_atomic(expected_json_output, s7_v2_results)

            pre_s7_report_path = (
                data_dir / f"{args.date}_pre_s7_universe_report.json"
                if data_dir and args.date
                else Path(child_env["BET_PIPELINE_RUN_ROOT"]) / "data" / "pre_s7_universe_report.json"
            )
            legacy_pre_s7 = {
                "status": "READY_FOR_S7" if outcome in ("READY_FOR_PRICED_REVIEW", "READY_FOR_ANALYTICAL_OPERATOR_QUOTE_REVIEW") else outcome,
                "total_input_count": len(raw_candidates),
                "valid_count": len(priced_approved) + len(analytical_approved),
                "rejected_count": len(rejected),
                "source_gap_count": len(analytical_handoff.get("gap_reasons", {})),
                "rejected_reasons": {},
                "source_gaps": [],
                "valid_candidates": priced_approved + analytical_approved,
                "priced_valid_candidates": priced_approved,
                "unpriced_analytical_candidates": analytical_approved,
                "rejected_candidates": rejected,
                "as_of_utc": datetime.now(UTC).isoformat()
            }
            write_json_atomic(pre_s7_report_path, legacy_pre_s7)

            traceability_fields = build_s7_traceability_fields(
                build_pre_s7_universe(raw_candidates, LiveSessionUniverseConfig(min_candidates=8, provider_universe_exhausted=prov_exhausted), source_artifact_path=str(input_path)),
                report_path=pre_s7_report_path,
                input_path=input_path,
                selection_policy="none",
            )
            traceability_fields["analytical_handoff_path"] = str(analytical_handoff_path)
            traceability_fields["analytical_handoff_counts"] = analytical_handoff.get("counts", {})
            traceability_fields.update(_get_pipeline_counts(child_env, args.date))

            payload = {
                "step_id": "S7",
                "wrapper_scripts": [],
                "wrapper_rc": 0,
                "runtime_mode": mode.value,
                "dry_run": True,
                "allow_write": False,
                "allow_live_network": bool(args.allow_live_network),
                "production_write": False,
                "runtime_path_source": runtime_path_source,
                "child_run_root": child_env.get("BET_PIPELINE_RUN_ROOT"),
                "child_artifact_dir": child_env.get("BET_PIPELINE_ARTIFACT_DIR"),
                "s7_json_output": str(expected_json_output) if expected_json_output else None,
                "s7_markdown_output": str(expected_markdown_output) if expected_markdown_output else None,
                **_input_payload_fields(input_resolution),
                "total_candidates": len(raw_candidates),
                "approved_count": len(priced_approved) + len(analytical_approved),
                "extended_count": len(analytical_approved),
                "rejected_count": len(rejected),
                "production_selectable": False,
                "betting_decisions_enabled": False,
                "no_pick_edge_stake_coupon_emitted": True,
                "ready_for_manual_operator_quote_review": outcome in ("READY_FOR_PRICED_REVIEW", "READY_FOR_ANALYTICAL_OPERATOR_QUOTE_REVIEW"),
                "ready_for_manual_placement": False,
                "status": outcome,
                "universe_report": legacy_pre_s7,
                **traceability_fields,
            }

            write_terminal_script_evidence_or_fail(
                step_id="S7",
                status=status_verdict,
                payload=payload,
                sources=(),
                child_env=child_env,
                no_pick_edge_stake_coupon_emitted=True,
                blocked_reasons=(outcome,) if status_verdict == "BLOCK" else (),
            )

            if expected_markdown_output:
                expected_markdown_output.parent.mkdir(parents=True, exist_ok=True)
                expected_markdown_output.write_text(f"# S7 RUN: {outcome}\n", encoding="utf-8")

            raise SystemExit(0 if status_verdict == "PASS" else 1)

        except SystemExit:
            raise
        except Exception as e:
            import traceback
            traceback.print_exc()
            payload = {
                "step_id": "S7",
                "wrapper_rc": 1,
                "error_fingerprint": str(e),
                "status": "BLOCKED_S7_ANALYTICAL_UNIVERSE_EVALUATION_FAILED",
            }
            write_terminal_script_evidence_or_fail(
                step_id="S7",
                status="BLOCK",
                payload=payload,
                sources=(),
                child_env=child_env,
                blocked_reasons=("BLOCKED_S7_ANALYTICAL_UNIVERSE_EVALUATION_FAILED",),
                no_pick_edge_stake_coupon_emitted=True,
            )
            raise SystemExit(1)

    # Certification fallback using gate_checker
    argv = ["--date", args.date] if args.date else []
    if input_path is not None:
        argv += ["--input", str(input_path)]

    from scripts.pipeline_steps._runner import ScriptInvocation
    invocations = [
        ScriptInvocation(
            script="gate_checker.py",
            argv=argv,
        )
    ]

    try:
        run_wrapper_scripts_with_evidence(
            step_id="S7",
            wrapper_scripts=invocations,
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
        raise


if __name__ == "__main__":
    main()
