#!/usr/bin/env python3
"""Stale vs current sport history on the same settled Superbet lines
(read-only evidence for the 2026-10-12 history fix, bet.sofa.sport_history).

Every settled Superbet line of --from..--to is priced twice by the score model
the line's own day would build (score_model.build_model as of the day, the
same `settled_shadow_rows` the line evidence uses): once from the history of
--stale-db (a copy taken before refresh_sport_history.py ran) and once from
the current database. The event identities (team ids) come from the current
database for both, so the two differ only in what the model knew.

Per sport: log-loss and Brier of the raw p, and the calibrated confidence the
installed curve prints (lookup without admission, as SPORT_CONFIDENCE reads it)
on lines >= 0.70 - gap and realised - with 95% intervals from a bootstrap over
games.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_sport_history_ab.py \\
        --stale-db data/refit_2026-10-12/sofa_replay.db \\
        --from 2026-10-05 --to 2026-10-11 [--sport basketball] [--json-out f]
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from bet.sofa import sport_confidence as scf
from bet.sofa.config import SofaConfig
from bet.sofa.score_model import load_events
from bet.sofa.shadow import SPORTS
from scripts.sofa.fit_sport_confidence import bb_freshness_on

KEYF = ("game", "family", "period", "line", "side")


def _ll(p: float, y: int) -> float:
    q = min(max(p, 1e-6), 1 - 1e-6)
    return -math.log(q if y else 1.0 - q)


def _days(a: str, b: str) -> list[str]:
    d0, d1 = datetime.fromisoformat(a), datetime.fromisoformat(b)
    return [(d0 + timedelta(days=i)).strftime("%Y-%m-%d")
            for i in range((d1 - d0).days + 1)]


def _boot(by_game: dict[str, list[tuple[float, ...]]], fn: Any,
          reps: int = 1000, seed: int = 7) -> tuple[float, float, float]:
    games = list(by_game)
    est = fn([x for g in games for x in by_game[g]])
    rng = random.Random(seed)
    vals = sorted(fn([x for _ in games for x in by_game[rng.choice(games)]])
                  for _ in range(reps))
    return est, vals[int(0.025 * reps)], vals[int(0.975 * reps) - 1]


def compare(sport: str, stale_db: str, db: str, runs_dir: str, dates: list[str],
            sims: int) -> dict[str, Any]:
    sp = SPORTS[sport]
    fresh_events = load_events(db, sp)
    stale_events = load_events(stale_db, sp)
    fresh_hist = scf.parse_history(fresh_events, sp)
    stale_hist = scf.parse_history(stale_events, sp)
    flag = sport == "basketball" and bb_freshness_on(dates[-1], "auto")
    rows = {}
    for name, hist in (("stale", stale_hist), ("current", fresh_hist)):
        rows[name] = {tuple(r[k] for k in KEYF): r for r in scf.settled_shadow_rows(
            runs_dir, sp, dates, fresh_events, hist, sims, flag)}
    both = sorted(set(rows["stale"]) & set(rows["current"]))
    cal = scf.SportCalibration.load(scf.calibration_path_for(dates[-1]))
    by_game: dict[str, list[tuple[float, ...]]] = defaultdict(list)
    printable: dict[str, dict[str, list[tuple[float, ...]]]] = {
        "stale": defaultdict(list), "current": defaultdict(list)}
    for k in both:
        s, c = rows["stale"][k], rows["current"][k]
        y = int(c["y"])
        by_game[k[0]].append((_ll(c["p"], y) - _ll(s["p"], y),
                              (c["p"] - y) ** 2 - (s["p"] - y) ** 2))
        for name, r in (("stale", s), ("current", c)):
            fam, side = str(r["key"]).split("|")
            conf = None if cal is None else cal.lookup(
                sport, fam, side, float(r["p"]), require_admitted=False)
            if conf is not None and conf.value >= 0.70:
                printable[name][k[0]].append((conf.value, float(y)))
    out: dict[str, Any] = {"sport": sport, "lines_both": len(both),
                           "games": len(by_game),
                           "history_games": {"stale": len(stale_hist),
                                             "current": len(fresh_hist)}}
    if not both:
        return out
    d_ll = _boot(by_game, lambda xs: sum(x[0] for x in xs) / len(xs))
    d_br = _boot(by_game, lambda xs: sum(x[1] for x in xs) / len(xs))
    out["d_logloss_e3"] = [round(1e3 * v, 2) for v in d_ll]
    out["d_brier_e3"] = [round(1e3 * v, 2) for v in d_br]
    for name in ("stale", "current"):
        pg = printable[name]
        n = sum(len(v) for v in pg.values())
        if n == 0:
            out[f"printable_{name}"] = {"lines": 0}
            continue
        gap = _boot(pg, lambda xs: sum(x[1] - x[0] for x in xs) / len(xs))
        out[f"printable_{name}"] = {
            "lines": n, "games": len(pg),
            "confidence": round(sum(x[0] for v in pg.values() for x in v) / n, 4),
            "realised": round(sum(x[1] for v in pg.values() for x in v) / n, 4),
            "gap_pp": [round(100 * v, 1) for v in gap]}
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--stale-db", required=True)
    ap.add_argument("--from", dest="start", required=True)
    ap.add_argument("--to", dest="end", required=True)
    ap.add_argument("--sport", action="append",
                    choices=["hockey", "basketball", "volleyball"])
    ap.add_argument("--sims", type=int, default=1000)
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args()
    config = SofaConfig.from_env()
    dates = _days(args.start, args.end)
    results = [compare(s, args.stale_db, config.db_path, config.runs_dir, dates,
                       args.sims)
               for s in (args.sport or ["hockey", "basketball", "volleyball"])]
    text = json.dumps(results, indent=1)
    print(text)
    if args.json_out:
        Path(args.json_out).write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
