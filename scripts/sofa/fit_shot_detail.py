#!/usr/bin/env python3
"""Fit the shot-detail estimator (bet.sofa.shot_detail) and its history curve,
on a COPY of the tables it reads - never installed by this script.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/fit_shot_detail.py \\
        --before <d> [--out-dir data/refit_shot_detail_<d>]

1. Copy: the shotmap rows of sofa_event_extra, the lineups of those events and
   their kickoff from sofa_listing_event go into <out-dir>/shot_detail.db
   (CLAUDE.md "Changing the pipeline" 4: fits run on a copy; only these three
   tables are needed, so the copy is small). An existing copy is reused.
2. Fit, on starts kicked off before --before: each metric's position means
   (and the all-positions mean) and K, the pseudo-starts that minimise the
   walk-forward log-loss summed over lines 0.5 / 1.5 / 2.5
   (measure_shot_detail.measure: a start is forecast only from earlier ones).
3. Curve: the walk-forward forecasts at the chosen K, bucketed by
   fit_confidence.EDGES per "<metric>|OVER" with fit_confidence's floors
   (MIN_MARKET_BUCKET rows a bucket), realised and its Wilson lower bound -
   the replay of the very estimator SHEET would price with.

Writes <out-dir>/sofa_shot_detail.json (the estimator file SHEET would read
from config/) and <out-dir>/curves.json (by_market_direction entries to merge
into config/sofa_confidence_calibration.json at an install the operator
approves), and fit_report.md. Exit 0, 2 on a crash.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import defaultdict
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import shot_detail as sd  # noqa: E402
from bet.sofa.config import SofaConfig  # noqa: E402
from scripts.sofa.fit_confidence import (  # noqa: E402
    EDGES,
    MIN_MARKET_BUCKET,
    wilson_lo,
)
from scripts.sofa.measure_shot_detail import (  # noqa: E402
    KS,
    LINES,
    ll,
    measure,
    starts,
)


def make_copy(source: str, target: Path) -> None:
    """The three tables the fit reads, for the events that have a shotmap."""
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".tmp")
    tmp.unlink(missing_ok=True)
    conn = sqlite3.connect(tmp)
    conn.execute("ATTACH DATABASE ? AS live", (f"file:{source}?mode=ro",))
    conn.executescript("""
        CREATE TABLE sofa_event_extra AS SELECT * FROM live.sofa_event_extra
            WHERE kind = 'shotmap' AND length(payload_json) > 2;
        CREATE INDEX x_id ON sofa_event_extra (sofascore_event_id);
        CREATE TABLE sofa_event_stats AS
            SELECT s.sofascore_event_id, s.lineups_json FROM live.sofa_event_stats s
            JOIN sofa_event_extra x USING (sofascore_event_id);
        CREATE TABLE sofa_listing_event AS
            SELECT l.event_id, l.start_ts FROM live.sofa_listing_event l
            JOIN sofa_event_extra x ON x.sofascore_event_id = l.event_id;
    """)
    conn.commit()
    conn.close()
    tmp.replace(target)


def bucket_of(p: float) -> int:
    """fit_confidence's bucket index of a forecast."""
    for i in range(len(EDGES) - 1):
        if EDGES[i] <= p < EDGES[i + 1]:
            return i
    return len(EDGES) - 2


def fit(rows: list[Any]) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    pool_sum: dict[tuple[str, str], float] = defaultdict(float)
    pool_n: dict[str, int] = defaultdict(int)
    for _ts, _e, _p, pos, start in rows:
        pool_n[pos] += 1
        for m in sd.METRICS:
            pool_sum[(pos, m)] += start[m]
    n_all = sum(pool_n.values())
    preds = measure(rows, sd.MIN_STARTS, sd.WINDOW)["preds"]
    metrics: dict[str, Any] = {}
    curves: dict[str, Any] = {}
    report = [f"starts: {n_all}", ""]
    for m in sd.METRICS:
        total = {k: sum(sum(ll(p[k], y) for p, _, y in preds[(m, line)])
                        for line in LINES) for k in KS}
        best = min(total, key=lambda k: total[k])
        metrics[m] = {
            "k": best,
            "pool": {pos: round(pool_sum[(pos, m)] / n, 5)
                     for pos, n in pool_n.items() if n >= 200},
            "pool_all": round(sum(pool_sum[(pos, m)] for pos in pool_n) / n_all, 5),
        }
        counts: dict[int, list[int]] = defaultdict(list)
        for line in LINES:
            for p, _, y in preds[(m, line)]:
                counts[bucket_of(p[best])].append(y)
        curve = {}
        for b, hits in sorted(counts.items()):
            if len(hits) < MIN_MARKET_BUCKET:
                continue
            k_, n = sum(hits), len(hits)
            curve[f"{EDGES[b]:.3f}-{EDGES[b + 1]:.3f}"] = {
                "n": n, "realised": round(k_ / n, 4),
                "realised_lo95": round(wilson_lo(k_, n), 4)}
        if curve:
            curves[f"{m}|OVER"] = curve
        report.append(f"## {m}: K={best}; " + ", ".join(
            f"K={k} {v / max(1, sum(len(preds[(m, ln)]) for ln in LINES)):.4f}"
            for k, v in total.items()))
        for key, c in curve.items():
            report.append(f"- {key}: n {c['n']}, realised {c['realised']}, "
                          f"lo95 {c['realised_lo95']}")
        report.append("")
    return metrics, curves, report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--before", required=True)
    ap.add_argument("--out-dir")
    args = ap.parse_args()
    before = date.fromisoformat(args.before)
    out = Path(args.out_dir or f"data/refit_shot_detail_{args.before}")
    copy = out / "shot_detail.db"
    if not copy.exists():
        make_copy(SofaConfig.from_env().db_path, copy)
    db = sqlite3.connect(f"file:{copy}?mode=ro", uri=True)
    cut = int(datetime(before.year, before.month, before.day, tzinfo=UTC).timestamp())
    rows = [r for r in starts(db) if r[0] < cut]
    metrics, curves, report = fit(rows)
    fitted_from = {"db_path": str(copy), "before": args.before,
                   "fitted_at_utc": datetime.now(UTC).isoformat(),
                   "starts": len(rows), "matches": len({r[1] for r in rows}),
                   "script": "scripts/sofa/fit_shot_detail.py"}
    (out / "sofa_shot_detail.json").write_text(json.dumps(
        {"fitted_from": fitted_from, "window": sd.WINDOW, "min_starts": sd.MIN_STARTS,
         "outside_x": sd.OUTSIDE_X, "metrics": metrics}, indent=1) + "\n")
    (out / "curves.json").write_text(json.dumps(
        {"fitted_from": fitted_from, "by_market_direction": curves}, indent=1) + "\n")
    (out / "fit_report.md").write_text("\n".join(
        [f"# Shot detail fit, before {args.before}", ""] + report) + "\n")
    print(json.dumps({"out_dir": str(out), **fitted_from,
                      "curves": {k: len(v) for k, v in curves.items()}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
