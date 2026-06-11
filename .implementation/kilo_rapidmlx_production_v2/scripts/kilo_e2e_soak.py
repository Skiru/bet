#!/usr/bin/env python3
"""Kilo CLI end-to-end harness for provider resolution and session continuity."""
from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
from pathlib import Path
from typing import Any

BAD = re.compile(
    r"Compaction exhausted|ContextOverflowError|context still exceeds|out of memory|traceback",
    re.IGNORECASE,
)


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
        return 124, output + f"\n[TIMEOUT] command exceeded {timeout} seconds\n"


def walk(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def extract_session_id(text: str) -> str | None:
    for line in text.splitlines():
        try:
            item = json.loads(line)
        except Exception:
            continue
        for record in walk(item):
            for key in ("sessionID", "sessionId", "session_id", "id"):
                value = record.get(key)
                if isinstance(value, str) and (
                    key != "id" or value.startswith("ses_")
                ):
                    return value
    match = re.search(r"\b(ses_[A-Za-z0-9_-]+)\b", text)
    return match.group(1) if match else None


def finish(
    root: Path,
    report_path: str,
    steps: list[dict[str, Any]],
    session_id: str | None,
) -> int:
    passed = all(step["code"] == 0 and not step["bad"] for step in steps)
    report = {
        "passed": passed,
        "session": session_id,
        "steps": steps,
        "note": (
            "This validates Kilo CLI transport and session continuity. "
            "Run a phase-sized workload separately."
        ),
    }
    path = root / report_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0 if passed else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", default=".")
    parser.add_argument("--turns", type=int, default=12)
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--report", default="reports/kilo-e2e-soak.json")
    args = parser.parse_args()

    root = Path(args.project).resolve()
    logs = root / "reports" / "kilo-e2e-logs"
    logs.mkdir(parents=True, exist_ok=True)
    steps: list[dict[str, Any]] = []

    code, output = run(["kilo", "config", "check"], root, args.timeout)
    steps.append({"name": "config-check", "code": code, "bad": bool(BAD.search(output))})
    (logs / "00-config-check.log").write_text(output)
    if code != 0:
        return finish(root, args.report, steps, None)

    first_prompt = "Reply with exactly KILO_E2E_1. Do not use tools."
    code, output = run(
        [
            "kilo",
            "run",
            "--format",
            "json",
            "--agent",
            "rapid-smoke",
            first_prompt,
        ],
        root,
        args.timeout,
    )
    session_id = extract_session_id(output)
    steps.append(
        {
            "name": "initial",
            "code": code,
            "bad": bool(BAD.search(output)),
            "session": session_id,
        }
    )
    (logs / "01-initial.jsonl").write_text(output)
    if code != 0 or BAD.search(output) or not session_id:
        return finish(root, args.report, steps, session_id)

    for number in range(2, args.turns + 1):
        prompt = f"Reply with exactly KILO_E2E_{number}. Do not use tools."
        code, output = run(
            [
                "kilo",
                "run",
                "--format",
                "json",
                "--session",
                session_id,
                prompt,
            ],
            root,
            args.timeout,
        )
        bad = bool(BAD.search(output))
        steps.append({"name": f"turn-{number}", "code": code, "bad": bad})
        (logs / f"{number:02d}-turn.jsonl").write_text(output)
        if code != 0 or bad:
            break

    return finish(root, args.report, steps, session_id)


if __name__ == "__main__":
    raise SystemExit(main())
