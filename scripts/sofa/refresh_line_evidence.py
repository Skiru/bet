#!/usr/bin/env python3
"""Refresh config/sofa_superbet_line_evidence.json between days - one command.

The morning after D-1 is settled (SETTLE, SHADOW_SETTLE, CS2_SETTLE), before
D's first build: the settled Superbet lines of D-1 join the evidence every
leg's confidence is read through (bet.sofa.line_evidence). Two steps:

1. fit_sport_confidence.py --sport <s> --before <d> --dry-run --rows-out <dir>
   for hockey, basketball, volleyball and CS2, in parallel (~15 min a sport):
   only for its `<sport>_superbet_settled.jsonl` rows (the model's p on every
   settled Superbet line, the model built on the line's own day). --dry-run:
   the installed sport curves are NOT touched - a curve refit is a separate,
   deliberate step (prepare_refit / fit_sport_confidence without --dry-run).
2. fit_line_evidence.py --before <d> --sport-rows-dir <dir>, read against the
   curves the day <d> reads (sport_confidence.calibration_path_for).

The rows are kept in data/line_evidence/rows_before_<d> (the evidence file
names that directory, so the fit can be reproduced).

Usage:
    PYTHONPATH=src:. .venv/bin/python scripts/sofa/refresh_line_evidence.py \\
        --before <d> [--dry-run] [--skip-sport-rows]
Exit 0 written, 1 a sport's row fit failed (evidence still written from the
others' rows plus the earlier day's rows of that sport), 2 a crash.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
SPORTS = ("hockey", "basketball", "volleyball", "cs2")
ROWS_ROOT = _REPO / "data" / "line_evidence"


def rows_dir(before: str) -> Path:
    return ROWS_ROOT / f"rows_before_{before}"


def previous_rows(before: str) -> Path | None:
    """The newest earlier rows directory (a sport whose fit fails keeps it)."""
    if not ROWS_ROOT.exists():
        return None
    older = sorted(p for p in ROWS_ROOT.iterdir()
                   if p.is_dir() and p.name.startswith("rows_before_")
                   and p.name < f"rows_before_{before}")
    return older[-1] if older else None


def stash_rows(out: Path, sports: tuple[str, ...] = SPORTS) -> dict[str, Path]:
    """Move this directory's rows of an earlier run aside (`.prev`), so a fit
    that fails can put them back instead of falling to an older day's."""
    kept: dict[str, Path] = {}
    for sport in sports:
        rows = out / f"{sport}_superbet_settled.jsonl"
        if rows.exists():
            kept[sport] = rows.with_suffix(".jsonl.prev")
            rows.replace(kept[sport])
    return kept


def restore_rows(
    out: Path, kept: dict[str, Path], only: tuple[str, ...] | None = None
) -> None:
    for sport, prev in kept.items():
        if only is not None and sport not in only:
            continue
        rows = out / f"{sport}_superbet_settled.jsonl"
        rows.unlink(missing_ok=True)
        prev.replace(rows)


def fit_commands(before: str, out: Path) -> list[list[str]]:
    return [[sys.executable, "scripts/sofa/fit_sport_confidence.py", "--sport", s,
             "--before", before, "--dry-run", "--rows-out", str(out),
             "--out", str(out / f"cal_{s}.json")] for s in SPORTS]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--before", required=True,
                    help="the day about to be built (its D-1 must be settled)")
    ap.add_argument("--dry-run", action="store_true",
                    help="fit and print, write no evidence file")
    ap.add_argument("--skip-sport-rows", action="store_true",
                    help="reuse data/line_evidence/rows_before_<d> as it is")
    args = ap.parse_args()
    out = rows_dir(args.before)
    out.mkdir(parents=True, exist_ok=True)
    failed: list[str] = []
    if not args.skip_sport_rows:
        kept = stash_rows(out)  # a file of an earlier run today is not this run's
        logs = {s: (out / f"log_{s}.txt").open("w") for s in SPORTS}
        try:
            procs = [(cmd[3], subprocess.Popen(
                cmd, cwd=_REPO, stdout=logs[cmd[3]], stderr=subprocess.STDOUT))
                for cmd in fit_commands(args.before, out)]
            codes = [(sport, proc.wait()) for sport, proc in procs]
        finally:
            for fh in logs.values():
                fh.close()
        for sport, code in codes:
            rows = out / f"{sport}_superbet_settled.jsonl"
            state = "present" if rows.exists() else "MISSING"
            print(f"{sport}: exit {code}, rows {state}", flush=True)
            if code != 0 or not rows.exists():
                failed.append(sport)
                rows.unlink(missing_ok=True)  # never a partial file
                if sport in kept:  # this run's earlier rows first
                    restore_rows(out, kept, (sport,))
                    print(f"  {sport}: kept this directory's earlier rows", flush=True)
                    continue
                prev = previous_rows(args.before)
                if prev is not None and (prev / rows.name).exists():
                    shutil.copy(prev / rows.name, rows)
                    print(f"  {sport}: kept {prev.name}/{rows.name}", flush=True)
    cmd = [sys.executable, "scripts/sofa/fit_line_evidence.py", "--before",
           args.before, "--sport-rows-dir", str(out.relative_to(_REPO))]
    if args.dry_run:
        cmd.append("--dry-run")
    done = subprocess.run(cmd, cwd=_REPO)
    if done.returncode != 0:
        return 2
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
