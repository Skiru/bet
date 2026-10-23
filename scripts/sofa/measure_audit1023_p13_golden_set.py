#!/usr/bin/env python3
"""Audit 2026-10-23 P13: volleyball matches followed by a golden set. Read-only.

Counts, on the cached listed events, the volleyball games Sofascore printed
"AET" / "AGS" (shadow.GOLDEN_SET_DESCRIPTIONS): how many the settlement grades
now (shadow.build_result, the correctness fix) and how many the score-model
history reads under epochs.VB_GOLDEN_SET (score_model.parse_event
golden_set). Then lists every SHADOW_SETTLE record (runs/sofa/shadow/
volleyball/<d>/settled.json) whose Sofascore id is such a game, with its
state - the rows the fix would regrade (re-run
`scripts/sofa/settle_shadow.py --sport volleyball --date <d>` for a listed
day; nothing is regraded here).

    PYTHONPATH=src:. .venv/bin/python \\
        scripts/sofa/measure_audit1023_p13_golden_set.py \\
        [--db-path data/sofa.db] [--runs-dir runs/sofa]
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa.score_model import parse_event  # noqa: E402
from bet.sofa.shadow import GOLDEN_SET_DESCRIPTIONS, SPORTS, build_result  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db-path", default=str(_REPO / "data" / "sofa.db"))
    ap.add_argument("--runs-dir", default=str(_REPO / "runs" / "sofa"))
    args = ap.parse_args(argv)
    vb = SPORTS["volleyball"]
    con = sqlite3.connect(f"file:{args.db_path}?mode=ro", uri=True)
    marks = ",".join("?" * len(GOLDEN_SET_DESCRIPTIONS))
    events: dict[int, dict[str, Any]] = {}
    for eid, raw in con.execute(
            "SELECT event_id, event_json FROM sofa_listed_event "
            "WHERE sport = 'volleyball' "
            f"AND json_extract(event_json, '$.status.description') IN ({marks})",
            sorted(GOLDEN_SET_DESCRIPTIONS)):
        events[int(eid)] = json.loads(raw)
    tally: Counter[str] = Counter()
    for e in events.values():
        tally[f"status {(e.get('status') or {}).get('description')}"] += 1
        tally["settle grades"] += build_result(
            e, vb, True, allow_final_only=True) is not None
        tally["history reads, switch off"] += parse_event(e, vb) is not None
        tally["history reads, switch on"] += parse_event(
            e, vb, golden_set=True) is not None
    print(f"golden-set games in the cache: {len(events)}")
    for key, n in sorted(tally.items()):
        print(f"  {key}: {n}")
    hits = []
    for path in sorted(Path(args.runs_dir, "shadow", "volleyball").glob(
            "*/settled.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        for sb_id, rec in (doc.get("events") or {}).items():
            if rec.get("sofascore_event_id") in events:
                hits.append((path.parent.name, sb_id, rec.get("sofascore_event_id"),
                             rec.get("state"), rec.get("status")))
    print(f"SHADOW_SETTLE records on such a game: {len(hits)}")
    for hit in hits:
        print("  " + " ".join(str(x) for x in hit))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
