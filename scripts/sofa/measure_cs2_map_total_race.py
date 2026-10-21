#!/usr/bin/env python3
"""CS2 map_rounds_total: the round race vs the history's base rate. Read-only.

Today cs2_engine prices a map's total rounds as the history's share above the
line - the same p for every match, blind to how strong the two teams are. The
round race (cs2_engine.map_distribution_for, which map_rounds_handicap and,
from CS2_TEAM_ROUNDS_RACE, map_team_rounds already read) gives the map's whole
score distribution from the map-win probability, so a mismatch moves the
total down. Two checks:

1. history walk-forward: the same replay as the curve fit
   (sport_confidence.cs2_walk_forward_rows - Elo, its calibration refitted
   every REFIT_DAYS_CS2 days, the map's p as of the series' start); every
   earlier map's total (LOOKBACK_DAYS) is the base rate; both priced on
   LINES, log-loss / Brier race minus base, series bootstrap; calibration
   at p >= 0.70; split by the favourite's map p.
2. Superbet's settled lines (runs/sofa/cs2/<d>/settled.json): the engine's
   p at settle (model_p, the base rate) against the race from the ratings
   as of the day, and both against Superbet's own de-margined price.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_cs2_map_total_race.py \\
        [--from 2025-10-19] [--to 2026-10-19] [--json-out f]
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from collections import Counter, defaultdict, deque
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
LINES = (16.5, 17.5, 18.5, 19.5, 20.5, 21.5, 22.5, 23.5)
FAV_BANDS = ((0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 0.96))


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


def race_total(p_map: float, line: float, over: bool) -> float | None:
    dist = cs2_engine._race_dist(round(min(max(p_map, 0.05), 0.95), 3))
    p_over = sum(q for s, q in dist if s[0] + s[1] > line)
    p_under = sum(q for s, q in dist if s[0] + s[1] < line)
    return cs2_engine.side_given_no_push(p_over, p_under, over)


def calib(pairs: list[tuple[str, float, int]]) -> dict[str, Any]:
    if not pairs:
        return {"n": 0}
    g: dict[str, list[float]] = defaultdict(list)
    for game, p, y in pairs:
        g[game].append(y - p)
    gap = boot(g)
    return {"n": len(pairs), "games": len(g),
            "mean_p": round(sum(p for _, p, _ in pairs) / len(pairs), 4),
            "realised": round(sum(y for _, _, y in pairs) / len(pairs), 4),
            "gap_pp": [round(100 * v, 2) for v in gap]}


def history(db: str, start: str, end: str) -> dict[str, Any]:
    t0, t1 = scf.day_ts(start), scf.day_ts(end)
    maps, series = scf.load_cs2(db, t1)
    # p_map per series from the replay's own map_winner rows (map identity
    # off: one p per series, home = T1)
    rows = scf.cs2_walk_forward_rows(maps, series, t0, t1, "m", True)
    p_series = {int(r["game"][2:]): float(r["p"]) for r in rows
                if r["family"] == "map_winner" and r["side"] == "T1"}
    window: deque[tuple[int, int]] = deque()
    counts: Counter[int] = Counter()
    by_series: dict[int, list[cs2_engine.MapRow]] = {}
    for m in maps:
        by_series.setdefault(m.event_id, []).append(m)
    d_ll: dict[str, list[float]] = defaultdict(list)
    d_br: dict[str, list[float]] = defaultdict(list)
    d_line: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    d_fav: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    cal: dict[str, list[tuple[str, float, int]]] = {"base": [], "race": []}
    cal_fav: dict[str, dict[str, list[tuple[str, float, int]]]] = defaultdict(
        lambda: {"base": [], "race": []})
    skipped_unrated = 0
    for eid, smaps in by_series.items():
        start_ts = smaps[0].start_ts
        while window and window[0][0] < start_ts - cs2_engine.LOOKBACK_DAYS * 86400:
            counts[window.popleft()[1]] -= 1
        if t0 <= start_ts < t1:
            pm = p_series.get(eid)
            if pm is None:
                skipped_unrated += 1
            else:
                fav = max(pm, 1 - pm)
                band = next((f"{lo:.1f}-{hi:.2f}" for lo, hi in FAV_BANDS
                             if lo <= fav < hi), "other")
                game = f"h:{eid}"
                for m in smaps:
                    if m.home_rounds is None or m.away_rounds is None:
                        continue
                    total = m.home_rounds + m.away_rounds
                    for line in LINES:
                        base = scf.counted_base_rate(counts, line)
                        if base is None:
                            continue
                        for over in (True, False):
                            pr = race_total(pm, line, over)
                            if pr is None:
                                continue
                            pb = cs2_engine.clamp(base if over else 1 - base)
                            pr = cs2_engine.clamp(pr)
                            y = int((total > line) == over)
                            d = ll(pr, y) - ll(pb, y)
                            d_ll[game].append(d)
                            d_br[game].append((pr - y) ** 2 - (pb - y) ** 2)
                            d_line[f"{line}|{'OVER' if over else 'UNDER'}"][game].append(d)
                            d_fav[band][game].append(d)
                            for k, p in (("base", pb), ("race", pr)):
                                if p >= 0.70:
                                    cal[k].append((game, p, y))
                                    cal_fav[band][k].append((game, p, y))
        for m in smaps:
            if m.home_rounds is not None and m.away_rounds is not None:
                t = m.home_rounds + m.away_rounds
                window.append((m.start_ts, t))
                counts[t] += 1
    return {
        "window": [start, end], "series": len(d_ll),
        "series_unrated_skipped": skipped_unrated,
        "lines": sum(len(v) for v in d_ll.values()),
        "logloss_race_minus_base": boot(d_ll),
        "brier_race_minus_base": boot(d_br),
        "by_line_side": {k: boot(v) + [sum(len(x) for x in v.values())]
                         for k, v in sorted(d_line.items())},
        "by_favourite_map_p": {k: boot(v) + [sum(len(x) for x in v.values())]
                               for k, v in sorted(d_fav.items())},
        "calibration_p_ge_070": {k: calib(v) for k, v in cal.items()},
        "calibration_p_ge_070_by_favourite": {
            b: {k: calib(v) for k, v in d.items()} for b, d in sorted(cal_fav.items())},
    }


def superbet(db: str, runs_dir: str) -> dict[str, Any]:
    d_ll: dict[str, list[float]] = defaultdict(list)
    d_mkt: dict[str, dict[str, list[float]]] = {"base": defaultdict(list),
                                                "race": defaultdict(list)}
    printable: dict[str, list[tuple[str, float, int, float]]] = defaultdict(list)
    cal: dict[str, list[tuple[str, float, int]]] = {"base": [], "race": []}
    days = sorted(p.parent.name for p in Path(runs_dir, "cs2").glob("2026-*/settled.json"))
    for day in days:
        doc = json.loads(Path(runs_dir, "cs2", day, "settled.json").read_text("utf-8"))
        evs = [e for e in (doc.get("events") or {}).values()
               if e.get("state") == "SETTLED" and any(
                   g.get("family") == "map_rounds_total" for g in e.get("graded") or [])]
        if not evs:
            continue
        maps, _ = scf.load_cs2(db, scf.day_ts(day))
        ratings = cs2_engine.build_ratings(maps)
        for ev in evs:
            h, a = ev.get("sofascore_home_id"), ev.get("sofascore_away_id")
            if not isinstance(h, int) or not isinstance(a, int):
                continue
            t1, t2 = (h, a) if ev.get("home_is_team1") else (a, h)
            pm = ratings.p_map(t1, t2, bool(ev.get("home_is_team1")))
            if pm is None:
                continue
            game = f"{day}:{ev.get('sofascore_event_id')}"
            for g in ev.get("graded") or []:
                if (g.get("family") != "map_rounds_total" or g.get("model_p") is None
                        or g.get("outcome") not in ("WIN", "LOSS")):
                    continue
                over = g["side"] == "OVER"
                pr = race_total(pm, float(g["line"]), over)
                if pr is None:
                    continue
                pr, pb = cs2_engine.clamp(pr), float(g["model_p"])
                y, odds = int(g["outcome"] == "WIN"), float(g["odds"])
                d_ll[game].append(ll(pr, y) - ll(pb, y))
                fair = g.get("fair_p")
                if fair is not None:
                    for k, p in (("base", pb), ("race", pr)):
                        d_mkt[k][game].append(ll(p, y) - ll(float(fair), y))
                for k, p in (("base", pb), ("race", pr)):
                    if p >= 0.70:
                        cal[k].append((game, p, y))
                        if p * odds >= 0.90:
                            printable[k].append((game, p, y, odds))
    from scripts.sofa.measure_sport_guard import boot as boot_legs
    return {"days": [days[0], days[-1]] if days else [],
            "games": len(d_ll), "lines": sum(len(v) for v in d_ll.values()),
            "logloss_race_minus_base": boot(d_ll),
            "logloss_minus_superbet_fair": {k: boot(v) for k, v in d_mkt.items()},
            "calibration_p_ge_070": {k: calib(v) for k, v in cal.items()},
            "raw_p_would_pass_x090": {k: boot_legs(v) for k, v in printable.items()}}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start", default="2025-10-19")
    ap.add_argument("--to", dest="end", default="2026-10-19")
    ap.add_argument("--json-out")
    args = ap.parse_args()
    cfg = SofaConfig.from_env()
    out = {"history": history(cfg.db_path, args.start, args.end),
           "superbet": superbet(cfg.db_path, cfg.runs_dir)}
    text = json.dumps(out, indent=1)
    print(text)
    if args.json_out:
        Path(args.json_out).write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
