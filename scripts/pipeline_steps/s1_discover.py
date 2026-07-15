#!/usr/bin/env python3
"""S1 — Discovery / scan step wrapper. Runs `scripts/discover_events.py`.
"""
from __future__ import annotations

import argparse
import io
import os
import re
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

try:
    from scripts.pipeline_steps._runner import _init_temp_db, resolve_child_runtime_env, run_scripts
except Exception:
    ROOT = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(ROOT))
    from scripts.pipeline_steps._runner import _init_temp_db, resolve_child_runtime_env, run_scripts

from bet.pipeline.integration_artifacts import write_script_evidence
from bet.pipeline.run_coordination import redact_sensitive_text, run_bounded_process

import json

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = [
    "discover_events.py",
    "generate_market_matrix.py",
    "build_shortlist.py",
]
CONTROLLED_OUTPUT_REASONS: tuple[tuple[str, str], ...] = (
    (r"\b(BLOCKED_[A-Z0-9_]+)\b", "TOKEN"),
    (r"duplicate\s+fixture_sources\s+mapping", "BLOCKED_FIXTURE_SOURCE_DUPLICATE_MAPPING"),
    (r"migration\s+preflight\s+error", "BLOCKED_MIGRATION_PREFLIGHT"),
    (r"fixture_sources", "BLOCKED_FIXTURE_SOURCE_DUPLICATE_MAPPING"),
    (r"no\s+events\s+discovered", "BLOCKED_NO_DISCOVERY_EVENTS"),
    (r"market\s+matrix\s+missing", "BLOCKED_MISSING_MARKET_MATRIX"),
    (r"market_matrix.*not\s+found", "BLOCKED_MISSING_MARKET_MATRIX"),
)


def _payload(
    *,
    rc: int,
    runtime_mode: str,
    dry_run: bool,
    allow_write: bool,
    allow_live_network: bool,
    child_env: dict[str, str],
    runtime_path_source: str,
    run_metrics: dict[str, object],
) -> dict[str, object]:
    p = {
        "discover_and_shortlist_rc": rc,
        "runtime_mode": runtime_mode,
        "dry_run": dry_run,
        "allow_write": allow_write,
        "allow_live_network": allow_live_network,
        "scripts": list(SCRIPTS),
        "production_write": False,
        "settled_runtime_path_source": runtime_path_source,
        "child_run_root": child_env.get("BET_PIPELINE_RUN_ROOT"),
        "child_artifact_dir": child_env.get("BET_PIPELINE_ARTIFACT_DIR"),
    }
    p.update(run_metrics)
    return p


def _controlled_block_reasons(output: str) -> tuple[str, ...]:
    reasons: list[str] = []
    for pattern, reason in CONTROLLED_OUTPUT_REASONS:
        if reason == "TOKEN":
            reasons.extend(re.findall(pattern, output))
            continue
        if re.search(pattern, output, flags=re.IGNORECASE):
            reasons.append(reason)
    return tuple(dict.fromkeys(reasons))


def _write_terminal_evidence(*, status: str, payload: dict[str, object], blocked_reasons: tuple[str, ...] = ()) -> Path:
    evidence_path = write_script_evidence(
        "S1",
        status=status,
        payload=payload,
        sources=tuple(f"scripts/{script_name}" for script_name in SCRIPTS),
        evidence_refs=(),
        environ=os.environ,
        no_pick_edge_stake_coupon_emitted=True,
        production_selectable=False,
        betting_decisions_enabled=False,
        blocked_reasons=blocked_reasons,
    )
    if evidence_path is None:
        print("S1 wrapper failed closed: runtime context missing for canonical S1 script evidence", file=sys.stderr)
        raise SystemExit(70)
    return evidence_path


def _replay_output(output: str) -> None:
    if output:
        sys.stdout.write(output)
        if not output.endswith("\n"):
            sys.stdout.write("\n")


