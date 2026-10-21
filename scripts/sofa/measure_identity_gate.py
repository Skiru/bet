#!/usr/bin/env python3
# ruff: noqa: E501  - report lines are tables.
"""What the per-family identity gate (epochs.IDENTITY_GATE_PER_FAMILY) gives
back, and whether what it gives back looks like the rest.

A. Per day (``--days``): every INTERNAL_INCONSISTENT gap of 03_samples.json
   whose detail names a sample event ("Side A event 123 gap") is re-read from
   the cache: the event's /statistics, /incidents and listing. Under the
   per-family rule (metrics.identity_gap_for_metric) the gap is either still
   a gap or an observation that comes back. Per metric: gaps, restored, kept;
   per identity family: distinct events.

B. Out of the days' samples (``--from`` / ``--to`` on the cache's listed
   football events with statistics): the full-match totals - goals, corners,
   card points, fouls - of the matches the per-family rule restores (they
   fail the shot identity only, or the goal-incident identity only) against
   the matches that fail no identity. Mean difference with a 95% interval
   from resampling matches; a restored group that read systematically higher
   or lower would bias the samples it joins (F28: the old shot identity
   blocked attacking matches directionally).

Measurement only: the DB is opened read-only, no artifact is written.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_identity_gate.py \\
        --days 2026-10-18,2026-10-20,2026-10-21 [--from 2026-06-01 --to 2026-10-21] \\
        [--limit 60000] [--json out.json]
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa.config import SofaConfig  # noqa: E402
from bet.sofa.contracts import GapReason  # noqa: E402
from bet.sofa.metrics import (  # noqa: E402
    IDENTITY_GOAL_INCIDENTS,
    IDENTITY_SHOTS,
    extract_flat_statistics,
    extract_metric,
    identity_failures,
    identity_gap_for_metric,
)

EVENT_IN_DETAIL = re.compile(r"event (\d+)")
_FETCHED: dict[int, str] = {}
TOTALS = ("goals_total", "corners_total", "cards_points_total", "fouls_total",
          "shots_total")
BOOT = 1000


def _connect(db_path: str) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)


def _payloads(conn: sqlite3.Connection, eid: int) -> tuple[Any, Any, dict[str, Any] | None] | None:
    row = conn.execute(
        "SELECT statistics_json, incidents_json, fetched_at FROM sofa_event_stats"
        " WHERE sofascore_event_id = ?", (eid,)).fetchone()
    if row is None:
        return None
    _FETCHED[eid] = str(row[2])[:10]
    le = conn.execute("SELECT event_json FROM sofa_listed_event WHERE event_id = ?",
                      (eid,)).fetchone()
    event = json.loads(le[0]) if le else None
    stats = json.loads(row[0]) if row[0] else None
    incidents = json.loads(row[1]) if row[1] else None
    return stats, incidents or None, event


def per_day(conn: sqlite3.Connection, runs_dir: Path, day: str) -> dict[str, Any]:
    run = runs_dir / day
    samples = json.loads((run / "03_samples.json").read_text(encoding="utf-8"))
    fixtures = {f["sofascore_event_id"]: f for f in json.loads(
        (run / "02_fixtures.json").read_text(encoding="utf-8"))}
    by_metric: dict[str, Counter[str]] = defaultdict(Counter)
    families: Counter[str] = Counter()
    events_seen: dict[int, tuple[str, ...]] = {}
    unread = 0
    none_refetched = 0  # passes now, its payload re-fetched after the day
    none_metrics: Counter[str] = Counter()
    cache: dict[int, Any] = {}
    for fx in samples:
        sport = (fixtures.get(fx["sofascore_event_id"]) or {}).get("sport")
        if sport is None:
            continue
        for gap in fx.get("gaps") or []:
            if gap.get("reason") != "INTERNAL_INCONSISTENT":
                continue
            m = EVENT_IN_DETAIL.search(gap.get("detail") or "")
            if not m:
                continue
            eid = int(m.group(1))
            if eid not in cache:
                cache[eid] = _payloads(conn, eid)
            loaded = cache[eid]
            metric = gap["metric"]
            if loaded is None or loaded[2] is None:
                unread += 1
                by_metric[metric]["unread"] += 1
                continue
            stats, incidents, event = loaded
            failed = identity_failures(extract_flat_statistics(stats), incidents, event, sport)
            if eid not in events_seen:
                events_seen[eid] = tuple(sorted(failed)) or ("none",)
                families[f"{sport}:{'+'.join(events_seen[eid])}"] += 1
                if not failed and _FETCHED.get(eid, "") >= day:
                    none_refetched += 1
            if not failed:
                none_metrics[metric] += 1
            by_metric[metric]["gaps"] += 1
            if not failed:
                # the gap is extract_metric's own (goal_score_inconsistent,
                # a negative half): not the identity gate's
                by_metric[metric]["not_identity"] += 1
            elif identity_gap_for_metric(metric, sport, failed) is None:
                by_metric[metric]["restored"] += 1
            else:
                by_metric[metric]["kept"] += 1
    restored = sum(c["restored"] for c in by_metric.values())
    gaps = sum(c["gaps"] for c in by_metric.values())
    return {"day": day, "gaps": gaps, "restored": restored, "unread": unread,
            "none_refetched_on_or_after_day": none_refetched,
            "none_metrics": dict(none_metrics.most_common(8)),
            "events": len(events_seen), "families": dict(families.most_common()),
            "by_metric": {k: dict(v) for k, v in sorted(
                by_metric.items(), key=lambda kv: -kv[1]["restored"])}}


def _boot_diff(a: list[float], b: list[float], rng: random.Random) -> tuple[float, float, float]:
    diff = sum(a) / len(a) - sum(b) / len(b)
    out = []
    for _ in range(BOOT):
        ra = [a[rng.randrange(len(a))] for _ in a]
        rb = [b[rng.randrange(len(b))] for _ in range(min(len(b), 20000))]
        out.append(sum(ra) / len(ra) - sum(rb) / len(rb))
    out.sort()
    return diff, out[int(0.025 * BOOT)], out[int(0.975 * BOOT)]


def bias(conn: sqlite3.Connection, start: str, end: str, limit: int) -> dict[str, Any]:
    lo = int(datetime.fromisoformat(start).replace(tzinfo=UTC).timestamp())
    hi = int(datetime.fromisoformat(end).replace(tzinfo=UTC).timestamp())
    rows = conn.execute(
        "SELECT l.event_json, s.statistics_json, s.incidents_json"
        " FROM sofa_listed_event l JOIN sofa_event_stats s"
        " ON s.sofascore_event_id = l.event_id"
        " WHERE l.sport = 'football' AND l.start_ts >= ? AND l.start_ts < ?"
        " AND s.statistics_json IS NOT NULL ORDER BY l.start_ts DESC LIMIT ?",
        (lo, hi, limit))
    groups: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    counts: Counter[str] = Counter()
    for ev_raw, st_raw, inc_raw in rows:
        event = json.loads(ev_raw)
        if (event.get("status") or {}).get("type") != "finished":
            continue
        flat = extract_flat_statistics(json.loads(st_raw))
        incidents = json.loads(inc_raw) if inc_raw else None
        failed = identity_failures(flat, incidents or None, event, "football")
        # a placeholder feed: an incident list holding nothing but period
        # entries (no goal, card or substitution)
        placeholder = bool(incidents) and all(
            i.get("incidentType") == "period"
            for i in (incidents or {}).get("incidents", []))
        if placeholder:
            counts["placeholder_feed"] += 1
        if not failed:
            group = "kept_placeholder_feed" if placeholder else "kept"
        elif set(failed) == {IDENTITY_SHOTS}:
            group = "restored_shots_only"
        elif set(failed) == {IDENTITY_GOAL_INCIDENTS}:
            group = "restored_goal_incidents_only"
        else:
            group = "other_failures"
        counts[group] += 1
        for metric in TOTALS:
            if identity_gap_for_metric(metric, "football", failed) is not None:
                continue
            val = extract_metric(metric, "football", flat, incidents or None, event, True)
            if isinstance(val, GapReason):
                continue
            groups[group][metric].append(float(val))
    rng = random.Random(20261021)
    out: dict[str, Any] = {"window": [start, end], "matches": dict(counts), "compare": {}}
    # A placeholder feed fails the goal identity only when the score is not
    # 0-0: the old gate kept its 0-0s and dropped its scoring matches. The
    # fair comparison for goals pools both halves of that feed against the
    # full feeds.
    for metric in TOTALS:
        groups["placeholder_feed_all"][metric] = (
            groups["kept_placeholder_feed"].get(metric, [])
            + groups["restored_goal_incidents_only"].get(metric, []))
    for group in ("restored_shots_only", "restored_goal_incidents_only",
                  "kept_placeholder_feed", "placeholder_feed_all"):
        for metric in TOTALS:
            a, b = groups[group].get(metric) or [], groups["kept"].get(metric) or []
            if len(a) < 30 or len(b) < 30:
                continue
            diff, lo_ci, hi_ci = _boot_diff(a, b, rng)
            out["compare"][f"{group}|{metric}"] = {
                "n_restored": len(a), "n_kept": len(b),
                "mean_restored": round(sum(a) / len(a), 3),
                "mean_kept": round(sum(b) / len(b), 3),
                "diff": round(diff, 3), "ci95": [round(lo_ci, 3), round(hi_ci, 3)]}
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--days", required=True, help="comma-separated YYYY-MM-DD")
    ap.add_argument("--from", dest="start", default=None)
    ap.add_argument("--to", dest="end", default=None)
    ap.add_argument("--limit", type=int, default=60000)
    ap.add_argument("--json", default=None)
    args = ap.parse_args()
    config = SofaConfig.from_env()
    conn = _connect(str(config.db_path))
    runs_dir = Path(config.runs_dir)
    report: dict[str, Any] = {"days": []}
    for day in [d.strip() for d in args.days.split(",") if d.strip()]:
        if not (runs_dir / day / "03_samples.json").exists():
            print(f"{day}: no 03_samples.json", file=sys.stderr)
            continue
        res = per_day(conn, runs_dir, day)
        report["days"].append(res)
        print(f"== {day}: INTERNAL_INCONSISTENT gaps {res['gaps']} (unread {res['unread']}),"
              f" restored per family {res['restored']}, distinct events {res['events']}")
        print(f"   families: {res['families']}")
        print(f"   passing now (family none): payload re-fetched on/after the day "
              f"{res['none_refetched_on_or_after_day']}; their gaps {res['none_metrics']}")
        for metric, c in list(res["by_metric"].items())[:15]:
            print(f"   {metric:28s} {c}")
    if args.start and args.end:
        b = bias(conn, args.start, args.end, args.limit)
        report["bias"] = b
        print(f"== bias {args.start}..{args.end}: matches {b['matches']}")
        for key, v in b["compare"].items():
            print(f"   {key:48s} restored {v['mean_restored']:7.3f} (n {v['n_restored']})"
                  f" kept {v['mean_kept']:7.3f} (n {v['n_kept']}) diff {v['diff']:+.3f}"
                  f" [{v['ci95'][0]:+.3f}, {v['ci95'][1]:+.3f}]")
    if args.json:
        Path(args.json).write_text(json.dumps(report, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
