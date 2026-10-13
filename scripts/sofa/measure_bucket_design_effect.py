#!/usr/bin/env python3
"""Walk-forward measurement of the bucket design effect (audit 2026-10-13 A4,
epochs.BUCKET_DESIGN_EFFECT): read-only evidence for a decision, never a gate.

Pre-registered in docs/sofa/evidence/bucket_design_effect_2026-10-13.md. For
every test day d the line evidence is fitted (le.fit, v2) on the settled lines
of days before d only - football / tennis from 07_settled.json
(fit_line_evidence.sheet_rows), the measured sports from the Superbet rows
(fit_line_evidence.sport_rows) - and day d's lines of keys WITHOUT a curve are
read with the sport's design effect (old) and with the bucket's (new).

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_bucket_design_effect.py \\
        --rows-dir data/line_evidence/rows_before_2026-10-13 \\
        --days 2026-10-07 ... 2026-10-12 [--json-out f]
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import math
import random
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO / "src"), str(_REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import line_evidence as le  # noqa: E402
from bet.sofa import sport_confidence as scf  # noqa: E402
from bet.sofa.confidence import Calibration, calibration_path_for  # noqa: E402
from bet.sofa.config import SofaConfig  # noqa: E402
from scripts.sofa.fit_line_evidence import (  # noqa: E402
    sheet_rows,
    sport_rows,
    stats_only_days,
)
from scripts.sofa.measure_sport_guard import boot  # noqa: E402

FLOOR, MIN_X = 0.70, 0.90
EPS = 1e-6


def row_day(game: str) -> str:
    """'2026-10-09:123' (sheet) or 's:2026-10-09:sb' (sports) -> the day."""
    parts = game.split(":")
    return parts[1] if parts[0] in ("s", "h") else parts[0]


def logloss(c: float, y: int) -> float:
    c = min(max(c, EPS), 1 - EPS)
    return -math.log(c if y else 1 - c)


def boot_diff(items: dict[str, list[float]], seed: int = 7, reps: int = 2000
              ) -> list[float]:
    keys = sorted(items)
    flat = [v for k in keys for v in items[k]]
    if not flat:
        return [float("nan")] * 3
    rng = random.Random(seed)
    stats = []
    for _ in range(reps):
        tot = n = 0.0
        for _k in keys:
            vs = items[keys[rng.randrange(len(keys))]]
            tot += sum(vs)
            n += len(vs)
        stats.append(tot / n)
    stats.sort()
    lo, hi = stats[int(0.025 * reps)], stats[int(0.975 * reps) - 1]
    return [sum(flat) / len(flat), lo, hi]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--rows-dir", required=True)
    ap.add_argument("--days", nargs="+", required=True)
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args()
    config = SofaConfig.from_env()
    runs_dir = Path(config.runs_dir)
    last = max(args.days)
    nxt = f"{last[:8]}{int(last[8:]) + 1:02d}"
    sheet_days = stats_only_days(runs_dir, nxt)
    cal = dataclasses.replace(Calibration.load(calibration_path_for(last)),
                              gap_shrink_k=0.0, cap_market_by_thin=True,
                              cap_pool_by_neighbour=True)
    sport_cal = scf.SportCalibration.load(scf.calibration_path_for(last))
    rows = list(sheet_rows(runs_dir, sheet_days, cal))
    if sport_cal is not None:
        rows += list(sport_rows(Path(args.rows_dir), sport_cal, config.runs_dir))
    print(f"rows {len(rows)}", file=sys.stderr)
    ll: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    legs: dict[str, dict[str, list[tuple[str, float, int, float]]]] = defaultdict(
        lambda: defaultdict(list))
    for day in args.days:
        train = [r for r in rows if row_day(str(r["game"])) < day]
        test = [r for r in rows if row_day(str(r["game"])) == day
                and r.get("base") is None]
        fitted = le.fit(train)
        doc = {"keys": fitted["keys"], "bands": fitted["bands"],
               "sport_printable": fitted["sport_printable"],
               "design_effect": fitted["design_effect"]}
        old = le.LineEvidence(doc, v2=True)
        new = le.LineEvidence(doc, v2=True, bucket_deff=True)
        for r in test:
            odds = None if r.get("odds") is None else float(r["odds"])
            a = old.read(r["sport"], r["key"], float(r["p"]), None, odds)
            b = new.read(r["sport"], r["key"], float(r["p"]), None, odds)
            if a is None or b is None:
                continue
            y, g = int(r["y"]), str(r["game"])
            for scope in (r["sport"], "all"):
                if max(a.value, b.value) >= FLOOR:
                    ll[scope][g].append(logloss(b.value, y) - logloss(a.value, y))
                if odds is None:
                    continue
                pa = a.value >= FLOOR and a.value * odds >= MIN_X
                pb = b.value >= FLOOR and b.value * odds >= MIN_X
                if pa:
                    legs[scope]["old"].append((g, a.value, y, odds))
                if pb:
                    legs[scope]["new"].append((g, b.value, y, odds))
                if pb and not pa:
                    legs[scope]["added"].append((g, b.value, y, odds))
        print(f"{day}: train {len(train)} test(no curve) {len(test)}", file=sys.stderr)
    out: dict[str, Any] = {"days": args.days, "sheet_days": sheet_days, "scopes": {}}
    for scope in sorted(set(ll) | set(legs)):
        out["scopes"][scope] = {
            "logloss_new_minus_old": boot_diff(ll[scope]),
            "lines": sum(len(v) for v in ll[scope].values()),
            "games": len(ll[scope]),
            **{k: boot(v) for k, v in legs[scope].items()}}
    text = json.dumps(out, indent=1, ensure_ascii=False)
    print(text)
    if args.json_out:
        Path(args.json_out).write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
