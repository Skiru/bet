"""Helper to run existing pipeline scripts in a safe, consistent way.

Wrappers use this helper to run the canonical scripts while enforcing a
`--dry-run` default that points `DATABASE_URL` to an in-memory DB. Set
`--allow-write` to permit writing to the configured `DATABASE_URL`.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[2]


def _venv_python() -> str:
    # Prefer current interpreter
    return sys.executable


def run_scripts(scripts: Iterable[str], date: str | None = None, dry_run: bool = True, allow_write: bool = False, date_arg: str = "--date") -> int:
    """Run one or more script paths (relative to repo root `scripts/`).

    - `date` is passed as `--date` to the script if provided.
    - When `dry_run` is True and `allow_write` False, `DATABASE_URL` will be
      temporarily set to an in-memory sqlite DB to avoid persisting changes.
    Returns the subprocess return code (0 for success).
    """
    env = os.environ.copy()
    if dry_run and not allow_write:
        env["DATABASE_URL"] = "sqlite:///:memory:"
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
        # Capture output to detect common CLI errors (e.g., unknown args)
        res = subprocess.run(cmd, env=env, capture_output=True, text=True)
        if res.returncode != 0:
            # Print captured output for debugging
            if res.stdout:
                print(res.stdout)
            if res.stderr:
                print(res.stderr)

            # If the script failed due to unrecognized args and we passed a date,
            # try rerunning without the date flag for robustness.
            stderr = (res.stderr or "").lower()
            if date and ("unrecognized arguments" in stderr or "usage:" in stderr or "error:" in stderr):
                print(f"Retrying {script} without date flag to accommodate CLI differences")
                cmd2 = [python, str(script_path)]
                print("Running:", " ".join(cmd2))
                res2 = subprocess.run(cmd2, env=env)
                if res2.returncode != 0:
                    print(f"Script {script} failed with code {res2.returncode}")
                    return res2.returncode
                else:
                    continue

            print(f"Script {script} failed with code {res.returncode}")
            return res.returncode
    return 0
