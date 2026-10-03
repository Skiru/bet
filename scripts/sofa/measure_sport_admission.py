#!/usr/bin/env python3
"""What would the main coupon's rule have printed in a measured sport?

Replays the CONFIDENCE rule football and tennis live under - a calibrated
confidence (the Wilson 95% lower bound of what the claimed probability's
bucket realised, `fit_confidence.EDGES`), a floor, confidence x odds against
the profile's bar, MAX_DISAGREEMENT against the devigged price and the
singles' ladder-margin cap - on graded shadow lines of hockey, basketball,
volleyball or CS2 (JSONL rows with date, game, family, odds, overround,
p_model, p_price and y, as written by measure_score_model.py --rows-out).

The curve is fitted on graded rows of EARLIER dates only (an expanding
window: the first date is never a test date), pooled over the sport's
families, a bucket used only with at least `--min-bucket` rows. The claim is
the model's probability, the devigged price, or a blend. Reported per test
date and pooled: printed legs, games, hit rate, flat-stake ROI at the offered
odds, and a 95% interval for the ROI from a bootstrap over games.

A measurement. It writes nothing the pipeline reads, and its result is no
admission: the sports stay out of the coupon (CLAUDE.md) until the operator
decides on a pre-registered test.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_sport_admission.py \\
        --rows hockey.rows.jsonl --claim model [--profile wariant]
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# fit_confidence.EDGES, copied so this script imports nothing that reads config
EDGES = (0.0, 0.60, 0.70, 0.75, 0.80, 0.825, 0.85, 0.875, 0.90, 0.925, 0.95, 1.01)
MAX_DISAGREEMENT = 0.10  # confidence.MAX_DISAGREEMENT
BOOTSTRAP = 2000


@dataclass(frozen=True)
class Rule:
    floor: float
    min_ev: float | None  # None: confidence x odds > 1 strictly
    max_overround: float


RULES = {
    "standard": Rule(0.70, None, 0.105),
    "wariant": Rule(0.65, 0.90, 0.15),
}


def wilson_lo(k: float, n: int, z: float = 1.959964) -> float:
    if n == 0:
        return 0.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - m)


def bucket_of(p: float) -> int:
    for i in range(len(EDGES) - 1):
        if EDGES[i] <= p < EDGES[i + 1]:
            return i
    return len(EDGES) - 2


def claim_of(row: dict[str, Any], claim: str) -> float:
    if claim == "model":
        return float(row["p_model"])
    if claim == "price":
        return float(row["p_price"])
    w = float(claim.split(":", 1)[1])  # "blend:0.25"
    return w * float(row["p_model"]) + (1 - w) * float(row["p_price"])


def fit_curve(
    rows: Sequence[dict[str, Any]], claim: str, min_bucket: int
) -> dict[int, tuple[float, int]]:
    """bucket -> (realised lower 95%, n), only buckets with min_bucket rows."""
    hits: dict[int, list[float]] = defaultdict(list)
    for r in rows:
        hits[bucket_of(claim_of(r, claim))].append(float(r["y"]))
    return {b: (wilson_lo(sum(ys), len(ys)), len(ys))
            for b, ys in hits.items() if len(ys) >= min_bucket}


def admitted(
    row: dict[str, Any], curve: dict[int, tuple[float, int]], claim: str, rule: Rule
) -> float | None:
    """The row's confidence when the rule prints it, else None."""
    c = claim_of(row, claim)
    entry = curve.get(bucket_of(c))
    if entry is None:
        return None
    conf = entry[0]
    odds = float(row["odds"])
    if conf < rule.floor:
        return None
    if rule.min_ev is None:
        if conf * odds <= 1.0:
            return None
    elif round(conf * odds, 9) < rule.min_ev:
        return None
    if c - float(row["p_price"]) > MAX_DISAGREEMENT:
        return None
    over = row.get("overround")
    if over is None or float(over) > rule.max_overround:
        return None
    return conf


def _line_key(r: dict[str, Any]) -> tuple[Any, ...]:
    return (r["game"], r["family"], r.get("period"), r.get("line"), r.get("subject"))


