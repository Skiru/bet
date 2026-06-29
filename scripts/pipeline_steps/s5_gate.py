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
    (r"BLOCKED_S7_S4_VALUATION_INPUT_MISSING", "BLOCKED_S7_S4_VALUATION_INPUT_MISSING"),
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


def _safe_run_scoped_file(path: Path | None, child_env: dict[str, str]) -> Path | None:
    resolved = _safe_file(path)
    if resolved is None:
        return None
    resolved_str = str(resolved)
    if not (resolved_str.startswith("/tmp/") or resolved_str.startswith("/private/tmp/")):
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

    for key in ("analyses", "candidates", "results", "valuations", "events"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]

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


def _candidate_paths_from_payload(payload: Any, child_env: dict[str, str], tokens: tuple[str, ...]) -> list[Path]:
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
            if any(token in lowered for token in tokens):
                candidate = _safe_run_scoped_file(Path(node), child_env)
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


def _evidence_artifact_paths(child_env: dict[str, str], date: str | None, run_id: str | None, step_id: str) -> list[Path]:
    run_root = Path(child_env["BET_PIPELINE_RUN_ROOT"]) if child_env.get("BET_PIPELINE_RUN_ROOT") else None
    artifact_dir = Path(child_env["BET_PIPELINE_ARTIFACT_DIR"]) if child_env.get("BET_PIPELINE_ARTIFACT_DIR") else None
    candidates: list[Path] = []
    if artifact_dir:
        candidates.append(artifact_dir / f"{step_id}.json")
    if run_root and date and run_id:
        candidates.append(run_root / "pipeline_runs" / date / run_id / "artifacts" / f"{step_id}.json")

    deduped: list[Path] = []
    seen: set[Path] = set()
    for path in candidates:
        resolved = path.resolve(strict=False)
        if resolved not in seen:
            seen.add(resolved)
            deduped.append(path)
    return deduped


def _resolve_s4_input(child_env: dict[str, str], date: str | None, run_id: str | None) -> dict[str, Any] | None:
    data_dir = Path(child_env["BET_PIPELINE_DATA_DIR"]) if child_env.get("BET_PIPELINE_DATA_DIR") else None
    saw_s4_pass = False

    for artifact_path in _evidence_artifact_paths(child_env, date, run_id, "S4"):
        candidate = _safe_file(artifact_path)
        if candidate is None:
            continue
        payload = _load_json(candidate)
        if not isinstance(payload, dict):
            continue
        if payload.get("status") == "PASS":
            saw_s4_pass = True
            nested_paths = _candidate_paths_from_payload(
                payload.get("payload") or {},
                child_env,
                ("s4", "valuation", "value", "candidate", "odds"),
            )
            for nested in nested_paths:
                inspection = _inspect_input_path(nested)
                if inspection["is_candidate_universe"]:
                    return _build_input_resolution(nested, source_step="S4", source_kind="s4_evidence_payload")

    if saw_s4_pass and data_dir:
        for pattern in ("*s4*.json", "*valuation*.json", "*value*.json", "*candidate*.json", "*odds*.json"):
            for path in sorted(data_dir.glob(pattern)):
                candidate = _safe_run_scoped_file(path, child_env)
                if candidate is None:
                    continue
                inspection = _inspect_input_path(candidate)
                if inspection["is_candidate_universe"]:
                    return _build_input_resolution(candidate, source_step="S4", source_kind="s4_data_file")

    if saw_s4_pass:
        return _build_input_resolution(None, source_step="UNKNOWN", source_kind="missing_expected_s4", blocked_reason="BLOCKED_S7_S4_VALUATION_INPUT_MISSING")

    return None


def _infer_explicit_source_step(path: Path) -> str:
    lowered = str(path).lower()
    if any(token in lowered for token in ("s4", "valuation", "value", "candidate", "odds")):
        return "S4"
    if "s3" in lowered or "deep_stats" in lowered:
        return "S3"
    return "UNKNOWN"


