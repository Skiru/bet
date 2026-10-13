#!/usr/bin/env python3
"""CS2 map identity (audit 2026-10-13 B11, epochs.CS2_MAP_IDENTITY).
Pre-registered in docs/sofa/evidence/cs2_map_identity_2026-10-13.md. Read-only.

The walk-forward replay sport_confidence.cs2_walk_forward_rows is run for the
base (one p for every map), A (order term), B (pool term) and A+B; the
map_winner rows (and the map_team_rounds guard) are compared map by map, the
interval a bootstrap over series.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_cs2_map_identity.py \\
        [--from 2025-10-13] [--to 2026-10-13] [--json-out f]
"""

from __future__ import annotations

import argparse
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

from bet.sofa import cs2_engine  # noqa: E402
from bet.sofa import sport_confidence as scf  # noqa: E402
from bet.sofa.config import SofaConfig  # noqa: E402

EPS = 1e-6
Key = tuple[Any, ...]


def ll(p: float, y: int) -> float:
    p = min(max(p, EPS), 1 - EPS)
    return -math.log(p if y else 1 - p)


def boot(groups: dict[str, list[float]], reps: int = 2000) -> list[float]:
    keys = sorted(groups)
    if not keys:
        return [float("nan")] * 3
    rng = random.Random(0)
    flat = [v for k in keys for v in groups[k]]
    stats = []
    for _ in range(reps):
        tot = n = 0.0
        for _k in keys:
            vs = groups[keys[rng.randrange(len(keys))]]
            tot += sum(vs)
            n += len(vs)
        stats.append(tot / n)
    stats.sort()
    return [sum(flat) / len(flat), stats[int(0.025 * reps)],
            stats[int(0.975 * reps) - 1]]


def run(maps: Any, series: Any, t0: int, t1: int, terms: tuple[str, ...] | None,
        family: str) -> dict[Key, tuple[float, int]]:
    """Rows of `family` (T1 side for map_winner); terms None = the base."""
    saved = cs2_engine.MAP_TERMS
    try:
        if terms is not None:
            cs2_engine.MAP_TERMS = terms
        rows = scf.cs2_walk_forward_rows(maps, series, t0, t1, "m", True,
                                         terms is not None)
    finally:
        cs2_engine.MAP_TERMS = saved
    out: dict[Key, tuple[float, int]] = {}
    for r in rows:
        if r["family"] != family:
            continue
        if family == "map_winner" and r["side"] != "T1":
            continue
        out[(r["game"], r["period"], r["subject"], r["line"], r["side"])] = (
            float(r["p"]), int(r["y"]))
    return out


def compare(base: dict[Key, tuple[float, int]], var: dict[Key, tuple[float, int]],
            keep: set[str]) -> dict[str, Any]:
    d: dict[str, list[float]] = defaultdict(list)
    cal: list[tuple[float, int]] = []
    for k in sorted(set(base) & set(var), key=str):
        if str(k[0]) not in keep:
            continue
        (pb, y), (pv, _) = base[k], var[k]
        d[str(k[0])].append(ll(pv, y) - ll(pb, y))
        if pv >= 0.70:
            cal.append((pv, y))
    return {"maps": sum(len(v) for v in d.values()), "series": len(d),
            "logloss_diff": boot(d),
            "printable": {
                "n": len(cal),
                "mean_p": sum(p for p, _ in cal) / len(cal) if cal else None,
                "realised": (sum(y for _, y in cal) / len(cal)
                             if cal else None)}}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start", default="2025-10-13")
    ap.add_argument("--to", dest="end", default="2026-10-13")
    ap.add_argument("--json-out")
    args = ap.parse_args()
    db = SofaConfig.from_env().db_path
    t0, t1 = scf.day_ts(args.start), scf.day_ts(args.end)
    maps, series = scf.load_cs2(db, t1)
    variants: dict[str, tuple[str, ...] | None] = {
        "base": None, "A": ("order",), "B": ("pool",), "AB": ("order", "pool")}
    res: dict[str, dict[Key, tuple[float, int]]] = {}
    tr: dict[str, dict[Key, tuple[float, int]]] = {}
    for name, terms in variants.items():
        res[name] = run(maps, series, t0, t1, terms, "map_winner")
        tr[name] = run(maps, series, t0, t1, terms, "map_team_rounds")
        print(name, len(res[name]), len(tr[name]), file=sys.stderr)
    starts = sorted({(series[int(str(k[0])[2:])].start_ts, str(k[0]))
                     for k in res["base"] if int(str(k[0])[2:]) in series})
    cut = starts[int(0.6 * len(starts))][0] if starts else 0
    main_w = {g for ts, g in starts if ts >= cut}
    all_w = {g for _, g in starts}
    out: dict[str, Any] = {"window": [args.start, args.end],
                           "main_window_from_ts": cut, "series_all": len(all_w),
                           "series_main": len(main_w)}
    for wname, keep in (("main", main_w), ("all", all_w)):
        w: dict[str, Any] = {}
        w["A_vs_base"] = compare(res["base"], res["A"], keep)
        w["B_vs_base"] = compare(res["base"], res["B"], keep)
        w["AB_vs_base"] = compare(res["base"], res["AB"], keep)
        w["AB_vs_A"] = compare(res["A"], res["AB"], keep)
        w["guard_team_rounds"] = {v: compare(tr["base"], tr[v], keep)
                                  for v in ("A", "B", "AB")}
        out[wname] = w
    text = json.dumps(out, indent=1)
    print(text)
    if args.json_out:
        Path(args.json_out).write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