def _run_s1_scripts(
    *,
    date: str | None,
    dry_run: bool,
    allow_write: bool,
    allow_live_network: bool,
    runtime_mode: str,
    child_env: dict[str, str],
    run_metrics: dict[str, object],
) -> int:
    env = os.environ.copy()
    env.update(child_env)
    normalized_mode = (runtime_mode or "DRY_RUN").upper()

    if normalized_mode == "CERTIFICATION":
        print("BLOCKED_LIVE_NETWORK_ACK_MISSING")
        return 5
    if normalized_mode == "LIVE_SHADOW":
        if not allow_live_network:
            print("BLOCKED_LIVE_NETWORK_ACK_MISSING")
            return 5
        if env.get("BET_PIPELINE_LIVE_ACK", "") != "I_UNDERSTAND_LIVE_PROVIDER_CALLS":
            print("BLOCKED_LIVE_NETWORK_ACK_MISSING")
            return 5

    temp_db_path: str | None = None
    try:
        if dry_run and not allow_write:
            fd, temp_db_path = tempfile.mkstemp(suffix=".db", prefix="bet_dryrun_")
            os.close(fd)
            _init_temp_db(temp_db_path)
            env["DATABASE_URL"] = f"sqlite:///{temp_db_path}"
            env["DRY_RUN"] = "1"

        for script_name in SCRIPTS:
            cmd = [sys.executable, str(ROOT / "scripts" / script_name)]
            if date:
                cmd += ["--date", date]
            
            if script_name == "discover_events.py":
                db_url = env.get("DATABASE_URL", "")
                resolved_db_path = None
                if db_url.startswith("sqlite:///"):
                    resolved_db_path = db_url[len("sqlite:///"):]
                elif temp_db_path:
                    resolved_db_path = temp_db_path
                
                if resolved_db_path:
                    cmd += ["--db-path", resolved_db_path]
            elif script_name == "generate_market_matrix.py":
                cmd += [
                    "--output-dir", env.get("BET_PIPELINE_DATA_DIR", ""),
                    "--pipeline-safe",
                    "--json-only"
                ]
            
            # Validate the market matrix right before starting build_shortlist.py
            if script_name == "build_shortlist.py":
                matrix_date = date or env.get("BET_PIPELINE_BETTING_DAY")
                if not matrix_date:
                    import datetime
                    matrix_date = datetime.date.today().isoformat()
                
                data_dir_str = env.get("BET_PIPELINE_DATA_DIR")
                if not data_dir_str:
                    print("BLOCKED_SHORTLIST_INPUT_MISSING")
                    run_metrics["market_matrix_validated"] = False
                    return 2
                
                matrix_path = Path(data_dir_str) / f"market_matrix_{matrix_date}.json"
                if not matrix_path.exists():
                    print("BLOCKED_MISSING_MARKET_MATRIX")
                    run_metrics["market_matrix_validated"] = False
                    return 2
                
                try:
                    matrix_data = json.loads(matrix_path.read_text(encoding="utf-8"))
                except Exception:
                    print("BLOCKED_MARKET_MATRIX_INVALID")
                    run_metrics["market_matrix_validated"] = False
                    return 2
                
                if matrix_data.get("artifact_type") != "MARKET_MATRIX" or matrix_data.get("date") != matrix_date:
                    print("BLOCKED_MARKET_MATRIX_INVALID")
                    run_metrics["market_matrix_validated"] = False
                    return 2
                
                events = matrix_data.get("events")
                if not isinstance(events, list):
                    print("BLOCKED_MARKET_MATRIX_INVALID")
                    run_metrics["market_matrix_validated"] = False
                    return 2
                
                if len(events) == 0:
                    print("BLOCKED_MARKET_MATRIX_EMPTY")
                    run_metrics["market_matrix_validated"] = False
                    return 2
                
                # Check safety fields:
                if not matrix_data.get("pipeline_safe") or matrix_data.get("production_selectable") is not False or matrix_data.get("betting_decisions_enabled") is not False or matrix_data.get("no_pick_edge_stake_coupon_emitted") is not True:
                    print("BLOCKED_MARKET_MATRIX_INVALID")
                    run_metrics["market_matrix_validated"] = False
                    return 2
                
                forbidden_keys = {"recommended_pick", "internal_pick", "edge", "stake", "coupon", "parlay", "accumulator"}
                for e in events:
                    if not e.get("sport") or not e.get("home_team") or not e.get("away_team") or "data_tier" not in e or not e.get("kickoff"):
                        print("BLOCKED_MARKET_MATRIX_INVALID")
                        run_metrics["market_matrix_validated"] = False
                        return 2
                    for fk in forbidden_keys:
                        if fk in e:
                            print("BLOCKED_MARKET_MATRIX_INVALID")
                            run_metrics["market_matrix_validated"] = False
                            return 2
                        # Also check markets
                        for sub_list_name in ("odds_markets", "safety_markets"):
                            if sub_list_name in e and isinstance(e[sub_list_name], list):
                                for item in e[sub_list_name]:
                                    if isinstance(item, dict):
                                        for k in item:
                                            if k in forbidden_keys:
                                                print("BLOCKED_MARKET_MATRIX_INVALID")
                                                run_metrics["market_matrix_validated"] = False
                                                return 2
                
                # Matrix is valid! Populate metrics
                run_metrics["market_matrix_validated"] = True
                run_metrics["market_matrix_path"] = str(matrix_path)
                run_metrics["market_matrix_event_count"] = len(events)
                run_metrics["market_matrix_schema_version"] = matrix_data.get("schema_version", 1)
                run_metrics["market_matrix_pipeline_safe"] = matrix_data.get("pipeline_safe", True)
                run_metrics["shortlist_started"] = True

            print("Running:", " ".join(cmd))
            res = run_bounded_process(cmd, env=env, cwd=ROOT, timeout_seconds=900.0)
            stdout = redact_sensitive_text(res.stdout, env)
            stderr = redact_sensitive_text(res.stderr, env)
            if stdout:
                print(stdout, end="" if stdout.endswith("\n") else "\n")
            if stderr:
                print(stderr, end="" if stderr.endswith("\n") else "\n")
            
            # Record individual return codes
            if script_name == "discover_events.py":
                run_metrics["discovery_rc"] = res.returncode
                
                # Check for database migration errors or other crashes
                combined_output = stdout + "\n" + stderr
                if "no such column: logical_identity" in combined_output or "Migration preflight failed" in combined_output or "sqlite3" in combined_output:
                    run_metrics["db_schema_verdict"] = "FAIL"
                
                # Parse AGENT_SUMMARY
                summary_match = re.search(r"AGENT_SUMMARY:(.*)", stdout)
                if summary_match:
                    try:
                        summary_data = json.loads(summary_match.group(1).strip())
                        run_metrics["raw_discovery_count"] = summary_data.get("total_discovered", 0)
                        run_metrics["after_dedup_count"] = summary_data.get("total_after_dedup", 0)
                        
                        provider_counts = {}
                        for src_name, src_stats in summary_data.get("sources", {}).items():
                            provider_counts[src_name] = src_stats.get("events", 0)
                        run_metrics["provider_counts"] = provider_counts
                        
                        run_metrics["fallback_used"] = summary_data.get("fallback_used", False)
                        run_metrics["fallback_reason"] = summary_data.get("fallback_reason", "N/A")
                        if "db_schema_verdict" in summary_data:
                            run_metrics["db_schema_verdict"] = summary_data["db_schema_verdict"]
                    except Exception as e:
                        print(f"WARNING: failed to parse AGENT_SUMMARY from discover_events: {e}")
            elif script_name == "generate_market_matrix.py":
                run_metrics["market_matrix_rc"] = res.returncode
                if res.returncode == 0:
                    matrix_date = date or env.get("BET_PIPELINE_BETTING_DAY")
                    if matrix_date:
                        data_dir_str = env.get("BET_PIPELINE_DATA_DIR")
                        if data_dir_str:
                            m_path = Path(data_dir_str) / f"market_matrix_{matrix_date}.json"
                            if m_path.exists():
                                run_metrics["market_matrix_path"] = str(m_path)
                                try:
                                    m_data = json.loads(m_path.read_text(encoding="utf-8"))
                                    run_metrics["market_matrix_event_count"] = len(m_data.get("events", []))
                                    run_metrics["market_matrix_schema_version"] = m_data.get("schema_version", 1)
                                    run_metrics["market_matrix_pipeline_safe"] = m_data.get("pipeline_safe", True)
                                except Exception:
                                    pass
            elif script_name == "build_shortlist.py":
                run_metrics["shortlist_rc"] = res.returncode

            if res.returncode not in {0, 1}:
                print(f"Script {script_name} failed with code {res.returncode}")
                if script_name == "generate_market_matrix.py":
                    if res.returncode == 3:
                        print("BLOCKED_NO_DISCOVERY_EVENTS")
                    elif res.returncode == 4:
                        print("BLOCKED_MARKET_MATRIX_EMPTY")
                    elif res.returncode == 5:
                        print("BLOCKED_MARKET_MATRIX_INVALID")
                    elif res.returncode == 6:
                        print("FAILED_MARKET_MATRIX_GENERATION")
                return res.returncode
        return 0
    finally:
        if temp_db_path:
            try:
                os.unlink(temp_db_path)
            except OSError:
                pass


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--date", "--betting-day", dest="date", help="YYYY-MM-DD", default=None)
    p.add_argument("--run-id", dest="run_id", help="Run ID", default=None)
    p.add_argument("--runtime-mode", dest="runtime_mode", help="Runtime mode", default="DRY_RUN")
    p.add_argument("--allow-live-network", dest="allow_live_network", action="store_true", default=False)
    p.add_argument("--allow-write", dest="allow_write", action="store_true", default=False)
    p.add_argument("--dry-run", dest="dry_run", action="store_true", default=True)
    args = p.parse_args()

    child_env, runtime_path_source = resolve_child_runtime_env(
        os.environ,
        runtime_mode=args.runtime_mode if isinstance(args.runtime_mode, str) else str(args.runtime_mode),
        betting_day=args.date,
        run_id=args.run_id,
        run_root=None,
    )

    run_metrics = {
        "discovery_rc": -1,
        "market_matrix_rc": -1,
        "shortlist_rc": -1,
        "market_matrix_path": "",
        "market_matrix_event_count": 0,
        "market_matrix_schema_version": 1,
        "market_matrix_pipeline_safe": False,
        "market_matrix_validated": False,
        "shortlist_started": False,
        "raw_discovery_count": 0,
        "after_dedup_count": 0,
        "provider_counts": {},
        "fallback_used": False,
        "fallback_reason": "N/A",
        "db_schema_verdict": "PASS"
    }

    captured_stdout = io.StringIO()
    try:
        with redirect_stdout(captured_stdout):
            rc = _run_s1_scripts(
                date=args.date,
                dry_run=args.dry_run,
                allow_write=args.allow_write,
                runtime_mode=args.runtime_mode,
                allow_live_network=args.allow_live_network,
                child_env=child_env,
                run_metrics=run_metrics,
            )
    except SystemExit:
        raise
    except Exception as exc:
        print(f"S1 wrapper runtime failure: {exc}", file=sys.stderr)
        _write_terminal_evidence(
            status="FAILED",
            payload={
                **_payload(
                    rc=-1,
                    runtime_mode=args.runtime_mode,
                    dry_run=args.dry_run,
                    allow_write=args.allow_write,
                    allow_live_network=args.allow_live_network,
                    child_env=child_env,
                    runtime_path_source=runtime_path_source,
                    run_metrics=run_metrics,
                ),
                "error": str(exc),
            },
            blocked_reasons=("FAILED_UNEXPECTED_SUBPROCESS_ERROR",),
        )
        raise SystemExit(1) from exc

    output = captured_stdout.getvalue()
    _replay_output(output)

    payload = _payload(
        rc=rc,
        runtime_mode=args.runtime_mode,
        dry_run=args.dry_run,
        allow_write=args.allow_write,
        allow_live_network=args.allow_live_network,
        child_env=child_env,
        runtime_path_source=runtime_path_source,
        run_metrics=run_metrics,
    )

    if rc == 0:
        _write_terminal_evidence(status="PASS", payload=payload)
        raise SystemExit(0)

    blocked_reasons = _controlled_block_reasons(output)
    if blocked_reasons:
        _write_terminal_evidence(status="BLOCK", payload=payload, blocked_reasons=blocked_reasons)
        raise SystemExit(rc)

    # Determine exact failed reasons
    failed_reasons = ("FAILED_UNEXPECTED_SUBPROCESS_ERROR",)
    if "FAILED_MARKET_MATRIX_GENERATION" in output:
        failed_reasons = ("FAILED_MARKET_MATRIX_GENERATION",)

    _write_terminal_evidence(
        status="FAILED",
        payload=payload,
        blocked_reasons=failed_reasons,
    )
    raise SystemExit(rc)


if __name__ == "__main__":
    main()
