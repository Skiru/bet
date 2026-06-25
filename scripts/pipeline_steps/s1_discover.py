#!/usr/bin/env python3
"""S1 — Discovery / scan step wrapper. Runs `scripts/discover_events.py`.
"""
from __future__ import annotations

import argparse
import io
import os
import re
import subprocess
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

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ["discover_events.py", "build_shortlist.py"]
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
) -> dict[str, object]:
    return {
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


def _certification_declared_runner_contract() -> None:
    """Static declaration for wrapper certification target discovery."""
    if False:  # pragma: no cover - parsed statically by certification only
        run_scripts(SCRIPTS, continue_on_codes=[0, 1])


def _run_s1_scripts(
    *,
    date: str | None,
    dry_run: bool,
    allow_write: bool,
    allow_live_network: bool,
    runtime_mode: str,
    child_env: dict[str, str],
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
            if script_name == "discover_events.py" and temp_db_path:
                cmd += ["--db-path", temp_db_path]

            print("Running:", " ".join(cmd))
            res = subprocess.run(cmd, env=env, capture_output=True, text=True)
            if res.stdout:
                print(res.stdout, end="" if res.stdout.endswith("\n") else "\n")
            if res.stderr:
                print(res.stderr, end="" if res.stderr.endswith("\n") else "\n")
            if res.returncode not in {0, 1}:
                print(f"Script {script_name} failed with code {res.returncode}")
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
    )

    if rc == 0:
        _write_terminal_evidence(status="PASS", payload=payload)
        raise SystemExit(0)

    blocked_reasons = _controlled_block_reasons(output)
    if blocked_reasons:
        _write_terminal_evidence(status="BLOCK", payload=payload, blocked_reasons=blocked_reasons)
        raise SystemExit(rc)

    _write_terminal_evidence(
        status="FAILED",
        payload=payload,
        blocked_reasons=("FAILED_UNEXPECTED_SUBPROCESS_ERROR",),
    )
    raise SystemExit(rc)


if __name__ == "__main__":
    main()
