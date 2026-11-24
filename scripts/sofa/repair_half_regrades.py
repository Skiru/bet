"""Undo regrade flips made off a rewritten first half (dry run by default).

Why. Sofascore rewrites a finished football match's half score days after
it (period1 0-0 or gone, period2 = the whole match, the incidents' HT
marker zeroed alike) while the goal list keeps its minutes. SETTLE re-fetched
/event for every event of a re-settled day and the cache replaced the good
payload; ``regrade_settled.py --apply`` then flipped correct half rows on the
degraded one (the HT marker agreed with it, so ``half_time_disagrees`` did
not refuse). Fixed 2026-11-24 (``detail_guard``, the goal witness in
``metrics.half_time_disagrees``); this script finds the rows already flipped.

What. Every change in ``runs/sofa/regrade_*.json`` whose row still holds the
regrade's value, whose event now fails ``half_time_disagrees`` and whose
pre-regrade value is what the row grades to on the goal incidents' own first
half (``metrics.goal_incidents_half_time``: period1 / period2 / HT marker set
from the goals, then ``regrade_settled.grade_live``) is a RESTORE. A change
the goals do not reproduce is reported (``left``), never touched.

``--apply`` writes the undo log ``runs/sofa/repair_half_regrades_<ts>.json``
first, then restores actual / outcome (settled_at = now); re-run
``record_results.py`` for the days it names afterwards. Read-only without it.

Exit 0 OK, 1 nothing restorable but rows left, 2 FAILED.
"""

from __future__ import annotations

import argparse
import copy
import json
import sqlite3
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bet.sofa.config import SofaConfig
from bet.sofa.db import RetryingConnection
from bet.sofa.metrics import (
    goal_incidents_half_time,
    half_time_disagrees,
    regulation_score,
)
from scripts.sofa.regrade_settled import _fixtures, _key, grade_live
from scripts.sofa.run_settle import printed_keys


