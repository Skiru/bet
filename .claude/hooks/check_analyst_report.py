#!/usr/bin/env python3
"""PostToolUse hook (Bash): an analyst report just written is checked for
depth (`bet.sofa.report_check`). Findings go back to the agent on stderr with
exit 2, so it rewrites the report in the same turn; anything else exits 0 and
says nothing. Never blocks a command that does not write a report."""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path(__file__).resolve().parents[2])
sys.path.insert(0, str(ROOT / "src"))
WRITE = re.compile(
    r"(?:cat\s*>|>\s*|tee\s+)\s*['\"]?([^\s'\"<>|;&]*_analiza_[^\s'\"<>|;&]*\.md)"
)


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except ValueError:
        return 0
    if event.get("tool_name") != "Bash":
        return 0
    command = str((event.get("tool_input") or {}).get("command") or "")
    paths = WRITE.findall(command)
    if not paths:
        return 0
    try:
        from bet.sofa.report_check import findings, report_day
    except ImportError:
        return 0
    problems: list[str] = []
    for raw in dict.fromkeys(paths):
        path = (
            Path(raw)
            if Path(raw).is_absolute()
            else Path(event.get("cwd") or ROOT) / raw
        )
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        found = findings(text, report_day(path.name))
        if found:
            problems.append(f"{raw}:")
            problems += [f"  - {x}" for x in found]
    if not problems:
        return 0
    print(
        "Raport analityka za płytki (sofa-analysis-core, references/context-pass.md) "
        "- popraw go i zapisz ponownie:\n" + "\n".join(problems),
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
