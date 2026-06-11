#!/usr/bin/env python3
"""End-to-end test for the project Kilo context-guard plugin."""
from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import time
from pathlib import Path
from typing import Any

BAD = re.compile(r"Compaction exhausted|ContextOverflowError|context still exceeds|out of memory|traceback", re.I)


def run(command: list[str], cwd: Path, timeout: int) -> tuple[int, str]:
    process = subprocess.Popen(
        command,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    try:
        output, _ = process.communicate(timeout=timeout)
        return process.returncode, output
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            output, _ = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            output, _ = process.communicate()
        return 124, output + f"\n[TIMEOUT] exceeded {timeout} seconds\n"


def walk(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def session_id(text: str) -> str | None:
    for line in text.splitlines():
        try:
            item = json.loads(line)
        except Exception:
            continue
        for record in walk(item):
            for key in ("sessionID", "sessionId", "session_id", "id"):
                value = record.get(key)
                if isinstance(value, str) and (key != "id" or value.startswith("ses_")):
                    return value
    match = re.search(r"\b(ses_[A-Za-z0-9_-]+)\b", text)
    return match.group(1) if match else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", default=".")
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--report", default="reports/kilo-context-guard.json")
    args = parser.parse_args()

    root = Path(args.project).resolve()
    artifact_dir = root / ".kilo" / "artifacts" / "tool-output"
    audit_log = root / ".kilo" / "runtime" / "context-guard.jsonl"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    before = {path.resolve() for path in artifact_dir.glob("*.txt")}
    started = time.time()

    first_code, first_output = run(
        ["kilo", "run", "--format", "json", "--agent", "context-guard-smoke", "RUN_CONTEXT_GUARD"],
        root,
        args.timeout,
    )
    sid = session_id(first_output)
    new_artifacts = [
        path for path in artifact_dir.glob("*.txt")
        if path.resolve() not in before and path.stat().st_mtime >= started - 2
    ]
    artifact_ok = any(path.stat().st_size > 12 * 1024 for path in new_artifacts)
    audit_text = audit_log.read_text(errors="replace") if audit_log.exists() else ""
    audit_ok = "tool-output-truncated" in audit_text
    marker_ok = "CONTEXT_GUARD_OK" in first_output
    bad_first = bool(BAD.search(first_output))

    second_code = 1
    second_output = "session id unavailable"
    recovery_ok = False
    if sid:
        second_code, second_output = run(
            ["kilo", "run", "--format", "json", "--session", sid, "Reply with exactly CONTEXT_GUARD_RECOVERY_OK."],
            root,
            args.timeout,
        )
        recovery_ok = "CONTEXT_GUARD_RECOVERY_OK" in second_output and not BAD.search(second_output)

    passed = all([
        first_code == 0,
        marker_ok,
        not bad_first,
        bool(sid),
        artifact_ok,
        audit_ok,
        second_code == 0,
        recovery_ok,
    ])
    report = {
        "passed": passed,
        "session": sid,
        "first_exit": first_code,
        "marker_ok": marker_ok,
        "artifact_ok": artifact_ok,
        "artifacts": [str(path.relative_to(root)) for path in new_artifacts],
        "audit_ok": audit_ok,
        "recovery_exit": second_code,
        "recovery_ok": recovery_ok,
    }
    report_path = root / args.report
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    (report_path.parent / "kilo-context-guard-first.jsonl").write_text(first_output)
    (report_path.parent / "kilo-context-guard-recovery.jsonl").write_text(second_output)
    print(json.dumps(report, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