def fill_overround(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rows graded before the settle recorded `overround` get it from the
    line's own sides (sum of 1/odds - 1); a line with one graded side keeps
    None, and the margin cap then refuses it."""
    groups: dict[tuple[Any, ...], list[float]] = defaultdict(list)
    for r in rows:
        groups[_line_key(r)].append(float(r["odds"]))
    out = []
    for r in rows:
        if r.get("overround") is None:
            odds = groups[_line_key(r)]
            if len(odds) >= 2:
                r = dict(r, overround=sum(1.0 / o for o in odds) - 1.0)
        out.append(r)
    return out


def replay(
    rows: Sequence[dict[str, Any]], claim: str, rule: Rule, min_bucket: int
) -> list[dict[str, Any]]:
    """Printed legs over every date but the first, curve from earlier dates;
    the best (confidence x odds) side of a line when both would print."""
    dates = sorted({str(r["date"]) for r in rows})
    printed: list[dict[str, Any]] = []
    for d in dates[1:]:
        curve = fit_curve([r for r in rows if str(r["date"]) < d], claim, min_bucket)
        best: dict[tuple[Any, ...], dict[str, Any]] = {}
        for r in rows:
            if str(r["date"]) != d:
                continue
            conf = admitted(r, curve, claim, rule)
            if conf is None:
                continue
            key = _line_key(r)
            leg = dict(r, confidence=conf)
            old = best.get(key)
            if old is None or conf * float(r["odds"]) > old["confidence"] * float(
                    old["odds"]):
                best[key] = leg
        printed.extend(best.values())
    return printed


def roi_interval(
    legs: Sequence[dict[str, Any]], seed: int = 7, n: int = BOOTSTRAP
) -> tuple[float, float, float] | None:
    """Flat-stake ROI and its 95% interval, resampling whole games."""
    if not legs:
        return None
    by_game: dict[str, list[float]] = defaultdict(list)
    for leg in legs:
        by_game[str(leg["game"])].append(
            float(leg["odds"]) - 1.0 if leg["y"] else -1.0)
    games = list(by_game)
    total = sum(sum(v) for v in by_game.values()) / len(legs)
    rng = random.Random(seed)
    stats = []
    for _ in range(n):
        pick = [by_game[games[rng.randrange(len(games))]] for _ in games]
        s = sum(sum(v) for v in pick)
        c = sum(len(v) for v in pick)
        stats.append(s / c)
    stats.sort()
    return total, stats[int(0.025 * n)], stats[int(0.975 * n)]


def summary(legs: Sequence[dict[str, Any]]) -> dict[str, Any]:
    ci = roi_interval(legs)
    return {
        "legs": len(legs), "games": len({leg["game"] for leg in legs}),
        "hit": round(sum(leg["y"] for leg in legs) / len(legs), 3) if legs else None,
        "mean_conf": round(sum(leg["confidence"] for leg in legs) / len(legs), 3)
        if legs else None,
        "mean_fair_p": round(sum(leg["p_price"] for leg in legs) / len(legs), 3)
        if legs else None,
        "roi": [round(x, 4) for x in ci] if ci else None,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--rows", required=True)
    ap.add_argument("--claim", default="model",
                    help="model | price | blend:<w> (w on the model)")
    ap.add_argument("--profile", choices=sorted(RULES), default="standard")
    ap.add_argument("--min-bucket", type=int, default=200)
    ap.add_argument("--family", action="append", default=None)
    args = ap.parse_args()
    rows = [json.loads(line) for line in
            Path(args.rows).read_text(encoding="utf-8").splitlines() if line]
    if args.family:
        rows = [r for r in rows if r["family"] in set(args.family)]
    rows = fill_overround(rows)
    legs = replay(rows, args.claim, RULES[args.profile], args.min_bucket)
    by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for leg in legs:
        by_date[str(leg["date"])].append(leg)
    print(json.dumps({
        "rows": args.rows, "claim": args.claim, "profile": args.profile,
        "test_dates": sorted({str(r["date"]) for r in rows})[1:],
        "all": summary(legs),
        "by_date": {d: summary(v) for d, v in sorted(by_date.items())},
        "by_family": {f: summary([g for g in legs if g["family"] == f])
                      for f in sorted({g["family"] for g in legs})},
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
