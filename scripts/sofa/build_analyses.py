#!/usr/bin/env python3
"""Rebuild a day's analyses.json from its analyst and verifier reports on disk.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/build_analyses.py --date <d> \\
        [--runs-dir <dir>] [--dry-run]

`merge_reads.py` records each report it merges; this rebuilds the store
from every `<d>_analiza_*.md` / `<d>_weryfikacja*.md` (oldest first), for a
day merged before the store existed or after a report was edited by hand
(`bet.sofa.analyses`). Display only: the HTML view and the PDF's appendix
read it at their next render (`build_coupon_html.py --date <d>` re-renders
the page alone). Prints per report the sections found, then the matches.
Exit 0 written (or dry run), 2 when the day's directory is missing.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(_ROOT / "src"), str(_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import analyses  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--date", required=True)
    ap.add_argument("--runs-dir", default=os.environ.get("SOFA_RUNS_DIR", "runs/sofa"))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    run = Path(args.runs_dir) / args.date
    if not run.is_dir():
        print(f"build_analyses: no {run}", file=sys.stderr)
        return 2
    names = analyses.coupon_match_names(run)
    for path in analyses.report_files(run, args.date):
        n = len(analyses.split_sections(path.read_text(encoding="utf-8"), names))
        print(f"{path.name}: {n} match sections" if n else
              f"{path.name}: NO_SECTIONS")
    store, n = analyses.rebuild(run, args.date, names)
    print(f"{n} sections, {len(store['events'])} matches")
    if args.dry_run:
        print("dry run: nothing written")
    else:
        print(f"-> {analyses.save(run, store)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
