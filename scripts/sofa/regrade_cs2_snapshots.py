#!/usr/bin/env python3
"""Remove CS2 graded sides that were priced from a snapshot Superbet had
already replaced - the one-off correction for settles before 2026-09-30.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/regrade_cs2_snapshots.py \\
        --from 2026-09-28 --to 2026-09-29 [--dry-run]

Until 2026-09-30 cs2.latest_pre_kickoff merged sides across snapshots, so a
line Superbet took down before the start (a recentred rounds ladder) was
still graded at the price it had hours earlier. The function now takes the
last pre-start snapshot whole. CS2_SETTLE never re-grades a SETTLED series,
so the days settled before the fix keep those rows; this removes them.

Offline: it reads snapshots.jsonl and settled.json only - no bridge. A graded
row stays when its side is in the event's last pre-start snapshot at the same
price; otherwise it and its partner go (a line is graded whole or not at
all). settled.json is backed up once as settled.pre_regrade.json and the
event gets `regraded_2026_09_30: <n removed>`. Idempotent. Exit 0; 2 on a
bad file.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import cs2  # noqa: E402
from bet.sofa import sport_coupon as sc  # noqa: E402
from bet.sofa.config import SofaConfig  # noqa: E402
from scripts.sofa.settle_sport_coupon import days  # noqa: E402

MARK = "regraded_2026_09_30"
BACKUP = "settled.pre_regrade.json"


def _line_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return (row["family"], row["map_nr"], row["subject"], row["line"])


def regrade_event(ev: dict[str, Any], latest: Any) -> tuple[list[dict[str, Any]], int]:
    """(rows kept, rows removed) for one settled event."""
    rows = ev.get("graded") or []
    stale_lines = set()
    for r in rows:
        side = None if latest is None else latest.sides.get((*_line_key(r), r["side"]))
        if side is None or abs(side.odds - float(r["odds"])) > 1e-9:
            stale_lines.add(_line_key(r))
    kept = [r for r in rows if _line_key(r) not in stale_lines]
    return kept, len(rows) - len(kept)


def regrade_day(runs_dir: str, date: str, dry_run: bool) -> dict[str, int]:
    d = cs2.cs2_day_dir(runs_dir, date)
    settled_path = d / cs2.SETTLED_FILE
    if not settled_path.exists():
        return {"events": 0, "removed": 0}
    doc = json.loads(settled_path.read_text(encoding="utf-8"))
    latest = cs2.latest_pre_kickoff(sc.load_snapshots(d / cs2.SNAPSHOTS_FILE))
    removed = events = 0
    for eid, ev in (doc.get("events") or {}).items():
        if ev.get("state") != "SETTLED" or not ev.get("graded"):
            continue
        kept, n = regrade_event(ev, latest.get(eid))
        if n:
            events += 1
            removed += n
            ev["graded"] = kept
            ev[MARK] = int(ev.get(MARK, 0)) + n
    if removed and not dry_run:
        backup = d / BACKUP
        if not backup.exists():
            shutil.copy2(settled_path, backup)
        cs2.write_atomic(settled_path, json.dumps(doc, ensure_ascii=False, indent=2))
    return {"events": events, "removed": removed}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--from", dest="start", required=True)
    parser.add_argument("--to", dest="end", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    runs_dir = SofaConfig.from_env().runs_dir
    try:
        for date in days(args.start, args.end):
            res = regrade_day(runs_dir, date, args.dry_run)
            verb = "would remove" if args.dry_run else "removed"
            print(
                f"{date}: {verb} {res['removed']} stale-price sides "
                f"in {res['events']} series"
            )
    except (OSError, ValueError, KeyError) as exc:
        print(f"FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
