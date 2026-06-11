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


def run_scripts(scripts: Iterable[str], date: str | None = None, dry_run: bool = True, allow_write: bool = False, date_arg: str = "--date", continue_on_codes: Iterable[int] | None = None) -> int:
    """Run one or more script paths (relative to repo root `scripts/`).

    - `date` is passed as `--date` to the script if provided.
    - When `dry_run` is True and `allow_write` False, `DATABASE_URL` will be
      temporarily set to a temp file DB to avoid persisting changes.
    - `continue_on_codes`: Exit codes that should NOT stop the sequence (default: [0]).
      Use [0, 1] to allow PARTIAL verdicts to continue.
    Returns the subprocess return code (0 for success).
    """
    if continue_on_codes is None:
        continue_on_codes = [0]
    env = os.environ.copy()
    # Allow an environment override to force DB writes for full pipeline runs.
    force_allow = env.get("FORCE_ALLOW_WRITE", "").lower() in ("1", "true", "yes")
    if force_allow:
        allow_write = True
        dry_run = False
        print("⚠️ FORCE_ALLOW_WRITE is set: enabling DB writes and disabling dry-run")

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
                    res2 = subprocess.run(cmd2, env=env)
                    if res2.returncode not in continue_on_codes:
                        print(f"Script {script} failed with code {res2.returncode}")
                        return res2.returncode
                    else:
                        continue

                print(f"Script {script} failed with code {res.returncode}")
                return res.returncode
        return 0
    finally:
        if temp_db_path:
            try:
                os.unlink(temp_db_path)
            except OSError:
                pass
