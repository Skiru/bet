#!/usr/bin/env python3
"""Volleyball set length from the history's table (audit 2026-10-13 B9 / C10)
against the i.i.d. rally share. Read-only evidence, never a gate.

Pre-registered in docs/sofa/evidence/volleyball_set_length_2026-10-13.md.

    --mode history   Test A: walk forward over [--start, --end); the model
                     (book + set-length table) rebuilt every REBUILD_DAYS at
                     the game's start and updated game by game, games sharing
                     a start forecast before any is learnt; every n-th game,
                     the old and the new simulation with the same seed; fixed
                     lines per gender from [--lines-start, --start)
    --mode superbet  Test B: Superbet's settled volleyball lines of
                     [--from, --to] priced by both models built at the day's
                     00:00Z (as sport_confidence.settled_shadow_rows); the
                     price is never read

The simulations run in worker processes (--workers); the walk forward itself
is sequential. Paired differences new - old per game, 95% bootstrap by game.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_volleyball_set_length.py \\
        --mode history --events-cache data/audit_2026-10-13/volleyball_events.pkl \\
        --json-out <f>
"""

from __future__ import annotations

import argparse
import gc
import json
import math
import pickle
import random
import sys
import time
from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from multiprocessing import Pool
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO / "src"), str(_REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import sport_confidence as scf  # noqa: E402
from bet.sofa.config import SofaConfig  # noqa: E402
from bet.sofa.football_rating import RatingBook  # noqa: E402
from bet.sofa.score_model import (  # noqa: E402
    DECIDER_TARGET,
    SET_TARGET,
    ScoreModel,
    SetLengthTable,
    _rated_values,
    build_model,
    line_probability,
    load_events,
)
from bet.sofa.shadow import (  # noqa: E402
    MARKETS,
    SPORTS,
    GameResult,
    ShadowLine,
    actual_value,
    grade,
)

VB = SPORTS["volleyball"]
QUANTILES = (0.10, 0.25, 0.50, 0.75, 0.90)
# the families whose p the table must not move (construction guard)
RESULT_FAMILIES = ("winner", "sets_total", "set_handicap", "exact_sets",
                   "set_winner")
SET_FAMILIES = ("set_winner", "set_points_total", "set_points_odd_even",
                "set_extra_points")


def _ts(day: str) -> int:
    return int(datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=UTC).timestamp())


def boot(groups: Sequence[float], reps: int = 2000) -> list[float]:
    if not groups:
        return [float("nan")] * 3
    rng = random.Random(0)
    m = len(groups)
    stats = sorted(sum(groups[rng.randrange(m)] for _ in range(m)) / m
                   for _ in range(reps))
    return [sum(groups) / m, stats[int(0.025 * reps)], stats[int(0.975 * reps) - 1]]


def _line(mid: int, period: int, line: float | None, side: str) -> ShadowLine:
    spec = MARKETS["volleyball"][mid]
    return ShadowLine("", mid, spec.family, period, "", line, side, 1.0)


def _cut(values: list[float]) -> tuple[float, ...]:
    values = sorted(values)
    return tuple(sorted({math.floor(values[int(q * (len(values) - 1))]) + 0.5
                         for q in QUANTILES}))


def history_lines(games: Sequence[scf.HistoryGame]) -> dict[bool, list[ShadowLine]]:
    """The fixed lines per gender, from games before the window."""
    out: dict[bool, list[ShadowLine]] = {}
    for women in (False, True):
        own = [g.result for g in games
               if g.rating.women == women and g.result is not None
               and g.result.t1_periods]
        if not own:
            out[women] = []
            continue
        totals = _cut([sum(r.t1_periods) + sum(r.t2_periods) for r in own])
        margins = _cut([sum(r.t1_periods) - sum(r.t2_periods) for r in own])
        set_totals = _cut([a + b for r in own
                           for a, b in list(zip(r.t1_periods, r.t2_periods,
                                                strict=True))[:4]])
        lines = [_line(230060, 0, c, "OVER") for c in totals]
        lines += [_line(1069, 0, -c, "T1") for c in margins]
        lines += [_line(782, k, c, "OVER") for k in range(1, 6) for c in set_totals]
        lines += [_line(100077, k, None, "YES") for k in range(1, 6)]
        # the result markets: the construction guard (p must not move)
        lines += [_line(745, 0, None, "T1"), _line(230058, 0, 3.5, "OVER"),
                  _line(230058, 0, 4.5, "OVER"), _line(100082, 0, -1.5, "T1"),
                  _line(100082, 0, 1.5, "T1")]
        lines += [_line(785, 0, None, s)
                  for s in ("3:0", "3:1", "3:2", "2:3", "1:3", "0:3")]
        lines += [_line(744, k, None, "T1") for k in range(1, 6)]
        out[women] = lines
    return out


