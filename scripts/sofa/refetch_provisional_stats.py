"""Re-ask Sofascore for cached /statistics that are its early snapshot.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/refetch_provisional_stats.py
    PYTHONPATH=src:. .venv/bin/python scripts/sofa/refetch_provisional_stats.py --apply

The first is a dry run (counts, asks nothing); --apply asks and writes.

A one-off repair for rows cached before bet.sofa.cache learned to treat an
early snapshot as provisional (2026-09-28). The rule is the cache's own
``is_provisional``: fetched within 72 h of kick-off, nothing or cards only,
the match at least 4 days old. From now on SAMPLES and SETTLE re-ask such a
row by themselves when they meet it; this reaches the ones nobody meets.

/statistics is asked, and for football /incidents too: the card points are
read from the incidents, and an early incidents payload is as stale as the
early statistics. Every row about to be overwritten is first written to
runs/sofa/refetch_provisional_<ts>.json, so the repair can be undone. It goes
through the bridge like everything else and stops when the circuit opens.

Exit 0 OK, 1 PARTIAL (some asks failed or the circuit opened), 2 FAILED.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bet.sofa.cache import SofaCache, _all_period_keys, is_provisional
from bet.sofa.config import SofaConfig
from bet.sofa.errors import CircuitOpenError, ProviderError


def kickoffs(conn: sqlite3.Connection) -> dict[int, tuple[int, str | None]]:
    """Event id -> (startTimestamp, sport slug), from every cached listing."""
    out: dict[int, tuple[int, str | None]] = {}
    for (events_json,) in conn.execute("SELECT events_json FROM sofa_entity_events"):
        try:
            events = json.loads(events_json).get("events", [])
        except ValueError:
            continue
        for event in events:
            eid, start = event.get("id"), event.get("startTimestamp")
            if isinstance(eid, int) and isinstance(start, (int, float)):
                category = (event.get("tournament") or {}).get("category") or {}
                sport = (category.get("sport") or {}).get("slug")
                out.setdefault(
                    eid, (int(start), sport if isinstance(sport, str) else None)
                )
    return out


def candidates(
    conn: sqlite3.Connection,
    starts: dict[int, tuple[int, str | None]],
    at: datetime,
    only: set[int] | None = None,
) -> list[dict[str, Any]]:
    """Provisional rows - or, with ``only``, exactly those events."""
    rows = []
    for eid, fetched_at, stats, incidents in conn.execute(
        "SELECT sofascore_event_id, fetched_at, statistics_json, incidents_json"
        " FROM sofa_event_stats WHERE status_type = 'finished'"
    ):
        known = starts.get(int(eid))
        if known is None:
            continue
        start, sport = known
        wanted = (
            int(eid) in only
            if only is not None
            else is_provisional(stats, fetched_at, start, at)
        )
        if wanted:
            rows.append(
                {
                    "event_id": int(eid),
                    "sport": sport,
                    "fetched_at": fetched_at,
                    "kickoff_ts": start,
                    "statistics_json": stats,
                    "incidents_json": incidents,
                }
            )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--apply", action="store_true", help="ask and write; default dry"
    )
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--from-backup",
        help="re-ask exactly the events of an earlier backup file (its rows were"
        " repaired before incidents were re-asked too)",
    )
    args = parser.parse_args()

    config = SofaConfig.from_env()
    at = datetime.now(UTC)
    try:
        conn = sqlite3.connect(f"file:{config.db_path}?mode=ro", uri=True)
        only = (
            {int(r["event_id"]) for r in json.loads(Path(args.from_backup).read_text())}
            if args.from_backup
            else None
        )
        todo = candidates(conn, kickoffs(conn), at, only)
        conn.close()
    except sqlite3.Error as exc:
        print(f"FAILED reading the cache: {exc}", file=sys.stderr)
        return 2
    todo.sort(key=lambda r: -r["kickoff_ts"])  # newest first: the samples need them
    if args.limit is not None:
        todo = todo[: args.limit]

    summary: dict[str, Any] = {"candidates": len(todo), "applied": args.apply}
    if not args.apply:
        summary["by_kind"] = dict(
            Counter("empty" if not r["statistics_json"] else "cards_only" for r in todo)
        )
        print(
            "SOFA_SUMMARY: "
            + json.dumps(
                {"stage": "REFETCH_PROVISIONAL", "verdict": "OK", "metrics": summary}
            )
        )
        return 0

    backup = Path(config.runs_dir) / f"refetch_provisional_{at:%Y%m%dT%H%M%SZ}.json"
    backup.parent.mkdir(parents=True, exist_ok=True)
    backup.write_text(json.dumps(todo) + "\n")

    from bet.sofa.client import SofascoreClient

    client = SofascoreClient(config)
    cache = SofaCache(config)
    outcome: Counter[str] = Counter()
    circuit_open = False

    # The incidents are part of the early snapshot too: on 2026-09-28, 35 of 46
    # re-asked football matches had different card points than the cached
    # incidents gave (17059933: 0-0 cached, 3-3 in fact). Statistics and
    # incidents are asked together, or card points mix two moments.
    def ask(row: dict[str, Any]) -> tuple[dict[str, Any], Any, Any, str | None]:
        try:
            stats = client.event_statistics(row["event_id"])
            incidents = (
                client.event_incidents(row["event_id"])
                if row["sport"] == "football"
                else None
            )
            return row, stats, incidents, None
        except CircuitOpenError:
            return row, None, None, "circuit"
        except ProviderError:
            return row, None, None, "error"

    # One request at a time left four of five windows idle and paid a /pull
    # cycle per job: 781 asks took ~27 min at ~2,050 ms each on 2026-09-28.
    # As many workers as windows, like SAMPLES; each window still paces itself.
    with ThreadPoolExecutor(max_workers=max(1, config.max_concurrency)) as pool:
        for row, body, incidents, failure in pool.map(ask, todo):
            if failure == "circuit":
                circuit_open = True
                continue
            if failure == "error" or circuit_open:
                outcome["error" if failure else "not_asked"] += 1
                continue
            keys = _all_period_keys(json.dumps(body) if body else None)
            before = _all_period_keys(row["statistics_json"])
            gained = keys - before - {"yellowCards", "redCards"}
            outcome["recovered" if gained else "unchanged"] += 1
            # None keeps the cached statistics (COALESCE) and stamps a late
            # fetched_at: asked once more, the row is final either way.
            cache.save_event_stats(row["event_id"], body, incidents, "finished")

    summary.update(outcome=dict(outcome), circuit_open=circuit_open, backup=str(backup))
    verdict = "PARTIAL" if circuit_open or outcome["error"] else "OK"
    print(
        "SOFA_SUMMARY: "
        + json.dumps(
            {"stage": "REFETCH_PROVISIONAL", "verdict": verdict, "metrics": summary}
        )
    )
    return 1 if verdict == "PARTIAL" else 0


if __name__ == "__main__":
    sys.exit(main())
