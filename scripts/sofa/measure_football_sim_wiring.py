#!/usr/bin/env python3
"""Hold-out of the wired football simulator chain (epochs.FOOTBALL_SIM) on
Superbet's own settled lines - read-only evidence, no pipeline artifact
written.

FROZEN RULE (written 2026-11-06 before any hold-out number was computed):

* Lines: football_sim_curves.BACKFILL (fit_football_sim_curves.py
  --backfill-out) - every path-market selection OFFER recorded in
  unmapped_prices, the latest snapshot before the start, graded by
  football_sim_markets.sim_value (what SETTLE runs) - of days
  2026-10-20 .. 2026-11-05 (after the curves' window, which ends 10-19).
* p: the simulator's p as SHEET prices it (football_sim_sheet.SimPricer, the
  match's walk-forward pure rating centres).
* Confidence, two variants:
    A  the history curve alone: config/sofa_football_sim_curves.json overlaid
       on the calibration 2026-11-07 reads (football_sim_curves.for_day),
       CONFIDENCE's K2 / K13 / K13b settings, Calibration.realised (lo95);
    B  the chain CONFIDENCE runs on 2026-11-07: A then
       config/sofa_superbet_line_evidence.json as installed today
       (LineEvidence.read with the day's v2 / design effect / price-gap
       settings) - the keys have no own lines in it, so the sport's pooled
       football offset lowers them. B is the verdict variant.
* Print gates (unchanged, CONFIDENCE's): odds >= MIN_ODDS_FOR_CEILING
  (ODDS_TOO_LOW - added after the first run, which omitted it; both
  reported), p_central >= 0.60 (catch-all bucket), confidence >= 0.70
  (leg_floor), confidence x odds >= 0.90; a
  two-sided rung (team_scores_both_halves, btts_any_half) needs the rung's
  overround <= 15% (both prices of one snapshot); a one-sided leg needs its
  confidence from its own market curve (source "market:" / "line:") with
  n >= epochs.ONE_SIDED_MIN_CURVE_N.
* Reported per market and in total: legs, matches, mean confidence,
  realised, realised - confidence with a 95% match bootstrap (2,000
  resamples, seed 7, all legs of a match together), ROI flat stake before
  and after the 12% tax (return 0.88 x odds) with its interval; also every
  leg with confidence >= 0.70 regardless of the price gates (calibration).
* STOP RULE: if variant B's printable legs over-promise - upper bound of
  realised - confidence < 0 - the switch is set to None. Price inferiority
  (ROI < 0) alone does not stop it (operator, 1X2 decision 11-06).

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_football_sim_wiring.py \\
        [--lines <jsonl.gz>] [--out <json>]
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import random
import sys
from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import (  # noqa: E402
    epochs,  # noqa: E402
    live_only_curves,
    tennis_point_curves,
)
from bet.sofa import football_sim_curves as fsc  # noqa: E402
from bet.sofa import line_evidence as le  # noqa: E402
from bet.sofa.confidence import (  # noqa: E402
    MIN_ODDS_FOR_CEILING,
    OWN_CURVE_SOURCES,
    Calibration,
    calibration_path_for,
    direction_key,
    overround,
)

DAY = "2026-11-07"
FROM, TO = "2026-10-20", "2026-11-05"
FLOOR, MIN_X, MAX_OVERROUND, P_MIN = 0.70, 0.90, 0.15, 0.60
TAX = 0.88
BOOT, SEED = 2000, 7


def calibration(at: datetime) -> Calibration:
    cal = Calibration.load(calibration_path_for(DAY, at))
    cal = live_only_curves.for_day(cal, DAY, at)
    cal = tennis_point_curves.for_day(cal, DAY, at)
    cal = fsc.for_day(cal, DAY, at)
    cal = dataclasses.replace(cal, gap_shrink_k=0.0, cap_market_by_thin=True)
    if epochs.pool_neighbour_cap(DAY, at):
        cal = dataclasses.replace(cal, cap_pool_by_neighbour=True)
    return cal


def evidence(at: datetime) -> le.LineEvidence:
    return le.LineEvidence.load(
        v2=epochs.line_evidence_v2(DAY, at),
        bucket_deff=epochs.bucket_design_effect(DAY, at),
        price_gap_sports=epochs.price_gap_offset_sports(DAY, at))


def boot(legs: Sequence[dict[str, Any]], stat: str) -> tuple[float, float, float]:
    by_match: dict[Any, list[dict[str, Any]]] = defaultdict(list)
    for x in legs:
        by_match[x["eid"]].append(x)
    groups = list(by_match.values())

    def value(sample: Sequence[list[dict[str, Any]]]) -> float:
        rows = [x for g in sample for x in g]
        if stat == "gap":
            return float(sum(x["y"] - x["conf"] for x in rows)) / len(rows)
        if stat == "roi":
            return float(sum(x["y"] * x["odds"] - 1 for x in rows)) / len(rows)
        return float(sum(x["y"] * x["odds"] * TAX - 1 for x in rows)) / len(rows)

    point = value(groups)
    rng = random.Random(SEED)
    draws = sorted(value([groups[rng.randrange(len(groups))] for _ in groups])
                   for _ in range(BOOT))
    return point, draws[int(0.025 * BOOT)], draws[int(0.975 * BOOT) - 1]


def summary(legs: Sequence[dict[str, Any]]) -> dict[str, Any]:
    if not legs:
        return {"legs": 0}
    gap = boot(legs, "gap")
    roi = boot(legs, "roi")
    tax = boot(legs, "tax")
    return {
        "legs": len(legs), "matches": len({x["eid"] for x in legs}),
        "confidence": round(sum(x["conf"] for x in legs) / len(legs), 4),
        "realised": round(sum(x["y"] for x in legs) / len(legs), 4),
        "realised_minus_confidence": [round(v, 4) for v in gap],
        "roi": [round(v, 4) for v in roi],
        "roi_after_tax": [round(v, 4) for v in tax],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    ap.add_argument("--lines", default=str(fsc.BACKFILL))
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    at = datetime(2026, 11, 7, 6, 0, tzinfo=UTC)
    cal, ev = calibration(at), evidence(at)
    lines = [r for r in fsc.load_backfill(Path(args.lines))
             if FROM <= str(r["day"]) <= TO]
    out: dict[str, Any] = {"rule": "frozen, see the module doc", "lines": len(lines),
                           "window": [FROM, TO]}
    for variant in ("A", "B"):
        printable: dict[str, list[dict[str, Any]]] = defaultdict(list)
        calib: dict[str, list[dict[str, Any]]] = defaultdict(list)
        refusals: dict[str, int] = defaultdict(int)
        for r in lines:
            market, direction, p = str(r["market"]), str(r["direction"]), float(r["p"])
            klass = r.get("klass") or None
            hit = cal.realised(market, p, "football", direction, klass)
            if variant == "B":
                read = ev.read("football", le.evidence_key(
                    direction_key(market, direction), klass), p, hit,
                    float(r["odds"]))
                hit = None if read is None else (read.value, read.source, read.n)
            if hit is None:
                refusals["no_confidence"] += 1
                continue
            conf, source, n = float(hit[0]), str(hit[1]), int(hit[2])
            leg = {"eid": r["eid"], "y": int(r["y"]), "conf": conf,
                   "odds": float(r["odds"]), "market": market}
            if leg["odds"] < MIN_ODDS_FOR_CEILING:
                # ODDS_TOO_LOW (run_confidence MIN_ODDS): omitted from the
                # first run of 2026-11-06 - a gate omission corrected after
                # the result, reported beside it (evidence report section 5)
                refusals["odds_too_low"] += 1
                continue
            if conf < FLOOR:
                refusals["below_floor"] += 1
                continue
            if p < P_MIN:
                refusals["catch_all"] += 1
                continue
            calib[market].append(leg)
            if conf * leg["odds"] < MIN_X:
                refusals["x_below_0.90"] += 1
                continue
            if r.get("counter_odds") is not None:
                margin = overround(leg["odds"], float(r["counter_odds"]))
                if margin is None or margin > MAX_OVERROUND:
                    refusals["margin"] += 1
                    continue
            elif market in {"team_scores_both_halves", "btts_any_half"}:
                refusals["no_counter_price"] += 1
                continue
            elif not (source.startswith(OWN_CURVE_SOURCES)
                      and n >= epochs.ONE_SIDED_MIN_CURVE_N):
                refusals["one_sided_not_admitted"] += 1
                continue
            printable[market].append(leg)
        all_print = [x for v in printable.values() for x in v]
        all_cal = [x for v in calib.values() for x in v]
        out[variant] = {
            "printable_total": summary(all_print),
            "printable_by_market": {
                m: summary(v) for m, v in sorted(printable.items())},
            "conf_ge_070_total": summary(all_cal),
            "conf_ge_070_by_market": {m: summary(v) for m, v in sorted(calib.items())},
            "refusals": dict(refusals),
        }
    b = out["B"]["printable_total"]
    out["stop_rule"] = (
        "NO_LEGS" if not b.get("legs")
        else "STOP" if b["realised_minus_confidence"][2] < 0 else "PASS")
    text = json.dumps(out, indent=1)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
