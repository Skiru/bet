#!/usr/bin/env python3
"""Audit 2026-10-23 P9: hockey / basketball games missing from one team's
list. Read-only (sport_history.missing_sides; nothing is written).

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_audit1023_p9_both_sides.py \\
        [--db-path data/sofa.db] [--days 400] [--event 16546356]

Prints the missing sides per sport (all, and with a start in the last
`--days`), and whether `--event` is among them.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from collections import Counter
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import sport_history as sh  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db-path", default=str(_REPO / "data" / "sofa.db"))
    ap.add_argument("--days", type=int, default=400)
    ap.add_argument("--event", type=int, default=16546356)
    args = ap.parse_args(argv)
    con = sqlite3.connect(f"file:{args.db_path}?mode=ro", uri=True)
    cut = int(time.time()) - args.days * 86400
    sides: Counter[tuple[str, bool]] = Counter()
    for slug in sh.BOTH_SIDES_SLUGS:
        for m in sh.missing_sides(con, [slug]):
            sides[(slug, (m.start_ts or 0) >= cut)] += 1
            if m.event_id == args.event:
                print(f"event {m.event_id}: team {m.team_id} missing "
                      f"(start {m.start_ts})")
    for slug in sh.BOTH_SIDES_SLUGS:
        total = sides[(slug, True)] + sides[(slug, False)]
        print(f"{slug}: {total} missing sides, {sides[(slug, True)]} with a "
              f"start in the last {args.days} days")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
