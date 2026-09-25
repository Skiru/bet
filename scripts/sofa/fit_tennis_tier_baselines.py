#!/usr/bin/env python3
"""Fit the tennis gender x tier x surface baselines from the cache (no network).

See bet.sofa.tennis_prior for why. Writes `config/sofa_tennis_tier_baselines.json`
by default, which SHEET reads for a tennis row without a ladder (most of
them) on the metrics in tennis_prior.TIER_PRIOR_METRICS. Like every
fitted file it is installed between days, never mid-day (CLAUDE.md).

`--before` fits on matches that started before a date and `--measure-from`
scores the result on matches from that date on, against the global pool it
replaces - the out-of-sample check, printed and not written anywhere.

Usage:
    PYTHONPATH=src:. .venv/bin/python scripts/sofa/fit_tennis_tier_baselines.py \\
        --out /tmp/tier.json --before 2026-09-01 --measure-from 2026-09-01
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import statistics
import sys
from collections import defaultdict
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bet.sofa.contracts import GapReason
from bet.sofa.metrics import extract_flat_statistics, extract_metric
from bet.sofa.tennis_prior import _is_countable, fit_tier_baselines, tier_key

DEFAULT_OUT = Path("config/sofa_tennis_tier_baselines.json")


def iter_tennis_events(db_path: str) -> Iterator[dict[str, Any]]:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        for (js,) in conn.execute("SELECT events_json FROM sofa_entity_events"):
            try:
                payload = json.loads(js)
            except (TypeError, json.JSONDecodeError):
                continue
            events = payload.get("events") if isinstance(payload, dict) else payload
            for e in events or []:
                cat = (e.get("tournament") or {}).get("category") or {}
                if (cat.get("sport") or {}).get("slug") == "tennis":
                    yield e
    finally:
        conn.close()


def load_statistics(db_path: str) -> dict[int, dict[str, Any]]:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        return {
            int(eid): json.loads(js)
            for eid, js in conn.execute(
                "SELECT sofascore_event_id, statistics_json FROM sofa_event_stats "
                "WHERE statistics_json IS NOT NULL"
            )
        }
    finally:
        conn.close()


def _ts(date: str) -> int:
    return int(datetime.fromisoformat(date).replace(tzinfo=UTC).timestamp())


def measure(
    baselines: dict[str, Any],
    global_means: dict[str, float],
    events: list[dict[str, Any]],
    stats: dict[int, dict[str, Any]],
) -> dict[str, dict[str, float]]:
    """Mean absolute error of the tier mean vs the pooled mean, per metric, on
    events the fit never saw. Only observations whose tier key has an entry."""
    err: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    seen: set[int] = set()
    for e in events:
        if e["id"] in seen or not _is_countable(e):
            continue
        seen.add(e["id"])
        cat = e["tournament"]["category"].get("name")
        key = tier_key(cat, e.get("groundType"))
        flat = extract_flat_statistics(stats.get(e["id"]))
        for metric, entry in baselines.items():
            tier = entry.get(key) if key else None
            if tier is None or metric not in global_means:
                continue
            sides = (True,) if metric.endswith("_total") else (True, False)
            for is_home in sides:
                v = extract_metric(metric, "tennis", flat, None, e, is_home)
                if isinstance(v, GapReason):
                    continue
                err[metric]["tier"].append(abs(v - tier["mean"]))
                err[metric]["global"].append(abs(v - global_means[metric]))
    return {
        m: {
            "n": len(d["tier"]),
            "mae_tier": round(statistics.mean(d["tier"]), 4),
            "mae_global": round(statistics.mean(d["global"]), 4),
        }
        for m, d in sorted(err.items())
        if d["tier"]
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", default="data/sofa.db")
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--before", default=None, help="fit only on matches before")
    ap.add_argument("--measure-from", default=None)
    args = ap.parse_args()
    if args.measure_from and (not args.before or args.before > args.measure_from):
        ap.error("--measure-from needs --before at or before it (no leakage)")

    events = list(iter_tennis_events(args.db))
    stats = load_statistics(args.db)
    fit_events = events
    if args.before:
        cut = _ts(args.before)
        fit_events = [e for e in events if (e.get("startTimestamp") or 0) < cut]
    baselines = fit_tier_baselines(fit_events, stats.get)
    out = {
        "fitted_at_utc": datetime.now(UTC).isoformat(),
        "fitted_from": "sofa_entity_events + sofa_event_stats (cache, no network)",
        "fitted_before": args.before,
        "metrics": baselines,
    }
    Path(args.out).write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "out": args.out, "metrics": len(baselines),
        "keys": sorted({k for m in baselines.values() for k in m}),
    }))

    if args.measure_from:
        start = _ts(args.measure_from)
        held_out = [e for e in events if (e.get("startTimestamp") or 0) >= start]
        pooled = fit_tier_baselines(fit_events, stats.get)
        # The pool the tier entry replaces: every level and surface together.
        global_means: dict[str, float] = {}
        for metric, entry in pooled.items():
            total = sum(float(v["mean"]) * int(v["n"]) for v in entry.values())
            n = sum(int(v["n"]) for v in entry.values())
            global_means[metric] = total / n
        report = measure(baselines, global_means, held_out, stats)
        print(json.dumps({"held_out_from": args.measure_from, **report}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
