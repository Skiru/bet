#!/usr/bin/env python3
"""Football simulator markets: a 0.60 confidence floor - read-only evidence.

The rule is frozen in docs/sofa/evidence/football_sim_floor_2026-11-06.md
section 0, written before any number in the band was computed. In short:
the backfilled Superbet lines of 2026-10-20 .. 11-05, confidence as variant
B of measure_football_sim_wiring.py (curve + today's installed line
evidence), legs with confidence in [0.60, 0.70) passing every other print
gate (ODDS_TOO_LOW, CATCH_ALL_BUCKET, x >= 0.90, two-sided margin <= 15%,
one-sided own curve n >= 300), judged per market|direction key: n_min 100
legs / 50 matches, realised - confidence upper 95% >= 0, realised - de-vigged
price upper 95% >= 0 (on >= 100 legs with a de-vigged price). ROI before and
after the 12% tax as facts.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_football_sim_floor.py \\
        [--lines <jsonl.gz>] [--out <json>]
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import defaultdict
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import epochs  # noqa: E402
from bet.sofa import football_sim_curves as fsc  # noqa: E402
from bet.sofa import football_sim_markets as fsm  # noqa: E402
from bet.sofa import line_evidence as le  # noqa: E402
from bet.sofa.confidence import (  # noqa: E402
    MIN_ODDS_FOR_CEILING,
    OWN_CURVE_SOURCES,
    direction_key,
    overround,
)
from scripts.sofa.measure_football_sim_wiring import (  # noqa: E402
    calibration,
    evidence,
)

FROM, TO = "2026-10-20", "2026-11-05"
BAND = (0.60, 0.70)
MIN_X, MAX_OVERROUND, P_MIN, TAX = 0.90, 0.15, 0.60, 0.88
N_MIN_LEGS, N_MIN_MATCHES, N_MIN_FAIR = 100, 50, 100
BOOT, SEED = 2000, 7
DEVIG_SUM = (1.00, 1.60)
FULL_SET: dict[str, int] = {
    fsm.HTFT: 9, fsm.RESULT_1H: 3, fsm.RESULT_2H: 3, fsm.HIGHER_HALF: 3,
    fsm.BTTS_HALVES: 4, fsm.FIRST_GOAL_1H: 3, fsm.HALF_GOALS_COMBO: 4,
}
Row = dict[str, Any]


def _set_key(r: Row) -> tuple[Any, ...] | None:
    """The outcome set a one-sided selection belongs to (one snapshot)."""
    market = str(r["market"])
    if market not in FULL_SET:
        return None
    extra: tuple[Any, ...] = ()
    if market == fsm.HALF_GOALS_COMBO:
        lines = fsm.combo_lines(str(r["subject"]))
        if lines is None:
            return None
        extra = (lines[1], lines[3])
    return (r["eid"], market, r["fetched_at_utc"], *extra)


def attach_fair(lines: Sequence[Row]) -> None:
    sets: dict[tuple[Any, ...], list[Row]] = defaultdict(list)
    for r in lines:
        if r["direction"] != "OVER":
            continue
        k = _set_key(r)
        if k is not None:
            sets[k].append(r)
    for k, rows in sets.items():
        subjects = {str(r["subject"]) for r in rows}
        if len(subjects) != FULL_SET[str(k[1])] or len(rows) != len(subjects):
            continue
        s = sum(1.0 / float(r["odds"]) for r in rows)
        if not DEVIG_SUM[0] <= s <= DEVIG_SUM[1]:
            continue
        for r in rows:
            r["fair"] = (1.0 / float(r["odds"])) / s
    for r in lines:
        if r.get("counter_odds") is not None and str(r["market"]) in fsm.TWO_SIDED:
            s = 1.0 / float(r["odds"]) + 1.0 / float(r["counter_odds"])
            if DEVIG_SUM[0] <= s <= DEVIG_SUM[1]:
                r["fair"] = (1.0 / float(r["odds"])) / s


def boot(legs: Sequence[Row], f: Callable[[Row], float]
         ) -> tuple[float, float, float] | None:
    if not legs:
        return None
    by: dict[Any, list[float]] = defaultdict(list)
    for x in legs:
        by[x["eid"]].append(f(x))
    groups = list(by.values())

    def mean(sample: Sequence[list[float]]) -> float:
        vals = [v for g in sample for v in g]
        return sum(vals) / len(vals)

    rng = random.Random(SEED)
    draws = sorted(mean([groups[rng.randrange(len(groups))] for _ in groups])
                   for _ in range(BOOT))
    return (round(mean(groups), 4), round(draws[int(0.025 * BOOT)], 4),
            round(draws[int(0.975 * BOOT) - 1], 4))


def summary(legs: Sequence[Row]) -> dict[str, Any]:
    fair = [x for x in legs if x.get("fair") is not None]
    out: dict[str, Any] = {
        "legs": len(legs), "matches": len({x["eid"] for x in legs}),
        "legs_with_fair": len(fair),
    }
    if not legs:
        return out
    out.update({
        "confidence": round(sum(x["conf"] for x in legs) / len(legs), 4),
        "realised": round(sum(x["y"] for x in legs) / len(legs), 4),
        "implied": round(sum(1 / x["odds"] for x in legs) / len(legs), 4),
        "realised_minus_confidence": boot(legs, lambda x: x["y"] - x["conf"]),
        "realised_minus_fair": boot(fair, lambda x: x["y"] - x["fair"]),
        "realised_minus_implied": boot(legs, lambda x: x["y"] - 1 / x["odds"]),
        "roi": boot(legs, lambda x: x["y"] * x["odds"] - 1),
        "roi_after_tax": boot(legs, lambda x: x["y"] * x["odds"] * TAX - 1),
    })
    return out


def verdict(s: dict[str, Any]) -> str:
    if s["legs"] < N_MIN_LEGS or s["matches"] < N_MIN_MATCHES:
        return "FAIL: below n_min"
    if s["realised_minus_confidence"][2] < 0:
        return "FAIL: over-promises"
    if s["legs_with_fair"] < N_MIN_FAIR or s["realised_minus_fair"] is None:
        return "FAIL: no de-vigged price on >= 100 legs"
    if s["realised_minus_fair"][2] < 0:
        return "FAIL: below the de-vigged price"
    return "PASS"


def main() -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    ap.add_argument("--lines", default=str(fsc.BACKFILL))
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    at = datetime(2026, 11, 7, 6, 0, tzinfo=UTC)
    cal, ev = calibration(at), evidence(at)
    lines = [r for r in fsc.load_backfill(Path(args.lines))
             if FROM <= str(r["day"]) <= TO]
    attach_fair(lines)
    band: dict[str, list[Row]] = defaultdict(list)
    refusals: dict[str, int] = defaultdict(int)
    for r in lines:
        market, direction, p = str(r["market"]), str(r["direction"]), float(r["p"])
        klass = r.get("klass") or None
        hit = cal.realised(market, p, "football", direction, klass)
        read = ev.read("football", le.evidence_key(
            direction_key(market, direction), klass), p, hit, float(r["odds"]))
        if read is None:
            refusals["no_confidence"] += 1
            continue
        conf, source, n = float(read.value), str(read.source), int(read.n)
        odds = float(r["odds"])
        if not BAND[0] <= conf < BAND[1]:
            continue
        if odds < MIN_ODDS_FOR_CEILING:
            refusals["odds_too_low"] += 1
            continue
        if p < P_MIN:
            refusals["catch_all"] += 1
            continue
        if conf * odds < MIN_X:
            refusals["x_below_0.90"] += 1
            continue
        if market in fsm.TWO_SIDED:
            margin = (None if r.get("counter_odds") is None
                      else overround(odds, float(r["counter_odds"])))
            if margin is None or margin > MAX_OVERROUND:
                refusals["margin_or_no_counter"] += 1
                continue
        elif not (source.startswith(OWN_CURVE_SOURCES)
                  and n >= epochs.ONE_SIDED_MIN_CURVE_N):
            refusals["one_sided_not_admitted"] += 1
            continue
        band[f"{market}|{direction}"].append(
            {"eid": r["eid"], "y": int(r["y"]), "conf": conf, "odds": odds,
             "fair": r.get("fair")})
    keys = sorted(f"{m}|OVER" for m in epochs.FOOTBALL_SIM_MARKETS) + sorted(
        f"{m}|UNDER" for m in fsm.TWO_SIDED)
    per_key = {}
    for k in sorted(keys):
        s = summary(band.get(k, []))
        s["verdict"] = verdict(s) if s["legs"] else "FAIL: below n_min"
        per_key[k] = s
    out = {"rule": "frozen, docs/sofa/evidence/football_sim_floor_2026-11-06.md s.0",
           "window": [FROM, TO], "band": list(BAND), "lines": len(lines),
           "per_key": per_key,
           "all_band_legs": summary([x for v in band.values() for x in v]),
           "refusals_in_band": dict(refusals),
           "passing": [k for k, s in per_key.items() if s["verdict"] == "PASS"]}
    text = json.dumps(out, indent=1)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
