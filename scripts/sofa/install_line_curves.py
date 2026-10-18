#!/usr/bin/env python3
"""Install the per-line history curves (bet.sofa.line_curves) fitted by
`fit_confidence.py --line-curves-only` into the football / tennis calibration.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/install_line_curves.py \\
        --staged data/refit_line_curves_<d>/sofa_confidence_calibration.json \\
        (--dry-run | --confirm) [--backup-dir config/backup_<d>_line_curves]

The staged file is a copy of the installed calibration with its per-line
section refitted; the install takes ONLY `by_market_direction_line` and
`line_curves_fitted_from` from it and refuses (exit 2, nothing written) when
any other top-level key of the staged file differs from the installed one
(the curves were then fitted from another installed file), when the section
is empty, when a staged `.next.json` exists beside the installed file (a day
from its `effective_from` would read that file instead), or when the backup
directory exists.

The section is read only under epochs.LINE_CURVES_FROM_UTC, so installing it
changes nothing a day before the switch prints; from the switch on it does,
so an install needs the operator's go (CLAUDE.md "Changing the pipeline" 4).

--confirm: the installed file is copied to --backup-dir first, written
atomically, then `tests/sofa` run; on a failure it is restored (exit 2).
--dry-run prints the plan. Exit 0 installed / planned, 2 refused or failed.
"""

from __future__ import annotations

import argparse
import json
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO / "src"), str(_REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import line_curves as lc  # noqa: E402
from bet.sofa.atomic import write_atomic  # noqa: E402
from bet.sofa.confidence import NEXT_CALIBRATION_NAME  # noqa: E402
from bet.sofa.config import config_path  # noqa: E402

TAKEN = (lc.SECTION, lc.FITTED_FROM)
DEFAULT_TESTS = f"{sys.executable} -m pytest tests/sofa -q"


def indent_of(text: str) -> int:
    """The installed file's indentation (a refit writes 1, a hand-kept file
    2), so an install rewrites only the keys it takes."""
    second = text.split("\n", 2)[1] if "\n" in text else ""
    return max(1, len(second) - len(second.lstrip(" ")))


def plan(installed: dict[str, Any], staged: dict[str, Any]
         ) -> tuple[list[str], dict[str, Any]]:
    """(refusals, the file to write)."""
    refusals = []
    others = (set(installed) | set(staged)) - set(TAKEN)
    differ = sorted(k for k in others if installed.get(k) != staged.get(k))
    if differ:
        refusals.append("the staged file differs from the installed one outside "
                        f"the per-line section: {', '.join(differ)}")
    section = staged.get(lc.SECTION)
    if not isinstance(section, dict) or not section:
        refusals.append(f"the staged file has no {lc.SECTION}")
    out = dict(installed)
    for key in TAKEN:
        if key in staged:
            out[key] = staged[key]
    return refusals, out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--staged", required=True)
    ap.add_argument("--target", default=None,
                    help="the installed calibration (default: config's)")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--confirm", action="store_true")
    ap.add_argument("--backup-dir", default=None)
    ap.add_argument("--tests", default=DEFAULT_TESTS)
    args = ap.parse_args(argv)
    target = Path(args.target) if args.target else config_path(
        "sofa_confidence_calibration.json")
    installed_text = target.read_text(encoding="utf-8")
    installed = json.loads(installed_text)
    staged = json.loads(Path(args.staged).read_text(encoding="utf-8"))
    refusals, out = plan(installed, staged)
    if target.with_name(NEXT_CALIBRATION_NAME).exists():
        refusals.append(f"a staged {NEXT_CALIBRATION_NAME} exists beside {target}")
    section = out.get(lc.SECTION) or {}
    summary = {"keys": len(section), "lines": sum(len(v) for v in section.values()),
               "missing_keys": sorted(lc.load_keys() - set(section))}
    if refusals:
        for r in refusals:
            print(f"REFUSED: {r}", file=sys.stderr)
        return 2
    if args.dry_run:
        print(json.dumps({"plan": "install", "target": str(target), **summary}))
        return 0
    backup = Path(args.backup_dir) if args.backup_dir else (
        target.parent / "backup_line_curves")
    if backup.exists():
        print(f"REFUSED: backup {backup} exists", file=sys.stderr)
        return 2
    backup.mkdir(parents=True)
    shutil.copy2(target, backup / target.name)
    write_atomic(target, json.dumps(out, indent=indent_of(installed_text)) + "\n")
    proc = subprocess.run(shlex.split(args.tests), cwd=_REPO)
    if proc.returncode != 0:
        shutil.copy2(backup / target.name, target)
        print(f"tests failed (exit {proc.returncode}): restored from {backup}",
              file=sys.stderr)
        return 2
    print(json.dumps({"installed": str(target), "backup": str(backup), **summary}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