def _clip(p: float, n: int) -> float:
    lo = 0.5 / (n + 1)
    return min(max(p, lo), 1.0 - lo)


def _ll(p: float, y: int) -> float:
    return -math.log(p if y else 1.0 - p)


def _extra_sets(g: GameResult) -> tuple[int, int]:
    """(sets on extra points, sets played)."""
    n = len(g.t1_periods)
    extra = 0
    for i, (a, b) in enumerate(zip(g.t1_periods, g.t2_periods, strict=True)):
        target = DECIDER_TARGET if i == 4 else SET_TARGET
        extra += max(a, b) > target
    return extra, n


def run_task(task: dict[str, Any]) -> dict[str, Any]:
    """Both simulations of one game and every line's (family, p_old, p_new,
    y). History tasks grade their lines on the game's result; Superbet
    tasks carry their settled outcome."""
    n = int(task["sims"])
    table: SetLengthTable | None = task["table"]
    old = ScoreModel(VB, RatingBook(), 6.0)
    new = ScoreModel(VB, RatingBook(), 6.0, set_length=table)
    mu1, mu2, seed, women = task["mu1"], task["mu2"], task["seed"], task["women"]
    so = old.simulate(mu1, mu2, seed=seed, n=n)
    sn = new.simulate(mu1, mu2, seed=seed, n=n, women=women)
    out: list[tuple[str, float, float, int, float]] = []
    result: GameResult | None = task.get("result")
    for line, y in task["lines"]:
        if y is None:
            if result is None:
                continue
            actual = actual_value(line, result, VB)
            if actual is None:
                continue
            outcome = grade(line, actual, False)
            if outcome == "VOID":
                continue
            y = 1 if outcome == "WIN" else 0
        po = line_probability(line, so, VB)
        pn = line_probability(line, sn, VB)
        if po is None or pn is None:
            continue
        out.append((line.family, po, pn, int(y), abs(pn - po)))
    tot_o = sum(sum(g.t1_periods) + sum(g.t2_periods) for g in so) / n
    tot_n = sum(sum(g.t1_periods) + sum(g.t2_periods) for g in sn) / n
    ex_o = [_extra_sets(g) for g in so]
    ex_n = [_extra_sets(g) for g in sn]
    return {
        "game": task["game"], "women": women, "rows": out, "n": n,
        "sim_total": (tot_o, tot_n),
        "sim_extra": (sum(a for a, _ in ex_o), sum(b for _, b in ex_o),
                      sum(a for a, _ in ex_n), sum(b for _, b in ex_n)),
        "actual_total": (None if result is None else
                         sum(result.t1_periods) + sum(result.t2_periods)),
        "actual_extra": None if result is None else _extra_sets(result),
    }