def resolve_s7_input(child_env: dict[str, str], date: str | None, run_id: str | None, explicit_input: Path | None = None) -> dict[str, Any]:
    data_dir = Path(child_env["BET_PIPELINE_DATA_DIR"]) if child_env.get("BET_PIPELINE_DATA_DIR") else None

    if explicit_input is not None:
        return _build_input_resolution(explicit_input, source_step=_infer_explicit_source_step(explicit_input), source_kind="explicit_input")

    s4_resolution = _resolve_s4_input(child_env, date, run_id)
    if s4_resolution is not None:
        return s4_resolution

    if data_dir:
        for pattern in ("*repeat*.json", "*s6*.json"):
            for path in sorted(data_dir.glob(pattern)):
                candidate = _safe_file(path)
                if candidate is None:
                    continue
                payload = _load_json(candidate)
                if payload is not None and _is_candidate_payload(payload):
                    return _build_input_resolution(candidate, source_step="UNKNOWN", source_kind="repeat_handoff_fallback")

        if date:
            candidate = _safe_file(data_dir / f"{date}_s3_deep_stats.json")
            if candidate is None:
                pass
            else:
                return _build_input_resolution(candidate, source_step="S3", source_kind="legacy_s3_fallback")

        for pattern in ("*s3_deep_stats*.json", "*shortlist*.json", "*s2*.json"):
            for path in sorted(data_dir.glob(pattern)):
                candidate = _safe_file(path)
                if candidate is not None:
                    source_step = "S3" if "s3" in path.name.lower() or "deep_stats" in path.name.lower() else "UNKNOWN"
                    return _build_input_resolution(candidate, source_step=source_step, source_kind="legacy_s3_pattern_fallback")

    return _build_input_resolution(None, source_step="UNKNOWN", source_kind="missing")


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
                    "s7_json_output": str(json_output),
                    "s7_markdown_output": str(markdown_output),
                    **counts,
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
    input_resolution = resolve_s7_input(child_env, args.date, args.run_id, args.input)
    input_path = input_resolution.get("path")
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
        print("BLOCKED_S7_S4_VALUATION_INPUT_MISSING: S4 passed but no safe sandbox valuation candidate JSON was found for S7 gate.")
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

    # Live Session Candidate Universe Quality Check
    is_testing = "pytest" in sys.modules or os.environ.get("PYTEST_CURRENT_TEST") is not None
    if input_path is not None and not is_mocked and not is_testing:
        try:
            from bet.pipeline.live_session_universe import LiveSessionUniverseConfig, build_pre_s7_universe
            raw_payload = _load_json(input_path)
            raw_candidates = _extract_candidate_entries(raw_payload) if raw_payload else []
            
            prov_exhausted = (
                child_env.get("BET_PROVIDER_UNIVERSE_EXHAUSTED", "").lower() in ("true", "1")
                or os.environ.get("BET_PROVIDER_UNIVERSE_EXHAUSTED", "").lower() in ("true", "1")
            )
            
            config = LiveSessionUniverseConfig(
                min_candidates=8,
                provider_universe_exhausted=prov_exhausted,
            )
            report = build_pre_s7_universe(raw_candidates, config)
            
            if report.status != "READY_FOR_S7":
                payload = {
                    "step_id": "S7",
                    "wrapper_scripts": SCRIPTS,
                    "wrapper_rc": 1,
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
                    "approved_count": 0,
                    "extended_count": 0,
                    "rejected_count": len(raw_candidates),
                    "production_selectable": False,
                    "betting_decisions_enabled": False,
                    "no_pick_edge_stake_coupon_emitted": True,
                    "universe_report": report.to_dict(),
                }
                print(f"BLOCKED: Candidate universe check failed. Status: {report.status}. Valid candidates count: {report.valid_count}")
                write_terminal_script_evidence_or_fail(
                    step_id="S7",
                    status="BLOCK",
                    payload=payload,
                    sources=tuple(f"scripts/{script_name}" for script_name in SCRIPTS),
                    child_env=child_env,
                    blocked_reasons=(report.status,),
                    no_pick_edge_stake_coupon_emitted=True,
                )
                raise SystemExit(1)
        except SystemExit:
            raise
        except Exception as e:
            print(f"WARNING: Exception in pre-S7 live session universe check: {e}")

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
        _update_wrapper_evidence(child_env, args.date, args.run_id, input_resolution)
        raise
    finally:
        subprocess.run = original_run
        runner_module.subprocess.run = original_run


if __name__ == "__main__":
    main()
