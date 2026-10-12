#!/usr/bin/env python3
"""Bring the measured sports' game history up to date (bet.sofa.sport_history).

Asks Sofascore `/event/{id}` for every hockey / basketball / volleyball game of
the last --days that should have ended and that the history does not hold as
finished, and indexes the answers - the score model of SPORT_CONFIDENCE and the
sport fits read them from then on. Every morning before `refresh_line_evidence`
(which runs it first) and before a build; needs the bridge.

    .venv/bin/python scripts/sofa/ensure_bridge.py
    PYTHONPATH=src:. .venv/bin/python scripts/sofa/refresh_sport_history.py \\
        [--days 14] [--sport hockey ...] [--max-minutes 7] [--dry-run]

Same client, token bucket, breaker and bridge as the pipeline; a refusal stops
the run (resumable: a game stored as finished is never asked again).
Exit: 0 OK, 1 PARTIAL (deadline or the bridge refused; a 404 is an answer),
2 FAILED (nothing could be asked).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import timedelta
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import sport_history as sh  # noqa: E402
from bet.sofa.config import SofaConfig  # noqa: E402
from bet.sofa.db import get_connection  # noqa: E402
from bet.sofa.stage import set_stage  # noqa: E402
from bet.sofa.timeutil import frozen_clock_refusal, now  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--days", type=int, default=sh.DAYS)
    ap.add_argument("--sport", action="append", choices=sorted(sh.SLUGS),
                    help="repeatable; default every sport with a score model")
    ap.add_argument("--min-age-h", type=float, default=sh.MIN_AGE_H)
    ap.add_argument("--max-minutes", type=float, default=7.0)
    ap.add_argument("--dry-run", action="store_true",
                    help="count the candidates; ask nothing, write nothing")
    args = ap.parse_args()
    config = SofaConfig.from_env()
    refusal = frozen_clock_refusal(config.runs_dir)
    if refusal:
        print(refusal, file=sys.stderr)
        return 2
    set_stage("SPORT_HISTORY")
    sports = args.sport or sorted(sh.SLUGS)
    at = now()
    hi_ts = int((at - timedelta(hours=args.min_age_h)).timestamp())
    lo_ts = int((at - timedelta(days=args.days)).timestamp())
    dates = [(at - timedelta(days=i)).strftime("%Y-%m-%d")
             for i in range(args.days + 1)]
    pinned = {sh.SLUGS[s]: sh.pinned_ids(config.runs_dir, s, dates) for s in sports}
    conn = get_connection(config.db_path)
    try:
        found = sh.candidates(conn, [sh.SLUGS[s] for s in sports], lo_ts, hi_ts,
                              pinned)
        summary: dict[str, object] = {
            "stage": "SPORT_HISTORY", "days": args.days,
            "candidates": {k: len(v) for k, v in found.ids.items()},
            "already_finished": found.already_finished,
        }
        if args.dry_run:
            summary["verdict"] = "OK"
            summary["dry_run"] = True
            print("SOFA_SUMMARY: " + json.dumps(summary))
            return 0
        from bet.sofa.client import SofascoreClient  # needs the bridge

        client = SofascoreClient(config)
        stop_at = time.monotonic() + 60.0 * args.max_minutes
        ids = sorted(set().union(*found.ids.values())) if found.ids else []
        result = sh.refresh(conn, ids, client.event,
                            lambda: now().isoformat(),
                            lambda: time.monotonic() > stop_at)
    finally:
        conn.close()
    # A 404 is an answer (a game Sofascore deleted, often from a stale `next`
    # page); only a stop - deadline, breaker, bridge - leaves work undone.
    partial = bool(result.stopped)
    verdict = "FAILED" if (result.asked == 0 and ids) else (
        "PARTIAL" if partial else "OK")
    summary.update({"verdict": verdict, "asked": result.asked,
                    "finished": result.finished,
                    "not_finished": result.not_finished,
                    "missing": result.missing, "stopped": result.stopped})
    print("SOFA_SUMMARY: " + json.dumps(summary))
    return {"OK": 0, "PARTIAL": 1, "FAILED": 2}[verdict]


if __name__ == "__main__":
    sys.exit(main())
