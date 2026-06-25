"""Helper to run existing pipeline scripts in a safe, consistent way.

Wrappers use this helper to run the canonical scripts while enforcing a
`--dry-run` default that points `DATABASE_URL` to a temp file DB. Set
`--allow-write` to permit writing to the configured `DATABASE_URL`.

Dry-run creates a temp DB with schema initialized so subprocess scripts
that need persistent schema across multiple calls work correctly.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[2]

# Ensure src/ is importable for bet package imports
src_path = str(ROOT / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from bet.pipeline.runtime_modes import (
    RuntimeMode,
    LIVE_ACK_KEY,
    LIVE_ACK_VALUE,
    WRITE_ACK_KEY,
    WRITE_ACK_VALUE,
)
from bet.pipeline.runtime_paths import build_runtime_env


def _venv_python() -> str:
    return sys.executable


def _init_temp_db(db_path: str) -> None:
    """Initialize schema in a temp DB for dry-run subprocesses."""
    import sqlite3
    schema_path = ROOT / "src" / "bet" / "db" / "schema.sql"
    if schema_path.exists():
        conn = sqlite3.connect(db_path)
        try:
            conn.executescript(schema_path.read_text(encoding="utf-8"))
        finally:
            conn.close()


def run_scripts(
    scripts: Iterable[str],
    date: str | None = None,
    dry_run: bool = True,
    allow_write: bool = False,
    date_arg: str = "--date",
    continue_on_codes: Iterable[int] | None = None,
    write_ack_env_key: str = "BET_PIPELINE_WRITE_ACK",
    runtime_mode: str | RuntimeMode | None = None,
    betting_day: str | None = None,
    run_id: str | None = None,
    allow_live_network: bool = False,
    run_root: Path | str | None = None,
) -> int:
    """Run one or more script paths (relative to repo root `scripts/`).

    - `date` is passed as `date_arg` to the script if provided.
    - When `dry_run` is True and `allow_write` False, `DATABASE_URL` will be
      temporarily set to a temp file DB to avoid persisting changes.
    - `continue_on_codes`: Exit codes that should NOT stop the sequence (default: [0]).
      Use [0, 1] to allow PARTIAL verdicts to continue.
    Returns the subprocess return code (0 for success).
    """
    if continue_on_codes is None:
        continue_on_codes = [0]
    env = os.environ.copy()

    # Determine/Validate runtime mode
    if runtime_mode is None:
        if allow_write:
            runtime_mode = RuntimeMode.PRODUCTION
        else:
            runtime_mode = RuntimeMode.DRY_RUN
    elif isinstance(runtime_mode, str):
        try:
            runtime_mode = RuntimeMode(runtime_mode.upper())
        except ValueError:
            runtime_mode = RuntimeMode.DRY_RUN

    # Check for live-target wrappers
    is_live_target = False
    for script in scripts:
        s_name = Path(script).name
        if s_name in [
            "discover_events.py",
            "fetch_odds_multi.py",
            "settle_on_finish.py",
            "tipster_aggregator.py",
            "validate_betclic_markets.py",
        ]:
            is_live_target = True
            break

    # If is_live_target, check live-network safety
    if is_live_target:
        if not allow_live_network:
            print("BLOCKED_LIVE_NETWORK_ACK_MISSING")
            return 5
        live_ack = env.get("BET_PIPELINE_LIVE_ACK", "")
        if live_ack != "I_UNDERSTAND_LIVE_PROVIDER_CALLS":
            print("BLOCKED_LIVE_NETWORK_ACK_MISSING")
            return 5

    # If runtime_mode is CERTIFICATION, we must never run live provider calls
    if is_live_target and runtime_mode == RuntimeMode.CERTIFICATION:
        print("BLOCKED_LIVE_NETWORK_ACK_MISSING")
        return 5

    # Adjust write flags and mode
    if runtime_mode == RuntimeMode.PRODUCTION:
        allow_write = True
        dry_run = False
    else:
        # Non-production modes must use sandboxed/dry-run settings
        allow_write = False
        dry_run = True

    # Check write acknowledgements for write mode
    write_ack = env.get(write_ack_env_key, "")
    force_allow = env.get("FORCE_ALLOW_WRITE", "").lower() in ("1", "true", "yes")

    if force_allow:
        if not (allow_write and write_ack == "I_UNDERSTAND_PRODUCTION_WRITE"):
            print("BLOCKED_FORCE_ALLOW_WRITE_UNSAFE")
            return 4
        dry_run = False
        allow_write = True
    elif allow_write:
        if write_ack != "I_UNDERSTAND_PRODUCTION_WRITE":
            print("BLOCKED_WRITE_ACK_MISSING")
            return 3
        dry_run = False

    # Inject sandboxed paths for non-production modes
    if runtime_mode != RuntimeMode.PRODUCTION:
        b_day = betting_day or date or "default_day"
        r_root = Path(run_root) if run_root else None
        sandbox_env = build_runtime_env(runtime_mode, b_day, run_id, r_root)
        env.update(sandbox_env)
        # Create directories
        for key in ("BET_PIPELINE_RUN_ROOT", "BET_PIPELINE_DATA_DIR", "BET_PIPELINE_COUPON_DIR", "BET_PIPELINE_ARTIFACT_DIR"):
            if key in env:
                Path(env[key]).mkdir(parents=True, exist_ok=True)

    temp_db_path = None
    try:
        if dry_run and not allow_write:
            fd, temp_db_path = tempfile.mkstemp(suffix=".db", prefix="bet_dryrun_")
            os.close(fd)
            _init_temp_db(temp_db_path)
            env["DATABASE_URL"] = f"sqlite:///{temp_db_path}"
            env["DRY_RUN"] = "1"
        python = _venv_python()
        for script in scripts:
            script_path = ROOT / "scripts" / script
            if not script_path.exists():
                print(f"Script not found: {script_path}")
                return 2
            cmd = [python, str(script_path)]
            if date:
                cmd += [date_arg, date]
            print("Running:", " ".join(cmd))
            res = subprocess.run(cmd, env=env, capture_output=True, text=True)
            if res.returncode not in continue_on_codes:
                if res.stdout:
                    print(res.stdout)
                if res.stderr:
                    print(res.stderr)

                stderr = (res.stderr or "").lower()
                if date and ("unrecognized arguments" in stderr or "usage:" in stderr or "error:" in stderr):
                    print(f"Retrying {script} without date flag to accommodate CLI differences")
                    cmd2 = [python, str(script_path)]
                    print("Running:", " ".join(cmd2))
                    # Note: Original code used subprocess.run(cmd2, env=env) without capture_output, returning its returncode or continuing.
                    # To remain fully compliant with exit code propagation and safety:
                    res2 = subprocess.run(cmd2, env=env, capture_output=True, text=True)
                    if res2.returncode not in continue_on_codes:
                        if res2.stdout:
                            print(res2.stdout)
                        if res2.stderr:
                            print(res2.stderr)
                        print(f"Script {script} failed with code {res2.returncode}")
                        return res2.returncode
                    else:
                        continue

                print(f"Script {script} failed with code {res.returncode}")
                return res.returncode
            else:
                # Still output stdout and stderr even if successful, for machine readability or logs
                if res.stdout:
                    print(res.stdout)
                if res.stderr:
                    print(res.stderr)
        return 0
    finally:
        if temp_db_path:
            try:
                os.unlink(temp_db_path)
            except OSError:
                pass
