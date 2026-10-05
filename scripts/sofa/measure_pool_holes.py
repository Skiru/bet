#!/usr/bin/env python3
"""Does a pool over-claim where it fills a hole in a market's own curve? Measured.

2026-10-05, Moss - Kongsvinger goals_1h_total O0.5: p_central 0.803 sits in
0.800-0.825, where goals_1h_total has no bucket of its own (market, OVER,
thin), so Calibration.realised fell to pooled:football and printed 0.815 -
above the model's own p - while the market's own neighbouring buckets bound
0.709 (thin OVER 0.75-0.80) and 0.731 (by_market 0.75-0.80). The K13 thin
cap only reads a thin bucket AT p, so it did nothing.

For every settled row (sofa_settled_row, the filters fit_confidence uses:
friendlies out, derived / model-less / player markets out) at p_central >=
--min-p, the lookup CONFIDENCE would make in the stats-only epoch
(cap_market_by_thin on, gap_shrink_k 0; the row's match class from the
cache) is repeated with Calibration.cap_pool_by_neighbour off and on. Rows
the lookup serves from a pool (`pooled:<sport>` / `pooled`) are kept and
split by what the market itself holds there:

* ``hole_below`` - the market has its own buckets and one below p: the cap
  applies;
* ``hole_no_below`` - own buckets, none below p: left to the pool;
* ``no_own_curve`` - the market has no bucket of its own anywhere.

``cap_acts`` (split ``:live`` / ``:cache``) are the rows whose capped claim is
below the pool's - the only rows the rule moves.

Per group: rows, matches, mean claimed (pool, and capped), realised, and
realised - claimed with a 95% interval from a Poisson bootstrap over
matches; for the priced live rows (offered_odds set) also the rows each
claim would admit at x = claim x odds >= 0.90 and claim >= 0.70, and their
ROI per bet.

Evaluation note: a hole row is by construction in no market curve, and its
weight in the pool is ~1e-4 of the bucket, so neither claim was fitted on
the rows it is scored on.

Measurement only: the DB is opened read-only and nothing is written but
--out.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_pool_holes.py \\
        [--min-p 0.70] [--out data/analysis_<d>/pool_holes.json]
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from collections.abc import Iterable
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np  # noqa: E402

from bet.sofa.confidence import (  # noqa: E402
    CATCH_ALL_BUCKET_TOP,
    Calibration,
    direction_key,
)
from bet.sofa.engine import has_calibratable_model  # noqa: E402
from bet.sofa.fit_meta import friendly_exclusion_sql  # noqa: E402
from bet.sofa.market_mapper import is_derived  # noqa: E402
from scripts.sofa.fit_confidence import (  # noqa: E402
    EDGES,
    bucket_of,
    load_event_classes,
)

# 'cache-calibration' sorts above every date, so a range keeps the live days.
LIVE_TERM = "and run_date between '2000-01-01' and '2999-12-31'"
STAKE_X = 0.90
FLOOR = 0.70

Cell = tuple[str | None, str, str, str, int]


def _own_view(cal: Calibration, klass: str | None) -> Calibration | None:
    return cal.for_class(klass) if klass is not None else cal


def group_of(cal: Calibration, klass: str | None, market: str, direction: str,
             p: float) -> str:
    """Which of the three groups a pooled read falls in (see module doc)."""
    own = _own_view(cal, klass)
    if own is None:
        return "no_own_curve"
    key = direction_key(market, direction)
    curves = [own.by_market.get(market, {}), own.by_market_direction.get(key, {}),
              own.thin_by_market_direction.get(key, {})]
    if not any(curves):
        return "no_own_curve"
    below = any(
        CATCH_ALL_BUCKET_TOP < float(k.split("-")[1]) <= p
        for curve in curves for k in curve
    )
    return "hole_below" if below else "hole_no_below"


def lookup_cells(
    base: Calibration, capped: Calibration, cells: Iterable[Cell]
) -> dict[Cell, tuple[float, float, str, str] | None]:
    """cell -> (pool claim, capped claim, group, capped source), pooled only."""
    out: dict[Cell, tuple[float, float, str, str] | None] = {}
    for cell in cells:
        klass, market, direction, sport, b = cell
        p = EDGES[b]
        hit = base.realised(market, p, sport, direction, klass)
        if hit is None:
            out[cell] = None
            continue
        source = hit[1].split(":", 1)[1] if klass and hit[1].startswith(f"{klass}:") \
            else hit[1]
        if not source.startswith("pooled"):
            out[cell] = None
            continue
        on = capped.realised(market, p, sport, direction, klass)
        assert on is not None
        out[cell] = (hit[0], on[0], group_of(base, klass, market, direction, p), on[1])
    return out


def poisson_ci(
    per_event: np.ndarray, reps: int, seed: int
) -> tuple[float, float]:
    """95% interval of sum(col1)/sum(col0)-style ratio: per_event columns are
    (n, numerator); resampled with Poisson(1) weights per match."""
    rng = np.random.default_rng(seed)
    w = rng.poisson(1.0, size=(reps, per_event.shape[0]))
    n = w @ per_event[:, 0]
    num = w @ per_event[:, 1]
    with np.errstate(invalid="ignore", divide="ignore"):
        stat = num / n
    stat = stat[np.isfinite(stat)]
    return float(np.percentile(stat, 2.5)), float(np.percentile(stat, 97.5))


def summarise(rows: list[dict[str, Any]], reps: int, seed: int) -> dict[str, Any]:
    if not rows:
        return {"rows": 0}
    events = sorted({r["event"] for r in rows})
    index = {e: i for i, e in enumerate(events)}
    out: dict[str, Any] = {
        "rows": len(rows), "matches": len(events),
        "claimed_pool": round(float(np.mean([r["pool"] for r in rows])), 4),
        "claimed_capped": round(float(np.mean([r["capped"] for r in rows])), 4),
        "realised": round(float(np.mean([r["hit"] for r in rows])), 4),
    }
    for name in ("pool", "capped"):
        agg = np.zeros((len(events), 2))
        for r in rows:
            i = index[r["event"]]
            agg[i, 0] += 1
            agg[i, 1] += r["hit"] - r[name]
        lo, hi = poisson_ci(agg, reps, seed)
        mean = float(agg[:, 1].sum() / agg[:, 0].sum())
        out[f"realised_minus_{name}"] = round(mean, 4)
        out[f"realised_minus_{name}_ci95"] = [round(lo, 4), round(hi, 4)]
    priced = [r for r in rows if r["odds"]]
    out["priced_rows"] = len(priced)
    for name in ("pool", "capped"):
        sel = [r for r in priced
               if r[name] >= FLOOR and r[name] * r["odds"] >= STAKE_X]
        block: dict[str, Any] = {"rows": len(sel)}
        if sel:
            ev = sorted({r["event"] for r in sel})
            idx = {e: i for i, e in enumerate(ev)}
            agg = np.zeros((len(ev), 2))
            for r in sel:
                agg[idx[r["event"]], 0] += 1
                agg[idx[r["event"]], 1] += (r["odds"] - 1.0) if r["hit"] else -1.0
            lo, hi = poisson_ci(agg, reps, seed)
            block.update({
                "matches": len(ev),
                "claimed": round(float(np.mean([r[name] for r in sel])), 4),
                "realised": round(float(np.mean([r["hit"] for r in sel])), 4),
                "roi": round(float(agg[:, 1].sum() / agg[:, 0].sum()), 4),
                "roi_ci95": [round(lo, 4), round(hi, 4)],
            })
        out[f"would_stake_{name}"] = block
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db-path", default="data/sofa.db")
    ap.add_argument("--calibration", default=None)
    ap.add_argument("--min-p", type=float, default=0.70)
    ap.add_argument("--bootstrap", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=20261005)
    ap.add_argument("--no-classes", action="store_true",
                    help="read every row unclassed (skips the cache scan)")
    ap.add_argument("--live-only", action="store_true",
                    help="only the live days' rows (run_date 2026-..., on the "
                    "index); every row the cap moved was one")
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    cal = Calibration.load(args.calibration) if args.calibration else Calibration.load()
    base = dataclasses.replace(cal, gap_shrink_k=0.0, cap_market_by_thin=True)
    capped = dataclasses.replace(base, cap_pool_by_neighbour=True)
    classes = {} if args.no_classes else load_event_classes(args.db_path)

    con = sqlite3.connect(f"file:{args.db_path}?mode=ro", uri=True)
    query = f"""select market, line, direction, actual_value, p_central, sport,
                       sofascore_event_id, run_date, offered_odds
                from sofa_settled_row
                where p_central >= ? and sport in ('football', 'tennis')
                  and sample_mean is not null and sample_sd is not null
                  and sample_size > 0 and actual_value is not null
                  and {friendly_exclusion_sql()}
                  {LIVE_TERM if args.live_only else ""}"""
    cache: dict[Cell, tuple[float, float, str, str] | None] = {}
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_cell: Counter[tuple[str, str, str, str]] = Counter()
    scanned = 0
    for (market, line, direction, actual, p, sport, event, run_date,
         odds) in con.execute(query, (args.min_p,)):
        if market.startswith("player_") or is_derived(market) \
                or not has_calibratable_model(market):
            continue
        scanned += 1
        klass = classes.get(event)
        cell: Cell = (klass, market, direction, sport, bucket_of(min(max(p, 0.0), 1.0)))
        if cell not in cache:
            cache.update(lookup_cells(base, capped, [cell]))
        got = cache[cell]
        if got is None:
            continue
        pool, cap, group, source = got
        hit = (actual > line) if direction == "OVER" else (actual < line)
        row = {"event": int(event), "hit": int(hit), "pool": pool, "capped": cap,
               "odds": float(odds) if odds and run_date != "cache-calibration"
               else None}
        groups[group].append(row)
        groups["all_pooled"].append(row)
        if cap < pool:
            # The rows the cap actually moves (the rest of hole_below is a
            # pool already below the market's own neighbour).
            groups["cap_acts"].append(row)
            groups["cap_acts:" + ("live" if run_date != "cache-calibration"
                                  else "cache")].append(row)
        b = cell[4]
        label = f"{klass + ':' if klass else ''}{direction_key(market, direction)}"
        by_cell[(group, label, f"{EDGES[b]:.3f}-{EDGES[b + 1]:.3f}", source)] += 1
    con.close()

    report = {
        "min_p": args.min_p, "scanned_rows": scanned,
        "groups": {g: summarise(rows, args.bootstrap, args.seed)
                   for g, rows in sorted(groups.items())},
        "top_cells": [
            {"group": g, "cell": c, "bucket": b, "capped_source": s, "rows": n}
            for (g, c, b, s), n in by_cell.most_common(40)
        ],
    }
    text = json.dumps(report, indent=1)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
