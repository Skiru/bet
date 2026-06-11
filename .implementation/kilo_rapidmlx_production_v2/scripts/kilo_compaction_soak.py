#!/usr/bin/env python3
"""Drive a continued Kilo session toward compaction without tool noise."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import signal
import subprocess
from pathlib import Path
from typing import Any

BAD = re.compile(r"Compaction exhausted|ContextOverflowError|context still exceeds|out of memory|traceback", re.I)


def run(command: list[str], cwd: Path, timeout: int) -> tuple[int, str]:
    process = subprocess.Popen(command, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True)
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


def payload(turn: int, chars: int) -> str:
    pieces: list[str] = []
    index = 0
    while sum(map(len, pieces)) < chars:
        digest = hashlib.sha256(f"turn={turn};index={index}".encode()).hexdigest()
        pieces.append(f"fact_{turn}_{index}_{digest} ")
        index += 1
    return "".join(pieces)[:chars]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", default=".")
    parser.add_argument("--turns", type=int, default=10)
    parser.add_argument("--payload-chars", type=int, default=7000)
    parser.add_argument("--timeout", type=int, default=1200)
    parser.add_argument("--report", default="reports/kilo-compaction-soak.json")
    args = parser.parse_args()

    root = Path(args.project).resolve()
    log_dir = root / "reports" / "kilo-compaction-logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    steps: list[dict[str, Any]] = []
    sid: str | None = None

    for turn in range(1, args.turns + 1):
        marker = f"COMPACTION_TURN_{turn}_OK"
        prompt = (
            "Treat the following as opaque retained facts. Do not summarize or repeat them. "
            f"Reply with exactly {marker}.\n\n" + payload(turn, args.payload_chars)
        )
        command = ["kilo", "run", "--format", "json"]
        if sid:
            command += ["--session", sid]
        else:
            command += ["--agent", "rapid-smoke"]
        command.append(prompt)
        code, output = run(command, root, args.timeout)
        if not sid:
            sid = session_id(output)
        bad = bool(BAD.search(output))
        marker_ok = marker in output
        steps.append({"turn": turn, "exit": code, "bad": bad, "marker_ok": marker_ok})
        (log_dir / f"{turn:02d}.jsonl").write_text(output)
        if code != 0 or bad or not marker_ok or not sid:
            break

    export_path = log_dir / "session-export-sanitized.json"
    compaction_observed: bool | None = None
    if sid:
        code, exported = run(["kilo", "export", sid, "--sanitize"], root, 180)
        export_path.write_text(exported)
        if code == 0:
            lowered = exported.lower()
            compaction_observed = any(term in lowered for term in ("session.compacted", '"compaction"', '"summary"'))

    passed = len(steps) == args.turns and all(step["exit"] == 0 and not step["bad"] and step["marker_ok"] for step in steps)
    report = {
        "passed": passed,
        "session": sid,
        "turns_requested": args.turns,
        "payload_chars_per_turn": args.payload_chars,
        "compaction_observed_in_export": compaction_observed,
        "note": "The export heuristic may be null/false even when internal compaction occurred; the hard gate is no overflow and successful continuation.",
        "steps": steps,
    }
    path = root / args.report
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
