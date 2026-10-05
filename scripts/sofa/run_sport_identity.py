#!/usr/bin/env python3
"""SPORT_IDENTITY - the Sofascore event of every hockey, basketball,
volleyball and CS2 Superbet event of the day, before it starts (plan
2026-10-05, F1; bet.sofa.sport_identity).

    .venv/bin/python scripts/sofa/ensure_bridge.py
    PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_sport_identity.py \\
        --date 2026-10-06 [--sport hockey --sport cs2]

Needs the bridge: one `team/<id>/events/next/0` request per match (cached
with the events TTL), once a day, after the day's SHADOW and CS2 snapshots.
A refusal stops the run (no retry); a re-run asks only for the events not
yet identified - an IDENTIFIED record is pinned and never asked again.

Writes runs/sofa/<date>/sport_fixtures.json; the team ids come from the
database read-only. Exit: 0 OK, 1 PARTIAL (an event not identified, or the
bridge refused), 2 FAILED (no snapshot of any sport).
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import sport_identity as si  # noqa: E402
from bet.sofa.atomic import write_atomic  # noqa: E402
from bet.sofa.config import SofaConfig  # noqa: E402
from bet.sofa.stage import set_stage  # noqa: E402
from bet.sofa.timeutil import frozen_clock_refusal, now  # noqa: E402


def run(date: str, sports: list[str], runs_dir: str, client: si.ListingClient,
        cache: si.ListingCache | None, conn: sqlite3.Connection) -> tuple[
            dict[str, Any], int]:
    at = now()
    out = Path(runs_dir) / date / si.FIXTURES_FILE
    prior = si.load_fixtures(out)
    pinned = {str(r["superbet_event_id"]): r
              for r in (prior or {}).get("fixtures") or []
              if r.get("status") == si.IDENTIFIED}
    events: list[si.BoardEvent] = []
    for sport in sports:
        events += si.board_events(runs_dir, sport, date, at)
    resolver = si.TeamResolver(conn, int(at.timestamp()))
    records, summary = si.identify(events, client, cache, resolver.team_id, at,
                                   date, pinned)
    # Sports not asked this run keep their earlier records.
    kept = [r for r in (prior or {}).get("fixtures") or []
            if r.get("sport") not in sports]
    doc = {
        "created_at_utc": si.iso(at),
        "date": date,
        "day_window_utc": [si.iso(t) for t in si.day_window(date)],
        # Every sport with records in the file, not only this run's: a
        # `--sport hockey` re-run must not make SPORT_CONFIDENCE read the
        # other sports as never identified (review 2026-10-05).
        **summary,
        "sports_run": sorted(
            set(sports) | set((prior or {}).get("sports_run") or [])),
        **(
            {"sports": {**((prior or {}).get("sports") or {}),
                        **(summary.get("sports") or {})}}
            if isinstance(summary.get("sports"), dict) else {}
        ),
        "fixtures": kept + records,
    }
    write_atomic(out, json.dumps(doc, indent=1, ensure_ascii=False) + "\n")
    if not events:
        return doc, 2
    partial = summary["aborted"] is not None or any(
        r["status"] != si.IDENTIFIED for r in records)
    return doc, 1 if partial else 0


def main() -> int:
    set_stage("SPORT_IDENTITY")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--date", required=True)
    ap.add_argument("--sport", action="append", choices=list(si.SPORT_KEYS))
    args = ap.parse_args()
    config = SofaConfig.from_env()
    frozen = frozen_clock_refusal(config.runs_dir)
    if frozen:
        print(frozen, file=sys.stderr)
        return 2
    from bet.sofa.cache import SofaCache
    from bet.sofa.client import SofascoreClient

    client = SofascoreClient(config)
    cache = SofaCache(config)
    conn = sqlite3.connect(f"file:{config.db_path}?mode=ro", uri=True)
    try:
        doc, code = run(args.date, list(args.sport or si.SPORT_KEYS),
                        config.runs_dir, client, cache, conn)
    finally:
        conn.close()
    print("SOFA_SUMMARY: " + json.dumps({
        "stage": "SPORT_IDENTITY",
        "verdict": {0: "OK", 1: "PARTIAL", 2: "FAILED"}[code],
        "sports": doc["sports"], "aborted": doc["aborted"],
        "output_path": str(Path(config.runs_dir) / args.date / si.FIXTURES_FILE),
    }), flush=True)
    return code


if __name__ == "__main__":
    sys.exit(main())
