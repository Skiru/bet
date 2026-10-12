#!/usr/bin/env python3
"""Walk-forward measurement of the measured sports' line-evidence guard
(read-only evidence for a decision, never a gate).

For every test day d the line evidence is fitted on the Superbet settled lines
dated before d only (the same `fit_line_evidence.sport_rows` + `le.fit` the
morning refresh runs), and day d's lines are read through it exactly as
SPORT_CONFIDENCE reads them (`LineEvidence.read`, v2). A line "would print"
when its confidence >= 0.70 and confidence x odds >= 0.90 (the ladder-margin
gate is not applied: the rows carry no ladder).

Variants (each only lowers the current read):
  current      the installed rule;
  bucket_up    the key's own lines with p in the leg's p bucket and above,
               pooled downward until MIN_CAP_CELL lines, cap = their realised
               rate where the Wilson upper bound of that cell (lines divided by
               the sport's design effect) is below the confidence;
  bucket_up_pt the same cell, cap = its realised rate whenever lower (point).

Per variant: legs, games, mean confidence, realised, gap (realised - confidence)
and ROI with 95% intervals from a bootstrap over games, plus the legs a variant
removes or lowers below the gates and how they did.

Usage:
  PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_sport_guard.py \
      --rows-dir data/line_evidence/rows_before_2026-10-12 \
      --days 2026-10-08 2026-10-09 2026-10-10 2026-10-11 [--sport basketball] \
      [--json-out f]
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from bet.sofa import line_evidence as le
from bet.sofa import sport_confidence as scf
from bet.sofa.config import SofaConfig
from scripts.sofa.fit_line_evidence import sport_rows

FLOOR = 0.70
MIN_X = 0.90
VARIANTS = ("current", "bucket_up", "bucket_up_pt")


def bucket_up_cell(rows_by_key: dict[tuple[str, str], list[tuple[float, int]]],
                   sport: str, key: str, p: float) -> tuple[int, int] | None:
    """(n, k) of the key's lines with p in the leg's bucket and up, widened
    downward to the printable floor until MIN_CAP_CELL lines."""
    lines = rows_by_key.get((sport, key)) or []
    b = le.bucket_of(p)
    floor_b = le.bucket_of(le.PRINTABLE_FROM)
    for lower in range(b, floor_b - 1, -1):
        edge = le.EDGES[lower]
        n = k = 0
        for q, y in lines:
            if q >= edge:
                n += 1
                k += y
        if n >= le.MIN_CAP_CELL:
            return n, k
    return None


def read_variant(variant: str, ev: le.LineEvidence,
                 rows_by_key: dict[tuple[str, str], list[tuple[float, int]]],
                 deff: float, row: dict[str, Any]) -> float | None:
    base = None if row["base"] is None else (float(row["base"]), "curve", 0)
    got = ev.read(row["sport"], row["key"], float(row["p"]), base, row["odds"])
    if got is None:
        return None
    value = got.value
    if variant == "current":
        return value
    cell = bucket_up_cell(rows_by_key, row["sport"], row["key"], float(row["p"]))
    if cell is None:
        return value
    n, k = cell
    rate = k / n
    if variant == "bucket_up":
        if le.wilson_hi(round(k / deff), max(round(n / deff), 1)) < value:
            return min(value, round(rate, 4))
        return value
    return min(value, round(rate, 4))  # bucket_up_pt


def boot(legs: list[tuple[str, float, int, float]], seed: int = 7,
         reps: int = 2000) -> dict[str, Any]:
    """legs: (game, confidence, y, odds) -> mean conf, realised, gap, ROI, CIs."""
    if not legs:
        return {"legs": 0, "games": 0}
    by_game: dict[str, list[tuple[float, int, float]]] = defaultdict(list)
    for g, c, y, o in legs:
        by_game[g].append((c, y, o))
    games = list(by_game)

    def stats(sample: list[str]) -> tuple[float, float, float]:
        n = sc = sy = sr = 0.0
        for g in sample:
            for c, y, o in by_game[g]:
                n += 1
                sc += c
                sy += y
                sr += y * o - 1.0
        return sc / n, sy / n, sr / n

    conf, real, roi = stats(games)
    rng = random.Random(seed)
    gaps, rois = [], []
    for _ in range(reps):
        s = [rng.choice(games) for _ in games]
        c, r, ro = stats(s)
        gaps.append(r - c)
        rois.append(ro)
    gaps.sort()
    rois.sort()
    lo, hi = int(0.025 * reps), int(0.975 * reps) - 1
    return {"legs": len(legs), "games": len(games), "confidence": round(conf, 4),
            "realised": round(real, 4), "gap_pp": round(100 * (real - conf), 1),
            "gap_ci": [round(100 * gaps[lo], 1), round(100 * gaps[hi], 1)],
            "roi_pct": round(100 * roi, 1),
            "roi_ci": [round(100 * rois[lo], 1), round(100 * rois[hi], 1)]}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--rows-dir", required=True)
    ap.add_argument("--days", nargs="+", required=True)
    ap.add_argument("--sport", choices=scf.SPORT_KEYS, default=None)
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args()

    runs_dir = SofaConfig.from_env().runs_dir
    out: dict[str, Any] = {"rows_dir": args.rows_dir, "days": args.days,
                           "by_variant": {}, "by_sport_key": {}}
    legs: dict[str, list[tuple[str, float, int, float]]] = defaultdict(list)
    per_key: dict[tuple[str, str, str], list[tuple[str, float, int, float]]] = \
        defaultdict(list)
    changed: dict[str, list[tuple[str, float, int, float]]] = defaultdict(list)
    for day in args.days:
        cal = scf.SportCalibration.load(scf.calibration_path_for(day))
        if cal is None:
            print(f"{day}: no sport calibration", file=sys.stderr)
            continue
        rows = [r for r in sport_rows(Path(args.rows_dir), cal, runs_dir)
                if args.sport is None or r["sport"] == args.sport]
        train = [r for r in rows if str(r["game"]).split(":")[1] < day]
        test = [r for r in rows if str(r["game"]).split(":")[1] == day
                and r["odds"] is not None]
        fitted = le.fit(train)
        doc = {"keys": fitted["keys"], "bands": fitted["bands"],
               "sport_printable": fitted["sport_printable"],
               "design_effect": fitted["design_effect"]}
        ev = le.LineEvidence(doc, v2=True)
        rows_by_key: dict[tuple[str, str], list[tuple[float, int]]] = \
            defaultdict(list)
        for r in train:
            if r["odds"] is not None:
                rows_by_key[(r["sport"], r["key"])].append((float(r["p"]),
                                                            int(r["y"])))
        for r in test:
            deff = max(float(doc["design_effect"].get(r["sport"]) or 1.0), 1.0)
            reads = {v: read_variant(v, ev, rows_by_key, deff, r) for v in VARIANTS}
            odds = float(r["odds"])
            item_of = {}
            for v, value in reads.items():
                if value is not None and value >= FLOOR and value * odds >= MIN_X:
                    item = (str(r["game"]), value, int(r["y"]), odds)
                    legs[v].append(item)
                    item_of[v] = item
                    if v == "current":
                        per_key[(r["sport"], r["key"], v)].append(item)
            if "current" in item_of:
                for v in VARIANTS[1:]:
                    if v not in item_of:
                        changed[v].append(item_of["current"])
        print(f"{day}: train {len(train)} test {len(test)}", file=sys.stderr)
    for v in VARIANTS:
        out["by_variant"][v] = boot(legs[v])
        if v != "current":
            out["by_variant"][v]["removed_vs_current"] = boot(changed[v])
    for (sport, key, _), items in sorted(per_key.items()):
        if len(items) >= 20:
            out["by_sport_key"][f"{sport}:{key}"] = boot(items)
    text = json.dumps(out, indent=1, ensure_ascii=False)
    print(text)
    if args.json_out:
        Path(args.json_out).write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
