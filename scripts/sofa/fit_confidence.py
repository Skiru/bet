#!/usr/bin/env python3
"""Fit the confidence calibration: what the model says -> what actually happens.

This is a DIFFERENT question from K_PRICE, and the distinction is the whole
point of the confidence view. K_PRICE asks "does the model beat the price"; the
answer measured on 6,187 priced rows is no (Brier 0.2067 against the price's
0.1845). Calibration asks "when the model says 0.88, how often does it happen",
and the answer over 1,868,474 settled rows is: to within 0.3 pp, exactly 0.88 —
right up to about 0.90, above which the model runs out of resolution and tops
out near 0.92 whatever it claims.

An operator who accepts a shaded price is not asking the first question. He is
asking the second, and it needs its own fitted table rather than a reuse of the
reliability curve, which is bucketed on `p_central` for a different purpose and
only ever emits a correction where a 95% interval clears zero.

Usage:
    python -m scripts.sofa.fit_confidence --db-path data/sofa.db
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa.engine import (  # noqa: E402
    calc_p_central_nb_raw,
    calc_p_central_raw,
    predictive_sd,
    support_floor_for,
    uses_empirical_frequency,
    uses_negative_binomial,
    uses_poisson_floor,
    winning_boundary,
)

# Buckets are narrow at the top because that is where the operator lives and
# where the model stops being linear. Below 0.60 the confidence view does not
# look, so the grid does not waste resolution there.
EDGES = [0.0, 0.60, 0.70, 0.75, 0.80, 0.825, 0.85, 0.875, 0.90, 0.925, 0.95, 1.01]

# A per-market bucket below this is noise; it falls back to the pooled curve.
MIN_MARKET_BUCKET = 400
MIN_POOLED_BUCKET = 200


def bucket_of(p: float) -> int:
    for i in range(len(EDGES) - 1):
        if EDGES[i] <= p < EDGES[i + 1]:
            return i
    return len(EDGES) - 2


def wilson_lo(k: int, n: int, z: float = 1.959964) -> float:
    if n == 0:
        return 0.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - m)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db-path", default="data/sofa.db")
    ap.add_argument("--out", default="config/sofa_confidence_calibration.json")
    args = ap.parse_args()

    con = sqlite3.connect(args.db_path)
    rows = con.execute(
        """select market, line, direction, sample_size, sample_mean, sample_sd,
                  actual_value
           from sofa_settled_row
           where sample_mean is not null and sample_sd is not null
             and sample_size > 0 and actual_value is not null"""
    )

    per_market: dict[str, dict[int, list[int]]] = defaultdict(lambda: defaultdict(list))
    pooled: dict[int, list[int]] = defaultdict(list)
    scored = 0
    for market, line, direction, n, mean, sd, actual in rows:
        if uses_empirical_frequency(market) or not uses_poisson_floor(market):
            continue
        psd = predictive_sd(sd * sd, mean, n, apply_poisson_floor=True)
        boundary = winning_boundary(line, direction)
        if uses_negative_binomial(market):
            p = calc_p_central_nb_raw(mean, psd, boundary, direction)
        else:
            p = calc_p_central_raw(
                mean, psd, boundary, direction, support_floor_for(market)
            )
        p = min(max(p, 0.0), 1.0)
        hit = 1 if ((actual > line) if direction == "OVER" else (actual < line)) else 0
        b = bucket_of(p)
        per_market[market][b].append(hit)
        pooled[b].append(hit)
        scored += 1

    def curve(counts: dict[int, list[int]], floor: int) -> dict[str, dict]:
        out: dict[str, dict] = {}
        for b, hits in sorted(counts.items()):
            if len(hits) < floor:
                continue
            k, n = sum(hits), len(hits)
            out[f"{EDGES[b]:.3f}-{EDGES[b + 1]:.3f}"] = {
                "n": n,
                "realised": round(k / n, 4),
                # The operator is told the LOWER bound, not the point estimate.
                # A confidence view that quotes its own best case is the same
                # mistake as a coupon that ranks by surplus.
                "realised_lo95": round(wilson_lo(k, n), 4),
            }
        return out

    doc = {
        "_doc": (
            "What the model's probability turns into in practice. Fitted by "
            "scripts/sofa/fit_confidence.py. A market with too few rows in a "
            "bucket falls back to the pooled curve; a bucket absent from both "
            "means the confidence view refuses the row rather than guessing."
        ),
        "fitted_from": {"db_path": args.db_path, "scored_rows": scored},
        "min_market_bucket": MIN_MARKET_BUCKET,
        "pooled": curve(pooled, MIN_POOLED_BUCKET),
        "by_market": {
            m: c
            for m, counts in per_market.items()
            if (c := curve(counts, MIN_MARKET_BUCKET))
        },
    }
    Path(args.out).write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "stage": "FIT_CONFIDENCE",
                "verdict": "OK",
                "metrics": {
                    "scored_rows": scored,
                    "markets": len(doc["by_market"]),
                    "pooled_buckets": len(doc["pooled"]),
                },
                "output_path": args.out,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
