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
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa.confidence import (  # noqa: E402
    CLASS_WOMEN,
    direction_key,
    match_class,
)
from bet.sofa.engine import (  # noqa: E402
    NORMAL_NON_COUNT_METRICS,
    calc_p_central_nb_raw,
    calc_p_central_raw,
    predictive_sd,
    support_floor_for,
    uses_empirical_frequency,
    uses_negative_binomial,
    uses_poisson_floor,
    winning_boundary,
)
from bet.sofa.resolve import sofascore_gender  # noqa: E402

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


def event_class(event: dict[str, Any]) -> str | None:
    """The match class of one cached event, as run_confidence reads it."""
    tournament = event.get("tournament") or {}
    sport = ((tournament.get("category") or {}).get("sport") or {}).get("slug")
    if sport == "football":
        return CLASS_WOMEN if sofascore_gender(event) == "W" else None
    if sport == "tennis":
        # The category name only - what run_confidence reads. The players'
        # gender field would put Juniors girls (485 cached events) in
        # tennis_women here while the run cannot tell them from boys.
        category = str((tournament.get("category") or {}).get("name") or "")
        return match_class("tennis", category)
    return None


def load_event_classes(db_path: str) -> dict[int, str]:
    """sofascore_event_id -> match class, for the football events in the cache.

    Only CLASS_WOMEN today. Read with resolve.sofascore_gender - the teams'
    own gender field first, the competition name only as a fallback - over
    every cached listing, which is where both the replayed and the live rows'
    events live.
    """
    out: dict[int, str] = {}
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        has_listings = con.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' "
            "AND name = 'sofa_entity_events'"
        ).fetchone()
        if has_listings is None:
            return out  # no cache: no class is known, every row is unclassed
        for (events_json,) in con.execute(
            "SELECT events_json FROM sofa_entity_events WHERE kind = 'last'"
        ):
            for event in json.loads(events_json).get("events", []):
                eid = event.get("id")
                if isinstance(eid, int) and eid not in out:
                    klass = event_class(event)
                    if klass is not None:
                        out[eid] = klass
    finally:
        con.close()
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db-path", default="data/sofa.db")
    ap.add_argument("--out", default="config/sofa_confidence_calibration.json")
    ap.add_argument(
        "--classes-only", action="store_true",
        help="refit only the by_class section of --out and keep every other "
        "curve byte-for-byte (a class curve can be added between two builds "
        "of one day without moving any leg that is not in the class)",
    )
    args = ap.parse_args()
    classes = load_event_classes(args.db_path)

    con = sqlite3.connect(args.db_path)
    # A settled table without the event id (hand-built test fixtures) scores
    # exactly as before and classes nothing.
    columns = {r[1] for r in con.execute("PRAGMA table_info(sofa_settled_row)")}
    event_col = "sofascore_event_id" if "sofascore_event_id" in columns else "NULL"
    rows = con.execute(
        f"""select market, line, direction, sample_size, sample_mean, sample_sd,
                  actual_value, p_central, sport, {event_col}
           from sofa_settled_row
           where sample_mean is not null and sample_sd is not null
             and sample_size > 0 and actual_value is not null"""
    )

    per_market: dict[str, dict[int, list[int]]] = defaultdict(lambda: defaultdict(list))
    # Per market AND direction. OVER and UNDER of one rung are complements, so
    # a curve that pools them describes neither: measured 2026-09-25 in the
    # 0.70-0.75 bucket, goals_for OVER realised 0.646 (n=20,396) against UNDER
    # 0.817, and the pooled 0.7177 put "Pasto to score O0.5 @1.44" on the PDF
    # at x=1.03 when its own direction said x~0.93. The coupon is mostly
    # UNDER, so the pooled curve is an UNDER curve that OVER legs borrow.
    per_market_direction: dict[str, dict[int, list[int]]] = defaultdict(
        lambda: defaultdict(list)
    )
    pooled: dict[int, list[int]] = defaultdict(list)
    # Pooled per sport. A global pool is 95% football counting markets, so a
    # tennis metric borrowing it borrows football's shape — which is how
    # `sets_total` read 0.856 off 64,790 rows that were almost all goals and
    # corners. Silence about tennis is not the same as knowledge about it.
    pooled_by_sport: dict[str, dict[int, list[int]]] = defaultdict(
        lambda: defaultdict(list)
    )
    # Per match class (CLASS_WOMEN): the same three curves over the class's
    # rows only. Measured 2026-09-30 on the cache replay, football goals at
    # p 0.80-0.85: men realised 0.806 (n=655,622), women 0.792 (n=67,531);
    # corners at 0.90-0.925 0.903 against 0.874. A women's leg read the
    # men-dominated curve and was printed 1.5-3.5 pp too confident.
    by_class_market: dict[str, dict[str, dict[int, list[int]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(list)))
    by_class_direction: dict[str, dict[str, dict[int, list[int]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(list)))
    by_class_sport: dict[str, dict[str, dict[int, list[int]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(list)))
    scored = 0
    for (market, line, direction, n, mean, sd, actual, stored_p, sport,
         event_id) in rows:
        if uses_empirical_frequency(market):
            # These have no distribution to recompute from — `p_central` IS
            # the sample's own hit rate, and the sheet already stored it. Until
            # 2026-09-21 the loop skipped them, so they had no curve, and
            # run_confidence refused every one of them as NOT_IN_CALIBRATION_
            # FIT. That banned `games_won_for` — the single largest tennis
            # market, 1084 rows on a Monday sheet and 9,286 settled — from the
            # path that produces the coupon, while the VALUE-singles path was
            # made of almost nothing else.
            #
            # Banning was the wrong answer to a real problem: the raw
            # frequency IS overconfident at the top (measured on those 9,286
            # rows, a claimed 0.95 realises 0.728). That is what a calibration
            # curve is for. Fitted, the top bucket caps itself at ~0.73 and
            # the 0.811-against-odds-of-20.0 leg that motivated the ban cannot
            # reach the floor any more.
            if stored_p is None:
                continue
            p = stored_p
        elif market in NORMAL_NON_COUNT_METRICS:
            # A floorless normal (no Poisson floor, no support floor), which is
            # run_sheet's estimator for these. Centred on the raw sample mean,
            # like every count branch below: the fit has never replayed the
            # prior / ladder shrink, so for tennis this p is the sample's own,
            # not the shrunk p_central the stage looks up - the same
            # approximation the count markets have always carried. Until
            # 2026-09-23 these fell into the branch below and were skipped.
            psd = predictive_sd(sd * sd, mean, n, apply_poisson_floor=False)
            p = calc_p_central_raw(
                mean, psd, winning_boundary(line, direction), direction, None
            )
        elif not uses_poisson_floor(market):
            # Neither a count, an empirical frequency, nor a modelled non-count
            # (the xG pair): no model at all.
            continue
        else:
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
        klass = classes.get(event_id)
        if klass is not None:
            by_class_market[klass][market][b].append(hit)
            by_class_direction[klass][direction_key(market, direction)][b].append(hit)
            by_class_sport[klass][sport][b].append(hit)
        if args.classes_only:
            scored += 1
            continue
        per_market[market][b].append(hit)
        per_market_direction[direction_key(market, direction)][b].append(hit)
        pooled[b].append(hit)
        if sport:
            pooled_by_sport[sport][b].append(hit)
        scored += 1

    def curve(
        counts: dict[int, list[int]], floor: int
    ) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
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

    by_direction = {
        m: c
        for m, counts in per_market_direction.items()
        if (c := curve(counts, MIN_MARKET_BUCKET))
    }
    by_class = {
        klass: {
            "by_market": {
                m: c for m, counts in by_class_market[klass].items()
                if (c := curve(counts, MIN_MARKET_BUCKET))
            },
            "by_market_direction": {
                m: c for m, counts in by_class_direction[klass].items()
                if (c := curve(counts, MIN_MARKET_BUCKET))
            },
            "pooled_by_sport": {
                sp: c for sp, counts in by_class_sport[klass].items()
                if (c := curve(counts, MIN_POOLED_BUCKET))
            },
        }
        for klass in sorted(by_class_sport)
    }
    if args.classes_only:
        prior: dict[str, Any] = json.loads(Path(args.out).read_text(encoding="utf-8"))
        prior["by_class"] = by_class
        prior["by_class_fitted_from"] = {
            "db_path": args.db_path, "scored_rows": scored,
            "classes": {k: len(v["by_market"]) for k, v in by_class.items()},
        }
        Path(args.out).write_text(json.dumps(prior, indent=1) + "\n", encoding="utf-8")
        print(json.dumps({
            "stage": "FIT_CONFIDENCE", "verdict": "OK", "mode": "classes-only",
            "metrics": prior["by_class_fitted_from"], "output_path": args.out,
        }))
        return 0
    doc: dict[str, Any] = {
        "_doc": (
            "What the model's probability turns into in practice. Fitted by "
            "scripts/sofa/fit_confidence.py. A market with too few rows in a "
            "bucket falls back to its SPORT's pooled curve, then the global "
            "one; a bucket absent from all three means the confidence view "
            "refuses the row rather than guessing. A market is never served "
            "from a pool ABOVE the top of its own measured range - see "
            "Calibration.realised. by_market_direction is the same curve "
            "split by OVER/UNDER and is read first; the two directions of one "
            "rung are complements, so the pooled curve describes neither."
        ),
        "fitted_from": {"db_path": args.db_path, "scored_rows": scored},
        "min_market_bucket": MIN_MARKET_BUCKET,
        "pooled": curve(pooled, MIN_POOLED_BUCKET),
        "pooled_by_sport": {
            sp: c
            for sp, counts in pooled_by_sport.items()
            if (c := curve(counts, MIN_POOLED_BUCKET))
        },
        "by_market": {
            m: c
            for m, counts in per_market.items()
            if (c := curve(counts, MIN_MARKET_BUCKET))
        },
        "by_market_direction": by_direction,
        "by_class": by_class,
        "by_class_fitted_from": {
            "db_path": args.db_path, "scored_rows": scored,
            "classes": {k: len(v["by_market"]) for k, v in by_class.items()},
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
                    "market_directions": len(by_direction),
                    "pooled_buckets": len(doc["pooled"]),
                    "pooled_by_sport": {
                        sp: len(c) for sp, c in doc["pooled_by_sport"].items()
                    },
                },
                "output_path": args.out,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
