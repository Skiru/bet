#!/usr/bin/env python3
"""Render a deterministic agent execution prompt from a work order."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from bet.pipeline.agent_execution_prompts import (
    load_work_order,
    render_agent_artifact_skeleton,
    render_agent_execution_prompt,
    validate_rendered_prompt,
)
from bet.pipeline.run_evidence import write_json_atomic


def _path_is_forbidden(path: Path) -> bool:
    resolved = path.expanduser().resolve()
    repo_root = Path(__file__).resolve().parents[2]
    forbidden_roots = (
        repo_root / "betting" / "data",
        repo_root / "betting" / "coupons",
        repo_root / "reports",
    )
    return any(root == resolved or root in resolved.parents for root in forbidden_roots)


def _write_text(path: Path, content: str) -> None:
    if _path_is_forbidden(path):
        raise ValueError(f"Refusing to write renderer output to forbidden path: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)


def main() -> int:
    parser = argparse.ArgumentParser(description="Render an agent execution prompt from a work order.")
    parser.add_argument("--work-order", required=True, help="Path to work order JSON")
    parser.add_argument("--output", help="Optional path to write prompt markdown/text")
    parser.add_argument("--print", action="store_true", dest="print_prompt", help="Print prompt to stdout")
    parser.add_argument("--skeleton-json", help="Optional path to write a safe artifact skeleton JSON")
    args = parser.parse_args()

    try:
        work_order = load_work_order(Path(args.work_order))
        prompt = render_agent_execution_prompt(work_order)
        errors = validate_rendered_prompt(prompt, work_order)
        if errors:
            raise ValueError("Rendered prompt validation failed: " + "; ".join(errors))

        if args.output:
            _write_text(Path(args.output), prompt)

        if args.skeleton_json:
            skeleton_path = Path(args.skeleton_json)
            if _path_is_forbidden(skeleton_path):
                raise ValueError(f"Refusing to write artifact skeleton to forbidden path: {skeleton_path}")
            write_json_atomic(skeleton_path, render_agent_artifact_skeleton(work_order))

        if args.print_prompt:
            sys.stdout.write(prompt)

        return 0
    except Exception as exc:  # pragma: no cover - covered through CLI assertions
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
