#!/usr/bin/env python3
"""
Mechanical qualification for .kilo/tool/bet_artifact_write.ts.

Runs the tool through a tsx-loaded TypeScript module in an isolated synthetic repo.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REPORT_DIR = PROJECT_ROOT / "reports" / "agent-config"
NODE_SCRIPT = PROJECT_ROOT / "scripts" / "test-bet-artifact-write-runner.ts"


def main() -> int:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report_path = REPORT_DIR / f"artifact-writer-qualification-{timestamp}.json"

    proc = subprocess.run(
        ["npx", "-y", "tsx", str(NODE_SCRIPT), str(PROJECT_ROOT), str(report_path)],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
    )

    sys.stdout.write(proc.stdout)
    sys.stderr.write(proc.stderr)
    if not report_path.exists():
        fallback = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "FAIL",
            "error": "runner did not produce report",
            "exit_code": proc.returncode,
            "stdout": proc.stdout[-4000:],
            "stderr": proc.stderr[-4000:],
        }
        report_path.write_text(json.dumps(fallback, indent=2), encoding="utf-8")

    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
