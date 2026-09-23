# ruff: noqa: E501  - report lines are tables.
"""Sweep CONFIDENCE's gates over settled history, scored out of sample.

The confidence path has five dials that decide what reaches the PDF:

    floor      the calibrated lower bound must be >= this        (today 0.70)
    price      confidence x odds must be >= this                 (today 1.00)
    disagree   p_central - devigged price must be <= this        (today 0.10)
    overround  the rung's two-sided margin must be <= this       (today 0.105)
    max_odds   the offered price must be <= this                 (today: none)

This script asks which setting would have done best, and - the part that
matters - how well "pick the best setting" itself does on a day it did not see.

Method
------
* Rows: `sofa_settled_row` for the live days (priced, devigged, WIN/LOSS),
  minus what CONFIDENCE refuses before any dial: derived markets, markets with
  no model, odds under MIN_ODDS.
* Confidence: a Wilson lower bound per (market | sport pool | global) bucket,
  fitted on the cache replay plus the TRAINING days only, on the stored
  `p_central` - the number CONFIDENCE actually looks up. Buckets are 0.05 wide
  below 0.60 (production uses one flat 0-0.60 bucket, which hands a 0.10 and a
  0.55 claim the same 0.326 and lets every price above 3.07 look EV-positive;
  a sweep on that curve would "find" long shots that are an artifact of it).
* Overround: rebuilt from the price and the power-devigged probability,
  because the other side's price is not stored: q^k = p gives k, and the other
  side is (1 - p)^(1/k).
* Leave-one-day-out: for every held-out day the curve is refitted without it
  and every combination is scored on it. A combination's out-of-sample ROI is
  the pooled profit over the pooled stake of its held-out days.
* Nested selection: on each held-out day, the combination is chosen on the
  OTHER days only and then scored on that day. That number is what tuning the
  dials is honestly worth; the best in-sample ROI is not.
* Flat stake of 1 per row; rows of one match are correlated, so intervals are a
  bootstrap over matches, not rows.

Not reproduced (they need raw samples the settled table does not keep): the
shape gates LINE_BEYOND_SAMPLE / MODE_LOSES / THIN / STALE / SEASON, vetoes,
the kickoff clock and the price-age gate. The p_central on each day is the
model as it was that day; later model changes (e.g. 82cf681e) are not
replayed. The disagreement gate reads p_central for every row: production
reads `sample_frequency` instead for tennis empirical rows, and the settled
table does not store it, so the TENNIS figures here come from a looser
disagreement gate than the one that ships - treat them as optimistic.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/sweep_confidence_gates.py
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
import random
import sqlite3
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa.confidence import MIN_ODDS_FOR_CEILING, is_derived  # noqa: E402
from bet.sofa.engine import has_calibratable_model  # noqa: E402

EDGES = [
    0.0, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55,
    0.60, 0.70, 0.75, 0.80, 0.825, 0.85, 0.875, 0.90, 0.925, 0.95, 1.01,
]
MIN_MARKET_BUCKET = 400
MIN_POOL_BUCKET = 200

FLOORS = [round(0.50 + 0.02 * i, 2) for i in range(21)]  # 0.50 .. 0.90
PRICES = [round(0.96 + 0.02 * i, 2) for i in range(9)]  # 0.96 .. 1.12
DISAGREE = [0.05, 0.10, 0.15, 0.20, 0.30, None]
OVERROUND = [0.08, 0.095, 0.105, 0.12, None]
MAX_ODDS = [1.6, 2.0, 3.0, None]
PRODUCTION = (0.70, 1.00, 0.10, 0.105, None)


@dataclass(frozen=True)
class Row:
    day: str
    event: int
    sport: str
    market: str
    p: float  # stored p_central
    market_p: float  # devigged
    odds: float
    won: bool


def bucket_of(p: float, edges: list[float] = EDGES) -> int:
    for i in range(len(edges) - 1):
        if edges[i] <= p < edges[i + 1]:
            return i
    return len(edges) - 2


def wilson_lo(k: int, n: int, z: float = 1.959964) -> float:
    if n == 0:
        return 0.0
    ph = k / n
    d = 1 + z * z / n
    c = (ph + z * z / (2 * n)) / d
    m = z * math.sqrt(ph * (1 - ph) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - m)


def overround_from_devig(odds: float, fair_p: float) -> float | None:
    """The two-sided margin, from one price and its power-devigged probability.

    Power devig solves q_a^k + q_b^k = 1 with q = 1/odds, and returns
    p_a = q_a^k. So k = ln p_a / ln q_a, and q_b = (1 - p_a)^(1/k).
    """
    q = 1.0 / odds
    if not (0.0 < q < 1.0 and 0.0 < fair_p < 1.0):
        return None
    k = math.log(fair_p) / math.log(q)
    if k <= 0:
        return None
    q_other = float((1.0 - fair_p) ** (1.0 / k))
    return q + q_other - 1.0


class Curve:
    """Per-market curve, else the sport pool, else global - as Calibration."""

    def __init__(self, hits: list[tuple[str, str, float, bool]]) -> None:
        by_m: dict[str, dict[int, list[int]]] = defaultdict(lambda: defaultdict(list))
        by_s: dict[str, dict[int, list[int]]] = defaultdict(lambda: defaultdict(list))
        glob: dict[int, list[int]] = defaultdict(list)
        for market, sport, p, won in hits:
            b = bucket_of(p)
            by_m[market][b].append(int(won))
            by_s[sport][b].append(int(won))
            glob[b].append(int(won))

        def fit(c: dict[int, list[int]], floor: int) -> dict[int, float]:
            return {
                b: wilson_lo(sum(v), len(v)) for b, v in c.items() if len(v) >= floor
            }

        self.market = {m: fit(c, MIN_MARKET_BUCKET) for m, c in by_m.items()}
        self.sport = {s: fit(c, MIN_POOL_BUCKET) for s, c in by_s.items()}
        self.glob = fit(glob, MIN_POOL_BUCKET)

    def lookup(self, market: str, sport: str, p: float) -> float | None:
        b = bucket_of(p)
        own = self.market.get(market, {})
        if b in own:
            return own[b]
        # Never borrow a pool above the market's own measured range.
        if own and b > max(own):
            return None
        if b in self.sport.get(sport, {}):
            return self.sport[sport][b]
        return self.glob.get(b)


Combo = tuple[float, float, float | None, float | None, float | None]


def passes(
    conf: float, row: Row, overround: float | None, combo: Combo
) -> bool:
    floor, price, disagree, max_over, max_odds = combo
    if conf < floor or conf * row.odds < price:
        return False
    if disagree is not None and row.p - row.market_p > disagree:
        return False
    if max_over is not None and (overround is None or overround > max_over):
        return False
    return not (max_odds is not None and row.odds > max_odds)


def profit(row: Row) -> float:
    return row.odds - 1.0 if row.won else -1.0


def load(db: str) -> tuple[list[Row], list[tuple[str, str, float, bool]]]:
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    live: list[Row] = []
    cache: list[tuple[str, str, float, bool]] = []
    q = (
        "select run_date, sofascore_event_id, sport, market, p_central, market_p,"
        " offered_odds, outcome from sofa_settled_row where outcome in ('WIN','LOSS')"
    )
    for day, ev, sport, market, p, mp, odds, oc in con.execute(q):
        if is_derived(market) or not has_calibratable_model(market) or p is None:
            continue
        if day == "cache-calibration":
            cache.append((market, sport, float(p), oc == "WIN"))
            continue
        if not str(day).startswith("2026-") or odds is None or mp is None:
            continue
        if odds < MIN_ODDS_FOR_CEILING:
            continue
        live.append(
            Row(day, int(ev), sport, market, float(p), float(mp), float(odds), oc == "WIN")
        )
    return live, cache


def score(
    rows: list[Row], confs: list[float | None], overs: list[float | None],
    combos: list[Combo],
) -> dict[Combo, tuple[int, float]]:
    """(bets, profit) per combination."""
    out: dict[Combo, tuple[int, float]] = {}
    usable = [
        (r, c, o) for r, c, o in zip(rows, confs, overs, strict=True) if c is not None
    ]
    for combo in combos:
        n = 0
        pr = 0.0
        for r, c, o in usable:
            if passes(c, r, o, combo):
                n += 1
                pr += profit(r)
        out[combo] = (n, pr)
    return out


def bootstrap_roi(
    rows: list[Row], sims: int = 2000, seed: int = 7
) -> tuple[float, float] | None:
    """95% interval of ROI, resampling whole matches."""
    by_ev: dict[int, list[Row]] = defaultdict(list)
    for r in rows:
        by_ev[r.event].append(r)
    evs = list(by_ev)
    if len(evs) < 5:
        return None
    rng = random.Random(seed)
    rois = []
    for _ in range(sims):
        n = 0
        pr = 0.0
        for _ in evs:
            for r in by_ev[evs[rng.randrange(len(evs))]]:
                n += 1
                pr += profit(r)
        if n:
            rois.append(pr / n)
    rois.sort()
    return rois[int(0.025 * len(rois))], rois[int(0.975 * len(rois)) - 1]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db-path", default="data/sofa.db")
    ap.add_argument("--sport", choices=["all", "football", "tennis"], default="all")
    ap.add_argument("--min-bets", type=int, default=150)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    live, cache = load(args.db_path)
    if args.sport != "all":
        live = [r for r in live if r.sport == args.sport]
    per_day_n = Counter(r.day for r in live)
    days = sorted(d for d, n in per_day_n.items() if n >= 200)
    live = [r for r in live if r.day in days]
    combos: list[Combo] = list(
        itertools.product(FLOORS, PRICES, DISAGREE, OVERROUND, MAX_ODDS)
    )
    print(f"rows {len(live)}  days {days}  combos {len(combos)}", file=sys.stderr)

    per_day: dict[str, dict[Combo, tuple[int, float]]] = {}
    held_rows: dict[str, tuple[list[Row], list[float | None], list[float | None]]] = {}
    for day in days:
        train = cache + [
            (r.market, r.sport, r.p, r.won) for r in live if r.day != day
        ]
        curve = Curve(train)
        test = [r for r in live if r.day == day]
        confs = [curve.lookup(r.market, r.sport, r.p) for r in test]
        overs = [overround_from_devig(r.odds, r.market_p) for r in test]
        per_day[day] = score(test, confs, overs, combos)
        held_rows[day] = (test, confs, overs)
        print(f"  scored held-out {day}: {len(test)} rows", file=sys.stderr)

    def pooled(combo: Combo, use: list[str]) -> tuple[int, float, int]:
        n = sum(per_day[d][combo][0] for d in use)
        pr = sum(per_day[d][combo][1] for d in use)
        active = sum(1 for d in use if per_day[d][combo][0] > 0)
        return n, pr, active

    def selected(combo: Combo, day: str) -> list[Row]:
        test, confs, overs = held_rows[day]
        return [
            r for r, c, o in zip(test, confs, overs, strict=True)
            if c is not None and passes(c, r, o, combo)
        ]

    # 1. Out-of-sample table.
    table = []
    for combo in combos:
        n, pr, active = pooled(combo, days)
        if n >= args.min_bets and active >= min(3, len(days)):
            table.append((pr / n, n, active, combo))
    table.sort(key=lambda t: -t[0])

    # 2. Nested: choose on the other days, score on the held-out one.
    nested_n = 0
    nested_pr = 0.0
    nested_rows: list[Row] = []
    picks = {}
    for day in days:
        others = [d for d in days if d != day]
        best = None
        for combo in combos:
            n, pr, active = pooled(combo, others)
            if n >= args.min_bets * len(others) / len(days) and active >= min(
                2, len(others)
            ):
                if best is None or pr / n > best[0]:
                    best = (pr / n, combo)
        if best is None:
            continue
        picks[day] = best[1]
        n, pr = per_day[day][best[1]]
        nested_n += n
        nested_pr += pr
        nested_rows += selected(best[1], day)

    prod_n, prod_pr, prod_active = pooled(PRODUCTION, days)
    prod_rows = [r for d in days for r in selected(PRODUCTION, d)]

    def fmt(c: Combo) -> str:
        f, p, d, o, m = c
        return (
            f"floor {f:.2f} price {p:.2f} disagree {d if d is not None else '-'} "
            f"overround {o if o is not None else '-'} max_odds {m if m is not None else '-'}"
        )

    print(f"\n== sport={args.sport}  held-out days={len(days)}  min_bets={args.min_bets}")
    print("\nPRODUCTION  ", fmt(PRODUCTION))
    if prod_n:
        ci = bootstrap_roi(prod_rows)
        print(
            f"   bets {prod_n}  ROI {prod_pr / prod_n:+.2%}  days active {prod_active}"
            + (f"  95% CI {ci[0]:+.1%}..{ci[1]:+.1%}" if ci else "  (too few matches for a CI)")
        )
    else:
        print("   no bets")
    print("\nNESTED (choose on other days, score on held-out day) - the honest number")
    if nested_n:
        ci = bootstrap_roi(nested_rows)
        print(
            f"   bets {nested_n}  ROI {nested_pr / nested_n:+.2%}"
            + (f"  95% CI {ci[0]:+.1%}..{ci[1]:+.1%}" if ci else "")
        )
        for d, c in picks.items():
            n, pr = per_day[d][c]
            print(f"   {d}: picked {fmt(c)} -> bets {n} ROI {pr / n if n else 0:+.2%}")
    print("\nTOP 15 by pooled out-of-sample ROI (each day scored on a curve that never saw it)")
    for roi, n, active, combo in table[:15]:
        per = "  ".join(
            f"{d[5:]}:{per_day[d][combo][0]}/{per_day[d][combo][1] / per_day[d][combo][0]:+.0%}"
            if per_day[d][combo][0] else f"{d[5:]}:0"
            for d in days
        )
        print(f"   {roi:+.2%}  n={n:5d}  {fmt(combo)}   [{per}]")
    print(f"\ncombinations meeting min_bets: {len(table)} of {len(combos)};"
          f" with ROI > 0: {sum(1 for t in table if t[0] > 0)}")

    # One-dial marginals around production, to see which dial moves ROI.
    print("\nONE DIAL AT A TIME (others at production)")
    names = ["floor", "price", "disagree", "overround", "max_odds"]
    grids: list[list[Any]] = [FLOORS, PRICES, DISAGREE, OVERROUND, MAX_ODDS]
    for i, (name, grid) in enumerate(zip(names, grids, strict=True)):
        cells = []
        for v in grid:
            dial: list[Any] = list(PRODUCTION)
            dial[i] = v
            n, pr, _ = pooled(tuple(dial), days)
            cells.append(f"{v if v is not None else '-'}:{n}/{pr / n:+.1%}" if n else f"{v}:0")
        print(f"   {name:9s} " + "  ".join(cells))

    if args.out:
        Path(args.out).write_text(
            json.dumps(
                {
                    "sport": args.sport,
                    "days": days,
                    "production": {"bets": prod_n, "profit": prod_pr},
                    "nested": {"bets": nested_n, "profit": nested_pr,
                               "picks": {d: list(c) for d, c in picks.items()}},
                    "top": [
                        {"roi": roi, "bets": n, "combo": list(c)}
                        for roi, n, _, c in table[:50]
                    ],
                },
                indent=1,
            ),
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