def summarise(results: list[dict[str, Any]]) -> dict[str, Any]:
    per_game: dict[str, dict[str, list[tuple[float, float]]]] = defaultdict(
        lambda: defaultdict(list))
    coin: dict[str, dict[str, list[tuple[float, float]]]] = defaultdict(
        lambda: defaultdict(list))
    calib: dict[str, dict[str, list[tuple[float, int]]]] = defaultdict(
        lambda: {"old": [], "new": []})
    max_dp: dict[str, float] = defaultdict(float)
    lines_n: dict[str, int] = defaultdict(int)
    for res in results:
        n = res["n"]
        for fam, po, pn, y, dp in res["rows"]:
            max_dp[fam] = max(max_dp[fam], dp)
            po_c, pn_c = _clip(po, n), _clip(pn, n)
            per_game[fam][res["game"]].append(
                (_ll(pn_c, y) - _ll(po_c, y), (pn - y) ** 2 - (po - y) ** 2))
            coin[fam][res["game"]].append(
                (_ll(pn_c, y) - _ll(0.5, y), _ll(po_c, y) - _ll(0.5, y)))
            lines_n[fam] += 1
            for key, p in (("old", po), ("new", pn)):
                for side_p, side_y in ((p, y), (1 - p, 1 - y)):
                    if side_p >= 0.70:
                        calib[fam][key].append((side_p, side_y))
    fams: dict[str, Any] = {}
    for fam, games in sorted(per_game.items()):
        ll = [sum(d for d, _ in v) / len(v) for v in games.values()]
        br = [sum(b for _, b in v) / len(v) for v in games.values()]
        cn = [sum(d for d, _ in v) / len(v) for v in coin[fam].values()]
        co = [sum(b for _, b in v) / len(v) for v in coin[fam].values()]
        fams[fam] = {
            "lines": lines_n[fam], "games": len(games),
            "logloss_new_minus_old": boot(ll), "brier_new_minus_old": boot(br),
            "logloss_new_minus_coin": boot(cn), "logloss_old_minus_coin": boot(co),
            "max_abs_dp": round(max_dp[fam], 6),
            "calibration_p_ge_070": {
                k: ({"n": len(v), "p": sum(p for p, _ in v) / len(v),
                     "realised": sum(y for _, y in v) / len(v)} if v else {"n": 0})
                for k, v in calib[fam].items()},
        }
    by_gender: dict[str, Any] = {}
    for women in (False, True):
        rs = [r for r in results if r["women"] == women]
        acts = [r for r in rs if r["actual_total"] is not None]
        if not rs:
            continue
        ex = [r["sim_extra"] for r in rs]
        aex = [r["actual_extra"] for r in acts if r["actual_extra"] is not None]
        by_gender["W" if women else "M"] = {
            "games": len(rs),
            "total_sim_old": sum(r["sim_total"][0] for r in rs) / len(rs),
            "total_sim_new": sum(r["sim_total"][1] for r in rs) / len(rs),
            "total_actual": (sum(r["actual_total"] for r in acts) / len(acts)
                             if acts else None),
            "extra_share_old": sum(e[0] for e in ex) / max(sum(e[1] for e in ex), 1),
            "extra_share_new": sum(e[2] for e in ex) / max(sum(e[3] for e in ex), 1),
            "extra_share_actual": (
                sum(a for a, _ in aex) / max(sum(b for _, b in aex), 1)
                if aex else None),
        }
    return {"families": fams, "by_gender": by_gender}


def pool_run(tasks: list[dict[str, Any]], workers: int) -> list[dict[str, Any]]:
    if workers <= 1:
        return [run_task(t) for t in tasks]
    with Pool(workers) as pool:
        return list(pool.imap(run_task, tasks, chunksize=8))


def load_history(args: argparse.Namespace) -> list[scf.HistoryGame]:
    if args.events_cache and Path(args.events_cache).exists():
        events = pickle.loads(Path(args.events_cache).read_bytes())
    else:
        events = load_events(args.db_path or SofaConfig.from_env().db_path, VB)
    return scf.parse_history(events, VB)


