#!/usr/bin/env python3
"""STAKES_LISTINGS - refresh the team listings a national group's stakes
flag reads, before the coupon is assembled (bet.sofa.stakes_listings;
operator 2026-11-19; display only).

For the day's not-yet-started men's national group fixtures
(stakes_groups.NATIONAL) asks page 0 of each group team's `last` and `next`
listing through the bridge (both sides, then the group's other teams, at
most GROUP_MAX_TEAMS a group), skipping a page fetched within FRESH_H hours.
No such fixture = no client, zero requests. A 403 / 429 or the breaker
stops it; the coupon still builds. Run by rebuild_day.py after
FIXTURE_CHECK (rebuild_plan) or by hand:

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/refresh_stakes_listings.py \\
        --date <d> [--dry-run]

Writes runs/sofa/<d>/stakes_listings.json (pages asked, their answer, each
run's counts). Exit 0 OK / nothing to do, 1 PARTIAL (stopped or errors),
2 no 02_fixtures.json.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import epochs  # noqa: E402
from bet.sofa import stakes_listings as sl  # noqa: E402
from bet.sofa.atomic import write_atomic  # noqa: E402
from bet.sofa.config import SofaConfig  # noqa: E402
from bet.sofa.stage import set_stage  # noqa: E402
from bet.sofa.timeutil import frozen_clock_refusal, now  # noqa: E402

STAGE = "STAKES_LISTINGS"


def _summary(verdict: str, metrics: dict[str, object], out: Path) -> None:
    print("SOFA_SUMMARY: " + json.dumps({
        "stage": STAGE, "verdict": verdict, "metrics": metrics,
        "output_path": str(out)}), flush=True)


def main() -> int:
    set_stage(STAGE)
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--date", required=True)
    ap.add_argument("--dry-run", action="store_true",
                    help="list the fixtures in scope; ask nothing")
    args = ap.parse_args()
    config = SofaConfig.from_env()
    frozen = frozen_clock_refusal(config.runs_dir)
    if frozen:
        print(frozen, file=sys.stderr)
        return 2
    run = Path(config.runs_dir) / args.date
    out = run / sl.RECORD_FILE
    fx_path = run / "02_fixtures.json"
    if not fx_path.exists():
        print(f"{fx_path} missing", file=sys.stderr)
        return 2
    at = now()
    if not epochs.stakes_groups(args.date, at):
        _summary("SKIPPED", {"reason": "epochs.STAKES_GROUPS_FROM_UTC off",
                             "requests": 0}, out)
        return 0
    fixtures = json.loads(fx_path.read_text(encoding="utf-8"))
    scope = sl.open_national(fixtures, at)
    if not scope or args.dry_run:
        _summary("OK", {"fixtures_in_scope": len(scope), "requests": 0,
                        "dry_run": args.dry_run,
                        "events": [f["sofascore_event_id"] for f in scope]}, out)
        return 0

    from bet.sofa.cache import SofaCache
    from bet.sofa.client import SofascoreClient, breaker_tripped

    cache = SofaCache(config)
    client = SofascoreClient(config)
    record = sl.load_record(run)
    con = sqlite3.connect(f"file:{config.db_path}?mode=ro", uri=True, timeout=30.0)
    try:
        refresher = sl.Refresher(
            con,
            lambda team, kind, page: client.entity_events(
                team, "next" if kind == "next" else "last", page),
            cache.save_entity_events, at,
            record["pages"], tripped=lambda: breaker_tripped(client))
        result = refresher.run(fixtures)
    finally:
        con.close()
    metrics = result.metrics()
    record["runs"].append({"at_utc": at.isoformat().replace("+00:00", "Z"),
                           **metrics})
    write_atomic(out, json.dumps(record, indent=1, ensure_ascii=False) + "\n")
    print(f"{STAGE}: {result.requests} requests ({len(result.asked)} pages: "
          + ", ".join(result.asked[:40])
          + (" ..." if len(result.asked) > 40 else "") + ")", file=sys.stderr)
    partial = bool(result.stopped or result.errors)
    _summary("PARTIAL" if partial else "OK", metrics, out)
    return 1 if partial else 0


if __name__ == "__main__":
    sys.exit(main())
