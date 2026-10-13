#!/usr/bin/env python3
"""CS2 map_team_rounds: round race vs own shrunk frequency (audit 2026-10-13
B10, epochs.CS2_TEAM_ROUNDS_RACE). Pre-registered in
docs/sofa/evidence/cs2_team_rounds_race_2026-10-13.md. Read-only.

The history replay sport_confidence.cs2_walk_forward_rows is run twice (the
same Elo, calibration and samples as the curve fit) and the map_team_rounds
rows priced both ways are compared line by line.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_cs2_team_rounds_race.py \\
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
    lo, hi = stats[int(0.025 * reps)], stats[int(0.975 * reps) - 1]
    return [sum(flat) / len(flat), lo, hi]


def superbet_check(db: str, runs_dir: str, days: list[str], base_cal: str,
                   race_cal: str) -> dict[str, Any]:
    """Settled Superbet team-rounds lines of `days`: the old p (model_p at
    settle) through the base curve against the race p (engine as of the day)
    through the race curve; lines with a confidence >= 0.70 and x >= 0.90."""
    cals = {"old": scf.SportCalibration.load(Path(base_cal)),
            "new": scf.SportCalibration.load(Path(race_cal))}
    llg: dict[str, list[float]] = defaultdict(list)
    legs: dict[str, list[tuple[str, float, int, float]]] = defaultdict(list)
    for day in days:
        path = Path(runs_dir) / "cs2" / day / "settled.json"
        if not path.exists():
            continue
        maps, _ = scf.load_cs2(db, scf.day_ts(day))
        ratings = cs2_engine.build_ratings(maps)
        doc = json.loads(path.read_text(encoding="utf-8"))
        for sb, ev in (doc.get("events") or {}).items():
            if ev.get("state") != "SETTLED":
                continue
            h, a = ev.get("sofascore_home_id"), ev.get("sofascore_away_id")
            if not isinstance(h, int) or not isinstance(a, int):
                continue
            t1, t2 = (h, a) if ev.get("home_is_team1") else (a, h)
            p_map = ratings.p_map(t1, t2, bool(ev.get("home_is_team1")))
            for g in ev.get("graded") or []:
                if g.get("family") != "map_team_rounds" or g.get("outcome") not in (
                        "WIN", "LOSS") or g.get("model_p") is None:
                    continue
                idx = 0 if g["subject"] == ev["team1"] else (
                    1 if g["subject"] == ev["team2"] else None)
                if idx is None or p_map is None or g.get("line") is None:
                    continue
                over = g["side"] == "OVER"
                line = float(g["line"])
                pn = cs2_engine.team_rounds_from_race(p_map, idx, line, over)
                if pn is None:
                    continue
                y, odds = int(g["outcome"] == "WIN"), float(g["odds"])
                game = f"{day}:{sb}"
                po = float(g["model_p"])
                llg[game].append(ll(cs2_engine.clamp(pn), y) - ll(po, y))
                fit = scf.line_in_fit("cs2", "map_team_rounds", float(g["line"]))
                for k, p_ in (("old", po), ("new", cs2_engine.clamp(pn))):
                    cal = cals[k]
                    conf = None if cal is None or not fit else cal.lookup(
                        "cs2", "map_team_rounds", g["side"], p_, require_admitted=False)
                    if (conf is not None and conf.value >= 0.70
                            and conf.value * odds >= 0.90):
                        legs[k].append((game, conf.value, y, odds))
    from scripts.sofa.measure_sport_guard import boot as boot_legs
    return {"days": days, "logloss_race_minus_old_p": boot(llg),
            "lines": sum(len(v) for v in llg.values()), "games": len(llg),
            "would_print": {k: boot_legs(v) for k, v in legs.items()}}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start", default="2025-10-13")
    ap.add_argument("--to", dest="end", default="2026-10-13")
    ap.add_argument("--json-out")
    ap.add_argument("--superbet-days", nargs="*", default=None)
    ap.add_argument("--base-cal")
    ap.add_argument("--race-cal")
    args = ap.parse_args()
    db = SofaConfig.from_env().db_path
    if args.superbet_days:
        res = superbet_check(db, SofaConfig.from_env().runs_dir, args.superbet_days,
                             args.base_cal, args.race_cal)
        text = json.dumps(res, indent=1)
        print(text)
        if args.json_out:
            Path(args.json_out).write_text(text + "\n", encoding="utf-8")
        return 0
    t0, t1 = scf.day_ts(args.start), scf.day_ts(args.end)
    maps, series = scf.load_cs2(db, t1)

    def team_rows(race: bool) -> dict[tuple[Any, ...], tuple[float, int]]:
        rows = scf.cs2_walk_forward_rows(maps, series, t0, t1, "m", race)
        return {(r["game"], r["period"], r["subject"], r["line"], r["side"]):
                (float(r["p"]), int(r["y"]))
                for r in rows if r["family"] == "map_team_rounds"}

    old, new = team_rows(False), team_rows(True)
    common = sorted(set(old) & set(new))
    diff: dict[str, list[float]] = defaultdict(list)
    brier: dict[str, list[float]] = defaultdict(list)
    by_line: dict[str, dict[str, list[float]]] = defaultdict(
        lambda: defaultdict(list))
    calib: dict[str, list[tuple[float, int]]] = {"old": [], "new": []}
    for k in common:
        (po, y), (pn, _) = old[k], new[k]
        g = str(k[0])
        d = ll(pn, y) - ll(po, y)
        diff[g].append(d)
        brier[g].append((pn - y) ** 2 - (po - y) ** 2)
        by_line[f"{k[3]}|{k[4]}"][g].append(d)
        if po >= 0.70:
            calib["old"].append((po, y))
        if pn >= 0.70:
            calib["new"].append((pn, y))
    out: dict[str, Any] = {
        "window": [args.start, args.end], "lines": len(common),
        "series": len(diff), "only_old": len(set(old) - set(new)),
        "only_new": len(set(new) - set(old)),
        "logloss_race_minus_freq": boot(diff),
        "brier_race_minus_freq": boot(brier),
        "by_line_side": {k: boot(v) + [float(sum(len(x) for x in v.values()))]
                         for k, v in sorted(by_line.items())},
        "printable_calibration": {
            k: {"n": len(v), "mean_p": sum(p for p, _ in v) / len(v),
                "realised": sum(y for _, y in v) / len(v)} if v else {"n": 0}
            for k, v in calib.items()},
    }
    text = json.dumps(out, indent=1)
    print(text)
    if args.json_out:
        Path(args.json_out).write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