def history_tasks(history: list[scf.HistoryGame], args: argparse.Namespace
                  ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    start, end = _ts(args.start), _ts(args.end)
    lines = history_lines([g for g in history
                           if _ts(args.lines_start) <= g.rating.ts < start])
    ratings = [g.rating for g in history]
    scores = scf.set_scores_of(history)
    window = [g for g in history if start <= g.rating.ts < end]
    step = max(1, len(window) // args.max_games) if args.max_games else 1
    scored = {id(g) for i, g in enumerate(window) if i % step == 0}
    tasks: list[dict[str, Any]] = []
    model: ScoreModel | None = None
    next_rebuild = start
    tables = 0
    i = 0
    while i < len(window):
        ts = window[i].rating.ts
        j = i
        while j < len(window) and window[j].rating.ts == ts:
            j += 1
        batch = window[i:j]
        if model is None or ts >= next_rebuild:
            model = build_model(ratings, VB, ts, set_length=True, set_scores=scores)
            next_rebuild = ts + scf.REBUILD_DAYS * 86400
            tables += model.set_length is not None
        for g in batch:
            if id(g) not in scored or g.result is None:
                continue
            r = g.rating
            exp = model.expected(r.competition_id, r.home_id, r.away_id, r.ts)
            if exp is None:
                continue
            women = model.women_of(r.home_id, r.away_id)
            tasks.append({
                "game": f"h:{r.event_id}", "mu1": exp[0], "mu2": exp[1],
                "seed": r.event_id, "women": women, "table": model.set_length,
                "result": g.result, "sims": args.sims,
                "lines": [(ln, None) for ln in lines[women]]})
        for g in batch:
            model.book.update(_rated_values(g.rating, VB))
            model.note_game(g.rating)
        i = j
    meta = {"window": [args.start, args.end], "lines_from": args.lines_start,
            "games_in_window": len(window), "step": step, "rebuilds_with_table": tables,
            "lines": {("W" if w else "M"): sorted({f"{ln.family}:{ln.line}"
                                                   for ln in ls})
                      for w, ls in lines.items()}}
    return tasks, meta


def superbet_tasks(history: list[scf.HistoryGame], events: dict[int, Any],
                   args: argparse.Namespace
                   ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    from bet.sofa.comparability import competition_id

    ratings = [g.rating for g in history]
    scores = scf.set_scores_of(history)
    allowed = scf.allowed_markets("volleyball", extended=True)
    tasks: list[dict[str, Any]] = []
    day = datetime.strptime(args.date_from, "%Y-%m-%d").replace(tzinfo=UTC)
    last = datetime.strptime(args.date_to, "%Y-%m-%d").replace(tzinfo=UTC)
    dates: list[str] = []
    while day <= last:
        dates.append(day.strftime("%Y-%m-%d"))
        day += timedelta(days=1)
    for date in dates:
        path = Path(args.runs_dir) / "shadow" / "volleyball" / date / "settled.json"
        if not path.exists():
            continue
        doc = json.loads(path.read_text(encoding="utf-8"))
        model = build_model(ratings, VB, scf.day_ts(date), set_length=True,
                            set_scores=scores)
        for sb_id, entry in (doc.get("events") or {}).items():
            try:
                event = events.get(int(entry["sofascore_event_id"]))
            except (KeyError, TypeError, ValueError):
                continue
            if event is None:
                continue
            comp = competition_id(event) or int(event["tournament"]["id"])
            home, away = int(event["homeTeam"]["id"]), int(event["awayTeam"]["id"])
            exp = model.expected(comp, home, away)
            if exp is None:
                continue
            mh, ma = exp
            mu1, mu2 = (mh, ma) if entry.get("home_is_team1") else (ma, mh)
            lines: list[tuple[ShadowLine, int]] = []
            for g in entry.get("graded") or []:
                if g.get("outcome") not in ("WIN", "LOSS"):
                    continue
                if allowed.get(int(g.get("market_id") or 0)) is None:
                    continue
                line = ShadowLine(str(sb_id), int(g["market_id"]), str(g["family"]),
                                  int(g.get("period") or 0),
                                  str(g.get("subject") or ""), g.get("line"),
                                  str(g["side"]), 1.0)
                lines.append((line, 1 if g["outcome"] == "WIN" else 0))
            if lines:
                tasks.append({
                    "game": f"s:{date}:{sb_id}", "mu1": mu1, "mu2": mu2,
                    "seed": int(entry["sofascore_event_id"]),
                    "women": model.women_of(home, away), "table": model.set_length,
                    "result": None, "sims": args.sims, "lines": lines})
    return tasks, {"dates": [args.date_from, args.date_to]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=("history", "superbet"), required=True)
    ap.add_argument("--events-cache", default=None)
    ap.add_argument("--db-path", default=None)
    ap.add_argument("--runs-dir", default="runs/sofa")
    ap.add_argument("--start", default="2025-10-01")
    ap.add_argument("--end", default="2026-10-13")
    ap.add_argument("--lines-start", default="2024-10-01")
    ap.add_argument("--from", dest="date_from", default="2026-09-29")
    ap.add_argument("--to", dest="date_to", default="2026-10-12")
    ap.add_argument("--max-games", type=int, default=6000)
    ap.add_argument("--sims", type=int, default=2000)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--json-out")
    args = ap.parse_args()
    t0 = time.time()
    if args.events_cache and Path(args.events_cache).exists():
        events: dict[int, Any] = pickle.loads(Path(args.events_cache).read_bytes())
    else:
        events = load_events(args.db_path or SofaConfig.from_env().db_path, VB)
    history = scf.parse_history(events, VB)
    if args.mode == "history":
        tasks, meta = history_tasks(history, args)
    else:
        tasks, meta = superbet_tasks(history, events, args)
    del events, history
    gc.collect()
    print(f"{len(tasks)} games to simulate ({time.time() - t0:.0f}s)", flush=True)
    results = pool_run(tasks, args.workers)
    out = {"mode": args.mode, "sims": args.sims, **meta, "games": len(results),
           **summarise(results), "seconds": round(time.time() - t0)}
    text = json.dumps(out, indent=1, default=str)
    print(text)
    if args.json_out:
        Path(args.json_out).write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
