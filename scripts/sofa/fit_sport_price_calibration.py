#!/usr/bin/env python3
"""Fit the price recalibration of the hockey and basketball sport coupons.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/fit_sport_price_calibration.py \\
        --before 2026-10-05 [--sports hockey basketball] [--dry-run]

Superbet's devigged price over-rates favourites in hockey and basketball by
3-4 pp (data/analysis_2026-10-04_shadow/RAPORT.md, section 2). The operator
ordered on 2026-10-05 that those two sport coupons print an honest
probability: y ~ a + c * logit(fair_p), fitted by maximum likelihood on every
graded non-player shadow line of the settled days strictly before --before
(runs/sofa/shadow/<sport>/<d>/settled.json). Leave-one-day-out is reported
beside the fit: the c of every held-out fit, and the out-of-sample Brier
change on lines with fair_p >= 0.70 (the coupon's own region). A measured
correction of the printed probability, not a source of edge - the report
measured ROI unchanged.

Writes config/sofa_sport_price_calibration.json (read by
bet.sofa.sport_coupon.load_price_calibration). Never between the stages of a
day: a coupon built on one fit and rebuilt on another is two rules.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import sport_coupon as sc  # noqa: E402
from bet.sofa.config import config_path  # noqa: E402
from bet.sofa.cs2 import write_atomic  # noqa: E402
from bet.sofa.timeutil import now  # noqa: E402

P_EDGE = 0.005  # a fair_p this close to 0 or 1 has no usable logit
COUPON_REGION = 0.70


def graded_rows(
    runs_dir: str, sport: sc.SportKey, before: str
) -> list[tuple[str, str, float, float]]:
    """(date, game, fair_p, y) of every graded non-player line before `before`."""
    root = sc.day_dir(runs_dir, sport, before).parent
    out: list[tuple[str, str, float, float]] = []
    if not root.exists():
        return out
    for day in sorted(p.name for p in root.iterdir() if p.is_dir()):
        if day >= before:
            continue
        settled = sc.load_settled(runs_dir, sport, day)
        for eid, ev in ((settled or {}).get("events") or {}).items():
            if ev.get("state") != "SETTLED":
                continue
            for g in ev.get("graded") or []:
                p = g.get("fair_p")
                if g.get("outcome") not in ("WIN", "LOSS") or p is None:
                    continue
                if sc.is_player_family(str(g.get("family") or "")):
                    continue
                if not P_EDGE < float(p) < 1 - P_EDGE:
                    continue
                out.append(
                    (day, f"{day}:{eid}", float(p),
                     1.0 if g["outcome"] == "WIN" else 0.0)
                )
    return out


def logit(p: float) -> float:
    return math.log(p / (1 - p))


def fit(rows: list[tuple[str, str, float, float]]) -> tuple[float, float]:
    """Maximum-likelihood (a, c) of y ~ a + c * logit(p), by Newton steps."""
    a, c = 0.0, 1.0
    xs = [(logit(p), y) for _, _, p, y in rows]
    for _ in range(50):
        g0 = g1 = h00 = h01 = h11 = 0.0
        for x, y in xs:
            q = 1 / (1 + math.exp(-(a + c * x)))
            r = y - q
            w = q * (1 - q)
            g0 += r
            g1 += r * x
            h00 += w
            h01 += w * x
            h11 += w * x * x
        det = h00 * h11 - h01 * h01
        if det <= 0:
            break
        da = (h11 * g0 - h01 * g1) / det
        dc = (h00 * g1 - h01 * g0) / det
        a, c = a + da, c + dc
        if abs(da) < 1e-10 and abs(dc) < 1e-10:
            break
    return a, c


def lodo(rows: list[tuple[str, str, float, float]]) -> dict[str, Any]:
    by_day: dict[str, list[tuple[str, str, float, float]]] = defaultdict(list)
    for r in rows:
        by_day[r[0]].append(r)
    cs: list[float] = []
    raw = cal = 0.0
    n = 0
    for day, held in sorted(by_day.items()):
        train = [r for r in rows if r[0] != day]
        if not train:
            continue
        a, c = fit(train)
        cs.append(c)
        for _, _, p, y in held:
            if p < COUPON_REGION:
                continue
            q = sc.calibrated_p(p, a, c)
            raw += (p - y) ** 2
            cal += (q - y) ** 2
            n += 1
    return {
        "days": len(cs),
        "c_min": round(min(cs), 4) if cs else None,
        "c_max": round(max(cs), 4) if cs else None,
        "oos_lines_p70": n,
        "oos_brier_diff_p70": round((cal - raw) / n, 6) if n else None,
    }


def region(
    rows: list[tuple[str, str, float, float]], a: float, c: float
) -> dict[str, Any]:
    sel = [(p, y) for _, _, p, y in rows if p >= COUPON_REGION]
    if not sel:
        return {"n": 0}
    return {
        "n": len(sel),
        "mean_fair_p": round(sum(p for p, _ in sel) / len(sel), 4),
        "mean_calibrated_p": round(
            sum(sc.calibrated_p(p, a, c) for p, _ in sel) / len(sel), 4
        ),
        "hit": round(sum(y for _, y in sel) / len(sel), 4),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--before", required=True, help="first date NOT fitted on")
    ap.add_argument("--sports", nargs="+", default=list(sc.CALIBRATED_SPORTS))
    ap.add_argument("--runs-dir", default="runs/sofa")
    ap.add_argument("--out", default=str(config_path(sc.PRICE_CALIBRATION_FILE)))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    sports: dict[str, Any] = {}
    for sport in args.sports:
        rows = graded_rows(args.runs_dir, sport, args.before)
        if not rows:
            print(f"{sport}: no graded lines before {args.before}", file=sys.stderr)
            return 2
        a, c = fit(rows)
        days = sorted({r[0] for r in rows})
        sports[sport] = {
            "a": round(a, 6),
            "c": round(c, 6),
            "lines": len(rows),
            "games": len({r[1] for r in rows}),
            "fitted_from": {"first": days[0], "last": days[-1], "days": len(days)},
            "coupon_region": region(rows, a, c),
            "leave_one_day_out": lodo(rows),
        }
    doc = {
        "fitted_at_utc": now().isoformat().replace("+00:00", "Z"),
        "before": args.before,
        "method": "y ~ a + c * logit(fair_p), maximum likelihood, every graded "
        "non-player shadow line of the settled days before `before`",
        "sports": sports,
    }
    text = json.dumps(doc, indent=1) + "\n"
    print(text)
    if not args.dry_run:
        write_atomic(Path(args.out), text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
