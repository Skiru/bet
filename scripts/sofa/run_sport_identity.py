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
yet identified - an IDENTIFIED record is pinned and never asked again, and
an event that has started keeps its last (pre-start) record, unasked: the
`events/next` listing no longer shows a game under way.

Writes runs/sofa/<date>/sport_fixtures.json; the team ids come from the
database read-only. After the file, the entity map learns from the
IDENTIFIED records (bet.sofa.entity_map: names confirmed by their own name,
the opponent-rule sides as NEEDS_ALIAS candidates, the tournament map) - a
write of its own; its learned rows are read from epochs.ENTITY_MAP_FROM_UTC.
Exit: 0 OK, 1 PARTIAL (an event not identified, or the bridge refused),
2 FAILED (no snapshot of any sport). With --if-snapshot a date that has
no snapshot yet is NOTHING_TO_DO, exit 0, and no file is written: the
daily loops ask D+1 after every snapshot, long before D+1 has one, and
logged that as FAILED every half hour (2026-10-12).
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

from bet.sofa import entity_map, epochs  # noqa: E402
from bet.sofa import sport_identity as si  # noqa: E402
from bet.sofa.atomic import write_atomic  # noqa: E402
from bet.sofa.config import SofaConfig  # noqa: E402
from bet.sofa.stage import set_stage  # noqa: E402
from bet.sofa.timeutil import frozen_clock_refusal, now  # noqa: E402

NOTHING_TO_DO = 3  # internal: --if-snapshot and no snapshot (exit 0)


def learn(db_path: str, doc: dict[str, Any], sports: list[str]) -> dict[str, Any]:
    """The entity map learns from this run's IDENTIFIED records (K1;
    entity_map.learn_records, once per Sofascore event). A write failure is
    reported and never fails the stage: the records are already written."""
    from bet.sofa.db import get_connection

    records = [r for r in doc.get("fixtures") or [] if r.get("sport") in sports]
    try:
        decisions = entity_map.load_manual()
    except ValueError as exc:  # a person's typo must be heard, not crash the stage
        print(f"ENTITY_ALIASES_INVALID: {exc}", file=sys.stderr)
        decisions = {"aliases": [], "rejected": []}
    try:
        with get_connection(db_path) as conn:
            manual = entity_map.sync_manual(conn, decisions, si.iso(now()))
            counts: dict[str, Any] = entity_map.learn_records(conn, records,
                                                              si.iso(now()))
            conn.commit()
        return {**counts, "manual": manual}
    except sqlite3.Error as exc:
        print(f"ENTITY_MAP_LEARN_FAILED: {exc}", file=sys.stderr)
        return {"error": str(exc)}


def run(date: str, sports: list[str], runs_dir: str, client: si.ListingClient,
        cache: si.ListingCache | None, conn: sqlite3.Connection,
        if_snapshot: bool = False) -> tuple[dict[str, Any], int]:
    at = now()
    out = Path(runs_dir) / date / si.FIXTURES_FILE
    prior = si.load_fixtures(out)
    # Every earlier record: an IDENTIFIED one is pinned, any other is kept
    # once its event has started (identify, FROZEN_AT_START).
    pinned = {str(r["superbet_event_id"]): r
              for r in (prior or {}).get("fixtures") or []}
    events: list[si.BoardEvent] = []
    for sport in sports:
        events += si.board_events(runs_dir, sport, date, at)
    if not events and if_snapshot:
        return {"sports": (prior or {}).get("sports") or {},
                "aborted": None}, NOTHING_TO_DO
    resolver = si.TeamResolver(conn, int(at.timestamp()),
                               learned=entity_map.learned_reads(date, at))
    records, summary = si.identify(events, client, cache, resolver.team_id, at,
                                   date, pinned, resolver.query_id,
                                   day_anchor=epochs.day_anchor(date, at))
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
            # Only the sports asked replace their counts: identify() counts
            # every sport, and an unasked one read 0 events (the CS2 loop
            # zeroed hockey's line every half hour; 2026-10-12).
            {"sports": {**((prior or {}).get("sports") or {}),
                        **{sp: c for sp, c in (summary.get("sports") or {}).items()
                           if sp in sports}}}
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
    ap.add_argument(
        "--if-snapshot", action="store_true",
        help="no snapshot of the date yet: NOTHING_TO_DO, exit 0, nothing "
        "written (the loops' D+1 run)")
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
                        config.runs_dir, client, cache, conn, args.if_snapshot)
    finally:
        conn.close()
    learned = (learn(config.db_path, doc, list(args.sport or si.SPORT_KEYS))
               if code != NOTHING_TO_DO else {})
    print("SOFA_SUMMARY: " + json.dumps({
        "stage": "SPORT_IDENTITY",
        "verdict": {0: "OK", 1: "PARTIAL", 2: "FAILED",
                    NOTHING_TO_DO: "NOTHING_TO_DO"}[code],
        "sports": doc["sports"], "aborted": doc["aborted"],
        "entity_map": learned,
        "output_path": str(Path(config.runs_dir) / args.date / si.FIXTURES_FILE),
    }), flush=True)
    return 0 if code == NOTHING_TO_DO else code


if __name__ == "__main__":
    sys.exit(main())