def goal_half_event(
    event: dict[str, Any], incidents: dict[str, Any] | None
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """(event, incidents) with the first half set from the goal incidents,
    or None when the goals are no reading."""
    half = goal_incidents_half_time(event, incidents)
    score = regulation_score(event)
    if half is None or score is None or incidents is None:
        return None
    ev = copy.deepcopy(event)
    for side, i in (("homeScore", 0), ("awayScore", 1)):
        block = dict(ev.get(side) or {})
        block["period1"] = half[i]
        block["period2"] = int(score[i]) - half[i]
        ev[side] = block
    inc = copy.deepcopy(incidents)
    for item in inc.get("incidents") or []:
        if item.get("incidentType") == "period" and item.get("text") == "HT":
            item["homeScore"], item["awayScore"] = half
    return ev, inc


def logged_changes(runs_dir: Path) -> dict[int, dict[str, Any]]:
    """The latest logged regrade change of each settled row id."""
    out: dict[int, dict[str, Any]] = {}
    for path in sorted(runs_dir.glob("regrade_*.json")):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            continue
        if not isinstance(doc, list):
            continue
        for change in doc:
            if isinstance(change, dict) and isinstance(change.get("id"), int):
                out[int(change["id"])] = {**change, "log": path.name}
    return out


def plan(
    conn: sqlite3.Connection, runs_dir: Path
) -> tuple[list[dict[str, Any]], Counter[str]]:
    changes = logged_changes(runs_dir)
    tally: Counter[str] = Counter()
    if not changes:
        return [], tally
    conn.row_factory = sqlite3.Row
    ids = sorted(changes)
    rows: dict[int, dict[str, Any]] = {}
    for start in range(0, len(ids), 500):
        chunk = ids[start:start + 500]
        for r in conn.execute(
            "SELECT id, run_date, sofascore_event_id, sport, market, subject, line,"
            " direction, actual_value, outcome, settled_at FROM sofa_settled_row"
            f" WHERE id IN ({','.join('?' * len(chunk))})", chunk
        ):
            rows[int(r["id"])] = dict(r)
    events: dict[int, tuple[dict[str, Any] | None, dict[str, Any] | None,
                            str | None, str | None, str | None]] = {}
    fixtures: dict[str, dict[int, dict[str, Any]]] = {}
    printed: dict[str, set[Any]] = {}
    out: list[dict[str, Any]] = []
    for rid, change in sorted(changes.items()):
        row = rows.get(rid)
        if row is None:
            tally["gone"] += 1
            continue
        if row["sport"] != "football":
            tally["not_football"] += 1
            continue
        if (row["actual_value"], row["outcome"]) != (
                change["new_actual"], change["new_outcome"]):
            tally["row_moved_since"] += 1
            continue
        eid = int(row["sofascore_event_id"])
        if eid not in events:
            d = conn.execute(
                "SELECT detail_json FROM sofa_event_detail WHERE sofascore_event_id = ?"
                " AND status_type = 'finished'", (eid,)).fetchone()
            s = conn.execute(
                "SELECT statistics_json, incidents_json, lineups_json FROM"
                " sofa_event_stats WHERE sofascore_event_id = ?", (eid,)).fetchone()
            event = (json.loads(d["detail_json"]) or {}).get("event") if d else None
            events[eid] = (
                event if isinstance(event, dict) else None,
                json.loads(s["incidents_json"]) if s and s["incidents_json"] else None,
                s["statistics_json"] if s else None,
                s["incidents_json"] if s else None,
                s["lineups_json"] if s else None,
            )
        event, incidents, sj, ij, lj = events[eid]
        if event is None:
            tally["left:NO_EVENT"] += 1
            continue
        if not half_time_disagrees(event, incidents):
            tally["half_agrees"] += 1
            continue
        patched = goal_half_event(event, incidents)
        if patched is None:
            tally["left:GOALS_NO_READING"] += 1
            continue
        day = row["run_date"]
        if day not in fixtures:
            fixtures[day] = _fixtures(runs_dir, day)
            printed[day] = (printed_keys(runs_dir / day)
                            if (runs_dir / day).exists() else set())
        fixture = fixtures[day].get(eid)
        graded = grade_live(row, patched[0], fixture, sj, json.dumps(patched[1]), lj)
        if graded == grade_live(row, event, fixture, sj, ij, lj):
            tally["not_half_market"] += 1  # the first half does not grade it
            continue
        if isinstance(graded, str):
            tally[f"left:{graded.split(':')[-1]}"] += 1
            continue
        if graded != (change["old_actual"], change["old_outcome"]):
            tally["left:GOALS_DISAGREE_WITH_OLD"] += 1
            continue
        tally["restore"] += 1
        out.append({
            "id": rid, "run_date": day, "event_id": eid,
            "market": row["market"], "subject": row["subject"],
            "line": row["line"], "direction": row["direction"],
            "old_actual": row["actual_value"], "old_outcome": row["outcome"],
            "new_actual": change["old_actual"], "new_outcome": change["old_outcome"],
            "old_settled_at": row["settled_at"], "regrade_log": change["log"],
            "printed": _key(row) in printed[day],
        })
    conn.row_factory = None
    return out, tally


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", default=True,
                      help="report only (the default)")
    mode.add_argument("--apply", action="store_true",
                      help="write the undo log, then restore the rows")
    args = parser.parse_args()
    config = SofaConfig.from_env()
    runs_dir = Path(config.runs_dir)
    at = datetime.now(UTC)
    try:
        uri = f"file:{config.db_path}{'' if args.apply else '?mode=ro'}"
        conn = sqlite3.connect(uri, uri=True, timeout=30.0,
                               factory=RetryingConnection)
        restores, tally = plan(conn, runs_dir)
    except (sqlite3.Error, ValueError, OSError) as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 2
    for r in restores:
        if r["printed"]:
            print(f"PRINTED {r['run_date']} event={r['event_id']} {r['market']} "
                  f"{r['subject']} {r['direction']} {r['line']:g}: "
                  f"{r['old_outcome']} -> {r['new_outcome']}")
    by_day = Counter(r["run_date"] for r in restores)
    metrics: dict[str, Any] = {
        "applied": bool(args.apply), "tally": dict(tally),
        "restore_by_day": dict(sorted(by_day.items())),
        "restore_events": len({r["event_id"] for r in restores}),
        "restore_printed": sum(1 for r in restores if r["printed"]),
    }
    if args.apply and restores:
        log = runs_dir / f"repair_half_regrades_{at:%Y%m%dT%H%M%SZ}.json"
        log.write_text(json.dumps(restores, indent=1, ensure_ascii=False) + "\n")
        with conn:
            conn.executemany(
                "UPDATE sofa_settled_row SET actual_value = ?, outcome = ?,"
                " settled_at = ? WHERE id = ? AND actual_value = ? AND outcome = ?",
                [(r["new_actual"], r["new_outcome"], at.isoformat(), r["id"],
                  r["old_actual"], r["old_outcome"]) for r in restores])
        metrics["log"] = str(log)
    conn.close()
    print("SOFA_SUMMARY: " + json.dumps(
        {"stage": "REPAIR_HALF_REGRADES", "verdict": "OK", "metrics": metrics}))
    left = sum(n for k, n in tally.items() if k.startswith("left:"))
    return 1 if left and not restores else 0


if __name__ == "__main__":
    sys.exit(main())
