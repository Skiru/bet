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
REPORT = r"([^\s'\"<>|;&()]*_(?:analiza|weryfikacja)[^\s'\"<>|;&()]*\.md)"
# a shell redirect / tee, or a python write (`open(...)`, `Path(...).write_text`)
WRITE = re.compile(
    r"(?:cat\s*>|>\s*|tee\s+)\s*['\"]?" + REPORT
    + r"|(?:open|Path)\(\s*[rf]?['\"]" + REPORT
)


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except ValueError:
        return 0
    if event.get("tool_name") != "Bash":
        return 0
    command = str((event.get("tool_input") or {}).get("command") or "")
    paths = [a or b for a, b in WRITE.findall(command)]
    if not paths:
        return 0
    try:
        from bet.sofa.report_check import findings, report_day, report_kind
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
        found = findings(text, report_day(path.name), **report_kind(path.name))
        if found:
            problems.append(f"{raw}:")
            problems += [f"  - {x}" for x in found]
    if not problems:
        return 0
    verifier = any("_weryfikacja" in p for p in paths)
    contract = ("Raport weryfikatora (sofa-verifier.md, Output contract)" if verifier
                else "Raport analityka za płytki (sofa-analysis-core, "
                "references/context-pass.md)")
    print(
        f"{contract} - popraw go i zapisz ponownie pod tą samą ścieżką:\n"
        + "\n".join(problems),
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
