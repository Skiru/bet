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

# Sandbox paths keys
RUNTIME_PATH_KEYS = (
    "BET_PIPELINE_RUN_ROOT",
    "BET_PIPELINE_DATA_DIR",
    "BET_PIPELINE_COUPON_DIR",
    "BET_PIPELINE_ARTIFACT_DIR",
)


class ScriptInvocation:
    """Typed invocation contract for safe script execution without monkeypatching."""
    def __init__(
        self,
        script: str,
        argv: list[str] | None = None,
        timeout_seconds: float | None = None,
        idempotent: bool = True,
        expected_exit_codes: set[int] | None = None,
    ):
        self.script = script
        self.argv = argv or []
        self.timeout_seconds = timeout_seconds
        self.idempotent = idempotent
        self.expected_exit_codes = expected_exit_codes or {0}


def _venv_python() -> str:
    return sys.executable


def _init_temp_db(db_path: str) -> None:
    """Initialize schema in a temp DB for dry-run subprocesses."""
    from bet.db.connection import get_db
    from bet.db.schema import init_db

    with get_db(db_path) as conn:
        init_db(conn)


def _has_runtime_path_env(env: dict[str, str]) -> bool:
    return all(env.get(key) for key in RUNTIME_PATH_KEYS)


def _repo_reports_root() -> Path:
    return ROOT / "reports"


def resolve_child_runtime_env(
    parent_env: dict[str, str],
    *,
    runtime_mode: RuntimeMode | str,
    betting_day: str | None,
    run_id: str | None,
    run_root: Path | str | None,
) -> tuple[dict[str, str], str]:
    if isinstance(runtime_mode, str):
        try:
            runtime_mode = RuntimeMode(runtime_mode.upper())
        except ValueError:
            runtime_mode = RuntimeMode.DRY_RUN

    env = parent_env.copy()
    runtime_path_source = "unmanaged"

    if runtime_mode != RuntimeMode.PRODUCTION:
        if _has_runtime_path_env(parent_env):
            runtime_path_source = "orchestrator_inherited_sandbox"
            for key in RUNTIME_PATH_KEYS:
                env[key] = parent_env[key]
        else:
            resolved_betting_day = betting_day or parent_env.get("BET_PIPELINE_BETTING_DAY") or "default_day"
            resolved_run_id = run_id or parent_env.get("BET_PIPELINE_RUN_ID")
            resolved_run_root = Path(run_root) if run_root else None
            sandbox_env = build_runtime_env(runtime_mode, resolved_betting_day, resolved_run_id, resolved_run_root)
            env.update(sandbox_env)
            runtime_path_source = "runner_built_sandbox"

        if betting_day:
            env["BET_PIPELINE_BETTING_DAY"] = betting_day
        if run_id:
            env["BET_PIPELINE_RUN_ID"] = run_id
        env["BET_PIPELINE_RUNTIME_MODE"] = runtime_mode.value
        env["DRY_RUN"] = "1"

        parent_run_root = parent_env.get("BET_PIPELINE_RUN_ROOT", "")
        child_run_root = env.get("BET_PIPELINE_RUN_ROOT", "")
        child_run_root_resolved = str(Path(child_run_root).expanduser().resolve()) if child_run_root else ""
        repo_reports_root = str(_repo_reports_root().resolve())
        if parent_run_root.startswith("/tmp") and child_run_root_resolved.startswith(repo_reports_root):
            raise RuntimeError(
                "Non-production child runtime sandbox fell back to repo-local reports despite inherited /tmp BET_PIPELINE_RUN_ROOT"
            )

        for key in RUNTIME_PATH_KEYS:
            if env.get(key):
                Path(env[key]).mkdir(parents=True, exist_ok=True)

    return env, runtime_path_source


def run_scripts(
    scripts: Iterable[str | ScriptInvocation],
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
    extra_args: list[str] | None = None,
) -> int:
    """Run one or more script paths (relative to repo root `scripts/`).

    - Accepts either raw string script names or ScriptInvocation objects.
    - When `dry_run` is True and `allow_write` False, `DATABASE_URL` will be
      temporarily set to a temp file DB to avoid persisting changes.
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
        s_name = script.script if isinstance(script, ScriptInvocation) else script
        name = Path(s_name).name
        if name in [
            "discover_events.py",
            "fetch_odds_multi.py",
            "settle_on_finish.py",
            "tipster_aggregator.py",
        ]:
            is_live_target = True
            break

    # If is_live_target, check live-network safety
    if is_live_target:
        if runtime_mode == RuntimeMode.CERTIFICATION:
            print("BLOCKED_LIVE_NETWORK_ACK_MISSING")
            return 5
        elif runtime_mode == RuntimeMode.LIVE_SHADOW:
            if not allow_live_network:
                print("BLOCKED_LIVE_NETWORK_ACK_MISSING")
                return 5
            live_ack = env.get("BET_PIPELINE_LIVE_ACK", "")
            if live_ack != "I_UNDERSTAND_LIVE_PROVIDER_CALLS":
                print("BLOCKED_LIVE_NETWORK_ACK_MISSING")
                return 5

    # Adjust write flags and mode
    if runtime_mode == RuntimeMode.PRODUCTION:
        allow_write = True
        dry_run = False
    else:
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

    if runtime_mode != RuntimeMode.PRODUCTION:
        try:
            env, _ = resolve_child_runtime_env(
                env,
                runtime_mode=runtime_mode,
                betting_day=betting_day or date,
                run_id=run_id,
                run_root=run_root,
            )
        except RuntimeError as exc:
            print(f"BLOCKED_RUNTIME_PATH_INHERITANCE_LOST: {exc}")
            return 6

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
            if isinstance(script, ScriptInvocation):
                script_name = script.script
                argv = list(script.argv)
                timeout = script.timeout_seconds
                expected_codes = script.expected_exit_codes
            else:
                script_name = script
                argv = []
                if date:
                    argv += [date_arg, date]
                timeout = None
                expected_codes = set(continue_on_codes or [0])

            script_path = ROOT / "scripts" / script_name
            if not script_path.exists():
                print(f"Script not found: {script_path}")
                return 2
            cmd = [python, str(script_path)] + argv
            if extra_args:
                cmd += extra_args
            print("Running:", " ".join(cmd))
            kwargs = {}
            if timeout is not None:
                kwargs["timeout"] = timeout
            res = subprocess.run(cmd, env=env, capture_output=True, text=True, **kwargs)
            if res.returncode not in expected_codes:
                if res.stdout:
                    print(res.stdout)
                if res.stderr:
                    print(res.stderr)

                if not isinstance(script, ScriptInvocation) and date and ("unrecognized arguments" in (res.stderr or "").lower() or "usage:" in (res.stderr or "").lower() or "error:" in (res.stderr or "").lower()):
                    print(f"Retrying {script_name} without date flag to accommodate CLI differences")
                    cmd2 = [python, str(script_path)]
                    if extra_args:
                        cmd2 += extra_args
                    print("Running:", " ".join(cmd2))
                    res2 = subprocess.run(cmd2, env=env, capture_output=True, text=True)
                    if res2.returncode not in expected_codes:
                        if res2.stdout:
                            print(res2.stdout)
                        if res2.stderr:
                            print(res2.stderr)
                        print(f"Script {script_name} failed with code {res2.returncode}")
                        return res2.returncode
                    else:
                        continue

                print(f"Script {script_name} failed with code {res.returncode}")
                return res.returncode
            else:
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
