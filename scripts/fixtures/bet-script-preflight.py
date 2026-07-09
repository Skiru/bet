#!/usr/bin/env python3
import json
import subprocess
import sys

COMMANDS = [
    "env PYTHONPATH=src:scripts .venv/bin/python3 scripts/final_artifact_consistency_audit.py --run-root \"/tmp/full-day-session-20260709/2026-07-09/PROD_SOURCE_LIVE_20260709T140326Z\" > /tmp/s8_audit.txt 2>&1; tail -40 /tmp/s8_audit.txt",
    "grep -R -n -E \"(API_KEY|SECRET|TOKEN|PASSWORD|Bearer |sk-|odds-papi|ODDSPAPI|THE_ODDS_API|ODDS_API_IO)\" \"/tmp/full-day-session-20260709/2026-07-09/PROD_SOURCE_LIVE_20260709T140326Z\" > /tmp/s8_secret_scan.txt || true; tail -40 /tmp/s8_secret_scan.txt",
]


def summarize_output(text: str, limit: int = 1200) -> str:
    if not text:
        return ""
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[-limit:]


def main() -> int:
    results = []
    for command in COMMANDS:
        proc = subprocess.run(command, shell=True, capture_output=True, text=True)
        result = {
            "command": command,
            "exit_code": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "stdout_summary": summarize_output(proc.stdout),
            "stderr_summary": summarize_output(proc.stderr),
        }
        results.append(result)
        if proc.returncode != 0:
            print(json.dumps({"status": "failed", "results": results}))
            return proc.returncode
    print(json.dumps({"status": "success", "results": results}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
