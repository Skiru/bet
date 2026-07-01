#!/usr/bin/env python3
"""S3 — Feature derivation / deep stats wrapper. Runs `deep_stats_report.py`."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]

try:
    from bet.pipeline.runtime_modes import RuntimeMode, parse_runtime_mode
    from scripts.pipeline_steps._runner import _init_temp_db, run_scripts, resolve_child_runtime_env
    from scripts.pipeline_steps._script_evidence import (
        _assert_non_production_sandbox_safety,
        build_wrapper_payload,
        classify_wrapper_result,
        write_terminal_script_evidence_or_fail,
    )
except Exception:
    sys.path.insert(0, str(ROOT))
    from bet.pipeline.runtime_modes import RuntimeMode, parse_runtime_mode
    from scripts.pipeline_steps._runner import _init_temp_db, run_scripts, resolve_child_runtime_env
    from scripts.pipeline_steps._script_evidence import (
        _assert_non_production_sandbox_safety,
        build_wrapper_payload,
        classify_wrapper_result,
        write_terminal_script_evidence_or_fail,
    )

SCRIPTS = ["deep_stats_report.py"]
NON_PRODUCTION_MODES = {
    RuntimeMode.DRY_RUN,
    RuntimeMode.LIVE_SHADOW,
    RuntimeMode.CERTIFICATION,
}
SHORTLIST_GLOB_PATTERNS = (
    "*_s2_shortlist.json",
    "*s2*shortlist*.json",
    "*shortlist*.json",
)
BLOCKED_REASON_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"BLOCKED_S3_SHORTLIST_MISSING", "BLOCKED_S3_SHORTLIST_MISSING"),
    (r"BLOCKED_S3_SHORTLIST_INVALID", "BLOCKED_S3_SHORTLIST_INVALID"),
    (r"BLOCKED_S3_SHORTLIST_EMPTY", "BLOCKED_S3_SHORTLIST_EMPTY"),
    (r"upstream data", "BLOCKED_UPSTREAM_DATA_MISSING"),
    (r"insufficient data|no candidates|no events", "BLOCKED_STATS_GENERATION_INSUFFICIENT_DATA"),
)


def _certification_targets() -> None:
    run_scripts(SCRIPTS)


def _is_safe_tmp_path(path: Path) -> bool:
    try:
        normalized = str(path.expanduser())
        return normalized.startswith("/tmp/") or normalized.startswith("/private/tmp/")
    except OSError:
        return False


def _repo_data_dir() -> Path:
    return (ROOT / "betting" / "data").resolve()


def _is_repo_local_data_path(path: Path) -> bool:
    try:
        path.expanduser().resolve().relative_to(_repo_data_dir())
        return True
    except ValueError:
        return False
    except OSError:
        return False


def _is_safe_shortlist_path(path: Path, runtime_mode: RuntimeMode) -> bool:
    if not path.is_file():
        return False
    if runtime_mode not in NON_PRODUCTION_MODES:
        return True
    return _is_safe_tmp_path(path) and not _is_repo_local_data_path(path)


def _shortlist_priority(path: Path, betting_day: str | None) -> tuple[int, int, str]:
    name = path.name.lower()
    date_prefix = (betting_day or "").lower()
    score = 0
    if betting_day and name == f"{date_prefix}_s2_shortlist.json":
        score = 0
    elif "s2" in name and "shortlist" in name:
        score = 1
    elif "shortlist" in name:
        score = 2
    elif "candidate" in name:
        score = 3
    else:
        score = 4
    return (score, len(name), str(path))


def _unique_paths(paths: list[Path]) -> list[Path]:
    deduped: list[Path] = []
    seen: set[str] = set()
    for path in sorted(paths, key=lambda item: str(item)):
        expanded = path.expanduser()
        display_path = expanded if expanded.is_absolute() else expanded.resolve()
        dedupe_key = os.path.realpath(str(display_path))
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        deduped.append(Path(str(display_path)))
    return deduped


def _candidate_paths_from_directory(directory: Path, betting_day: str | None) -> list[Path]:
    if not directory.exists() or not directory.is_dir():
        return []
    matches: list[Path] = []
    for pattern in SHORTLIST_GLOB_PATTERNS:
        matches.extend(path for path in directory.glob(pattern) if path.is_file())
    return sorted(_unique_paths(matches), key=lambda item: _shortlist_priority(item, betting_day))


def _collect_json_path_strings(value: Any) -> list[Path]:
    matches: list[Path] = []
    if isinstance(value, str) and value.endswith(".json"):
        matches.append(Path(value))
    elif isinstance(value, dict):
        for child in value.values():
            matches.extend(_collect_json_path_strings(child))
    elif isinstance(value, list):
        for child in value:
            matches.extend(_collect_json_path_strings(child))
    return matches


def _candidate_paths_from_json_pointer(json_path: Path, betting_day: str | None, runtime_mode: RuntimeMode) -> list[Path]:
    if not _is_safe_shortlist_path(json_path, runtime_mode):
        return []
    try:
        payload = json.loads(json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    candidates = [
        path
        for path in _collect_json_path_strings(payload)
        if any(token in path.name.lower() for token in ("shortlist", "candidate", "s2"))
        and _is_safe_shortlist_path(path, runtime_mode)
    ]
    return sorted(_unique_paths(candidates), key=lambda item: _shortlist_priority(item, betting_day))


def _search_shortlist_candidates(
    *,
    child_env: dict[str, str],
    runtime_mode: RuntimeMode,
    betting_day: str | None,
    run_id: str | None,
) -> tuple[Path | None, list[str]]:
    searched_paths: list[str] = []
    candidates: list[Path] = []

    data_dir_value = child_env.get("BET_PIPELINE_DATA_DIR")
    if data_dir_value:
        data_dir = Path(data_dir_value)
        searched_paths.append(str(data_dir))
        candidates.extend(_candidate_paths_from_directory(data_dir, betting_day))

    run_root_value = child_env.get("BET_PIPELINE_RUN_ROOT")
    if run_root_value:
        run_root = Path(run_root_value)
        searched_paths.append(str(run_root))
        for relative in (Path("data"), Path("artifacts"), Path("pipeline_runs")):
            target_dir = run_root / relative
            searched_paths.append(str(target_dir))
            candidates.extend(_candidate_paths_from_directory(target_dir, betting_day))

        summary_path = run_root / "run_summary.json"
        searched_paths.append(str(summary_path))
        if summary_path.is_file():
            candidates.extend(_candidate_paths_from_json_pointer(summary_path, betting_day, runtime_mode))

        if betting_day and run_id:
            artifact_root = run_root / "pipeline_runs" / betting_day / run_id / "artifacts"
            searched_paths.append(str(artifact_root))
            candidates.extend(_candidate_paths_from_directory(artifact_root, betting_day))
            if artifact_root.is_dir():
                for artifact_path in artifact_root.glob("S*.json"):
                    searched_paths.append(str(artifact_path))
                    candidates.extend(_candidate_paths_from_json_pointer(artifact_path, betting_day, runtime_mode))

    safe_candidates = [path for path in _unique_paths(candidates) if _is_safe_shortlist_path(path, runtime_mode)]
    return (safe_candidates[0] if safe_candidates else None, searched_paths)


def _load_shortlist_event_count(path: Path) -> tuple[str | None, int | None]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ("BLOCKED_S3_SHORTLIST_INVALID", None)
    entries = payload.get("candidates", payload.get("events"))
    if not isinstance(entries, list):
        return ("BLOCKED_S3_SHORTLIST_INVALID", None)
    if not entries:
        return ("BLOCKED_S3_SHORTLIST_EMPTY", 0)
    return (None, len(entries))


def _s3_report_paths(data_dir: str | None, betting_day: str | None) -> list[str]:
    if not data_dir or not betting_day:
        return []
    candidates = [
        Path(data_dir) / f"{betting_day}_s3_deep_stats.md",
        Path(data_dir) / f"{betting_day}_s3_deep_stats.json",
    ]
    return [str(path.expanduser()) for path in candidates if path.exists()]


def _read_s3_report_json(data_dir: str | None, betting_day: str | None) -> dict[str, Any] | None:
    if not data_dir or not betting_day:
        return None
    report_path = Path(data_dir) / f"{betting_day}_s3_deep_stats.json"
    if not report_path.exists():
        return None
    try:
        return json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _build_evidence_fields(
    *,
    child_env: dict[str, str],
    runtime_path_source: str,
    shortlist_path: Path | None,
    shortlist_resolved: bool,
    shortlist_event_count: int | None,
    searched_paths: list[str],
    betting_day: str | None,
) -> dict[str, Any]:
    fields = {
        "shortlist_path": str(shortlist_path.expanduser()) if shortlist_path else None,
        "shortlist_resolved": shortlist_resolved,
        "shortlist_event_count": shortlist_event_count,
        "searched_paths": searched_paths,
        "runtime_mode": child_env.get("BET_PIPELINE_RUNTIME_MODE", "DRY_RUN"),
        "data_dir": child_env.get("BET_PIPELINE_DATA_DIR"),
        "run_root": child_env.get("BET_PIPELINE_RUN_ROOT"),
        "runtime_path_source": runtime_path_source,
        "s3_report_paths": _s3_report_paths(child_env.get("BET_PIPELINE_DATA_DIR"), betting_day),
        "production_selectable": False,
        "betting_decisions_enabled": False,
        "no_pick_edge_stake_coupon_emitted": True,
    }
    return fields


def _invoke_deep_stats_report(
    *,
    betting_day: str,
    shortlist_path: Path,
    child_env: dict[str, str],
    runtime_mode: RuntimeMode,
) -> tuple[int, str]:
    env = child_env.copy()
    temp_db_path: str | None = None
    try:
        if runtime_mode != RuntimeMode.PRODUCTION:
            fd, temp_db_path = tempfile.mkstemp(suffix=".db", prefix="bet_dryrun_")
            os.close(fd)
            _init_temp_db(temp_db_path)
            env["DATABASE_URL"] = f"sqlite:///{temp_db_path}"
            env["DRY_RUN"] = "1"

        cmd = [
            sys.executable,
            str(ROOT / "scripts" / "deep_stats_report.py"),
            "--date",
            betting_day,
            "--shortlist",
            str(shortlist_path.expanduser()),
        ]
        print("Running:", " ".join(cmd))
        res = subprocess.run(cmd, env=env, capture_output=True, text=True)
        output_parts = [part for part in (res.stdout, res.stderr) if part]
        output = "".join(output_parts)
        if output:
            sys.stdout.write(output)
            if not output.endswith("\n"):
                sys.stdout.write("\n")
        return res.returncode, output
    finally:
        if temp_db_path:
            try:
                os.unlink(temp_db_path)
            except OSError:
                pass


def _normalize_blocked_reasons(blocked_reasons: tuple[str, ...]) -> tuple[str, ...]:
    if "PRECONDITION_FAILED" in blocked_reasons:
        return tuple(
            "BLOCKED_STATS_INPUT_MISSING" if reason == "PRECONDITION_FAILED" else reason
            for reason in blocked_reasons
        )
    return blocked_reasons


def _exit_code_for_status(status: str, wrapper_rc: int) -> int:
    if status == "PASS":
        return 0
    if wrapper_rc > 0:
        return wrapper_rc
    if status == "FAILED":
        return 1
    return 2


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--date", "--betting-day", dest="date", help="YYYY-MM-DD", default=None)
    p.add_argument("--run-id", dest="run_id", help="Run ID", default=None)
    p.add_argument("--runtime-mode", dest="runtime_mode", help="Runtime mode", default="DRY_RUN")
    p.add_argument("--allow-live-network", dest="allow_live_network", action="store_true", default=False)
    p.add_argument("--allow-write", dest="allow_write", action="store_true", default=False)
    p.add_argument("--dry-run", dest="dry_run", action="store_true", default=True)
    args = p.parse_args()

    runtime_mode = parse_runtime_mode(args.runtime_mode)
    child_env, runtime_path_source = resolve_child_runtime_env(
        os.environ,
        runtime_mode=runtime_mode,
        betting_day=args.date,
        run_id=args.run_id,
        run_root=None,
    )
    _assert_non_production_sandbox_safety(runtime_mode=runtime_mode, child_env=child_env)

    shortlist_path, searched_paths = _search_shortlist_candidates(
        child_env=child_env,
        runtime_mode=runtime_mode,
        betting_day=args.date,
        run_id=args.run_id,
    )
    shortlist_error: str | None = None
    shortlist_event_count: int | None = None
    if shortlist_path is None:
        shortlist_error = "BLOCKED_S3_SHORTLIST_MISSING"
    else:
        shortlist_error, shortlist_event_count = _load_shortlist_event_count(shortlist_path)

    if shortlist_error is not None:
        print(shortlist_error)
        evidence_fields = _build_evidence_fields(
            child_env=child_env,
            runtime_path_source=runtime_path_source,
            shortlist_path=shortlist_path,
            shortlist_resolved=False,
            shortlist_event_count=shortlist_event_count,
            searched_paths=searched_paths,
            betting_day=args.date,
        )
        payload = build_wrapper_payload(
            step_id="S3",
            wrapper_scripts=SCRIPTS,
            wrapper_rc=2,
            runtime_mode=runtime_mode,
            dry_run=args.dry_run,
            allow_write=args.allow_write,
            allow_live_network=args.allow_live_network,
            child_env=child_env,
            runtime_path_source=runtime_path_source,
            extra=evidence_fields,
        )
        write_terminal_script_evidence_or_fail(
            step_id="S3",
            status="BLOCK",
            payload=payload,
            sources=("scripts/deep_stats_report.py",),
            child_env=child_env,
            blocked_reasons=(shortlist_error,),
            no_pick_edge_stake_coupon_emitted=True,
            extra_top_level_fields=evidence_fields,
        )
        raise SystemExit(2)

    wrapper_rc, output = _invoke_deep_stats_report(
        betting_day=args.date,
        shortlist_path=shortlist_path,
        child_env=child_env,
        runtime_mode=runtime_mode,
    )

    evidence_fields = _build_evidence_fields(
        child_env=child_env,
        runtime_path_source=runtime_path_source,
        shortlist_path=shortlist_path,
        shortlist_resolved=True,
        shortlist_event_count=shortlist_event_count,
        searched_paths=searched_paths,
        betting_day=args.date,
    )
    payload = build_wrapper_payload(
        step_id="S3",
        wrapper_scripts=SCRIPTS,
        wrapper_rc=wrapper_rc,
        runtime_mode=runtime_mode,
        dry_run=args.dry_run,
        allow_write=args.allow_write,
        allow_live_network=args.allow_live_network,
        child_env=child_env,
        runtime_path_source=runtime_path_source,
        extra=evidence_fields,
    )

    if wrapper_rc == 0:
        report_json = _read_s3_report_json(child_env.get("BET_PIPELINE_DATA_DIR"), args.date)
        if report_json is None:
            status = "BLOCK"
            blocked_reasons = ("BLOCKED_STATS_INPUT_MISSING",)
        elif shortlist_event_count and int(report_json.get("candidates_with_data", 0) or 0) == 0:
            print("BLOCKED_STATS_GENERATION_INSUFFICIENT_DATA")
            status = "BLOCK"
            blocked_reasons = ("BLOCKED_STATS_GENERATION_INSUFFICIENT_DATA",)
        else:
            status = "PASS"
            blocked_reasons = ()
    else:
        status, blocked_reasons = classify_wrapper_result(
            rc=wrapper_rc,
            output=output,
            blocked_reason_patterns=BLOCKED_REASON_PATTERNS,
            fallback_blocked_reason="BLOCKED_STATS_INPUT_MISSING",
        )
        blocked_reasons = _normalize_blocked_reasons(blocked_reasons)

    write_terminal_script_evidence_or_fail(
        step_id="S3",
        status=status,
        payload=payload,
        sources=("scripts/deep_stats_report.py",),
        child_env=child_env,
        blocked_reasons=blocked_reasons,
        no_pick_edge_stake_coupon_emitted=True,
        extra_top_level_fields=evidence_fields,
    )
    raise SystemExit(_exit_code_for_status(status, wrapper_rc))


if __name__ == "__main__":
    main()
