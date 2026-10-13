#!/usr/bin/env python3
"""Basketball pace x efficiency (audit 2026-10-13 B7) against today's points
rating. Read-only evidence, never a gate.

Pre-registered in docs/sofa/evidence/basketball_pace_2026-10-13.md.

    --mode tune      alpha grid of the pace metrics on the tune window:
                     one-step squared error of the regulation total
    --mode history   Test A: walk forward over [--start, --end), both models
                     rebuilt every REBUILD_DAYS and updated game by game;
                     Brier / log-loss at the history's quartile lines (from
                     [--lines-start, --start)) of total, team total and
                     margin, and the winner; paired, bootstrap by game
    --mode superbet  Test B: Superbet's settled basketball lines of
                     [--from, --to] priced by both models built at the day's
                     00:00Z (sport_confidence.settled_shadow_rows); the price
                     only selects the main lines (fair 0.45-0.55)

    SOFA_DB_PATH=<copy> PYTHONPATH=src:. .venv/bin/python \\
        scripts/sofa/measure_basketball_pace.py --mode history \\
        --cache data/audit_2026-10-13/bb_history.pkl --box-cache <f> --json-out <f>
"""

from __future__ import annotations

import argparse
import json
import math
import pickle
import random
import sys
import time
from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO / "src"), str(_REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import sport_confidence as scf  # noqa: E402
from bet.sofa.config import SofaConfig  # noqa: E402
from bet.sofa.football_rating import ALPHA_BY_METRIC, FootballResult  # noqa: E402
from bet.sofa.score_model import (  # noqa: E402
    PACE_METRICS,
    PACE_POSS,
    PACE_PPP,
    ScoreModel,
    _rated_values,
    attach_box,
    build_model,
    load_box_scores,
    load_events,
)
from bet.sofa.shadow import SPORTS, GameResult  # noqa: E402
from scripts.sofa.measure_score_history import _quartile_lines, load  # noqa: E402

BB = SPORTS["basketball"]
REBUILD_DAYS = scf.REBUILD_DAYS
FAMILIES = ("total", "team_total", "handicap", "winner")
Data = list[tuple[FootballResult, GameResult | None]]


def _ts(day: str) -> int:
    return int(datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=UTC).timestamp())


def boot(groups: Sequence[tuple[float, int]], reps: int = 2000
         ) -> list[float]:
    """[mean, lo95, hi95] of sum(diff) / sum(n), resampling games."""
    if not groups:
        return [float("nan")] * 3
    rng = random.Random(0)
    m = len(groups)
    tot = sum(d for d, _ in groups) / max(sum(n for _, n in groups), 1)
    stats = []
    for _ in range(reps):
        s = c = 0.0
        for _ in range(m):
            d, n = groups[rng.randrange(m)]
            s += d
            c += n
        stats.append(s / c if c else 0.0)
    stats.sort()
    return [tot, stats[int(0.025 * reps)], stats[int(0.975 * reps) - 1]]


def _ll(p: float, y: int) -> float:
    return -math.log(p if y else 1.0 - p)


def with_box(data: Data, box: dict[int, str]) -> Data:
    out: Data = []
    for r, g in data:
        if g is not None and r.event_id in box:
            r = attach_box(r, box[r.event_id], float(g.t1_full), float(g.t2_full),
                           g.overtime)
        out.append((r, g))
    return out


def load_box(db_path: str, data: Data, cache: str | None) -> dict[int, str]:
    if cache and Path(cache).exists():
        got: dict[int, str] = pickle.loads(Path(cache).read_bytes())
        return got
    box = load_box_scores(db_path, (r.event_id for r, _ in data))
    if cache:
        Path(cache).parent.mkdir(parents=True, exist_ok=True)
        Path(cache).write_bytes(pickle.dumps(box))
    return box


def reg(g: GameResult) -> tuple[int, int]:
    return sum(g.t1_periods), sum(g.t2_periods)


# --- tune ----------------------------------------------------------------------


def tune(data: Data, start: int, end: int, grid_poss: Sequence[float],
         grid_ppp: Sequence[float]) -> dict[str, Any]:
    ratings = [r for r, _ in data]
    games = [(r, g) for r, g in data if start <= r.ts < end
             and g is not None and len(g.t1_periods) == 4]
    out: list[dict[str, Any]] = []
    for ap_ in grid_poss:
        for ae in grid_ppp:
            ALPHA_BY_METRIC[PACE_POSS], ALPHA_BY_METRIC[PACE_PPP] = ap_, ae
            model = build_model(ratings, BB, start, pace=True)
            base = ScoreModel(BB, model.book, model.period_sd, model.shares)
            se_new = se_old = 0.0
            n = 0
            idx = {id(r): g for r, g in games}
            for r in ratings:
                if r.ts < start:
                    continue
                if r.ts >= end:
                    break
                g = idx.get(id(r))
                if g is not None:
                    pe = model.pace_expected(r.competition_id, r.home_id,
                                             r.away_id, r.ts)
                    eo = base.expected(r.competition_id, r.home_id, r.away_id)
                    if pe is not None and eo is not None:
                        y = sum(reg(g))
                        se_new += (sum(pe) - y) ** 2
                        se_old += (sum(eo[0]) + sum(eo[1]) - y) ** 2
                        n += 1
                model.book.update(_rated_values(r, BB))
                model.note_game(r)
            out.append({"alpha_poss": ap_, "alpha_ppp": ae, "games": n,
                        "mse_pace": se_new / max(n, 1),
                        "mse_points_same_games": se_old / max(n, 1)})
            print(json.dumps(out[-1]), file=sys.stderr, flush=True)
    best = min(out, key=lambda x: x["mse_pace"])
    return {"grid": out, "best": best}


# --- Test A: history -------------------------------------------------------------


def _family_probs(sims: list[GameResult], lines: dict[str, list[float]]
                  ) -> dict[str, list[float]]:
    """P(quantity > line) per family and line; team_total: home lines then
    away lines; winner: P(team1 wins)."""
    n = len(sims)
    regs = [reg(s) for s in sims]

    def frac(values: Sequence[int], c: float) -> float:
        k = sum(1 for v in values if v > c)
        return (k + 0.5) / (n + 1.0)

    tot = [a + b for a, b in regs]
    t1 = [a for a, _ in regs]
    t2 = [b for _, b in regs]
    mar = [a - b for a, b in regs]
    out: dict[str, list[float]] = {
        "total": [frac(tot, c) for c in lines["total"]],
        "team_total": ([frac(t1, c) for c in lines["team_total"]]
                       + [frac(t2, c) for c in lines["team_total"]]),
        "handicap": [frac(mar, c) for c in lines["margin"]],
    }
    w = sum(1 for s in sims if s.winner == "T1")
    out["winner"] = [(w + 0.5) / (n + 1.0)]
    return out


def _family_outcomes(g: GameResult, lines: dict[str, list[float]]
                     ) -> dict[str, list[int]]:
    a, b = reg(g)
    return {
        "total": [int(a + b > c) for c in lines["total"]],
        "team_total": ([int(a > c) for c in lines["team_total"]]
                       + [int(b > c) for c in lines["team_total"]]),
        "handicap": [int(a - b > c) for c in lines["margin"]],
        "winner": [int(g.winner == "T1")],
    }


def history_test(data: Data, lines_start: int, start: int, end: int,
                 max_games: int, sims: int) -> dict[str, Any]:
    ratings = [r for r, _ in data]
    ref = [g for r, g in data if lines_start <= r.ts < start
           and g is not None and len(g.t1_periods) == 4]
    lines = {
        "total": _quartile_lines([float(sum(reg(g))) for g in ref]),
        "team_total": _quartile_lines([float(v) for g in ref for v in reg(g)]),
        "margin": _quartile_lines([float(reg(g)[0] - reg(g)[1]) for g in ref]),
    }
    window = [(r, g) for r, g in data if start <= r.ts < end]
    step = max(1, len(window) // max_games)
    scored = {id(r) for i, (r, _) in enumerate(window) if i % step == 0}
    diffs: dict[str, dict[str, list[tuple[float, int]]]] = {
        m: defaultdict(list) for m in ("brier", "logloss")}
    diffs_pace: dict[str, dict[str, list[tuple[float, int]]]] = {
        m: defaultdict(list) for m in ("brier", "logloss")}
    absolute: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    calib: dict[str, list[tuple[float, int]]] = {"old": [], "new": []}
    n_games = n_pace = 0
    old: ScoreModel | None = None
    new: ScoreModel | None = None
    next_rebuild = start
    t0 = time.monotonic()
    i = 0
    while i < len(window):
        ts = window[i][0].ts
        j = i
        while j < len(window) and window[j][0].ts == ts:
            j += 1
        batch = window[i:j]
        if old is None or new is None or ts >= next_rebuild:
            old = build_model(ratings, BB, ts)
            new = build_model(ratings, BB, ts, pace=True)
            for m in (old, new):
                if m.recent is None:
                    m.recent = {}
            next_rebuild = ts + REBUILD_DAYS * 86400
            print(f"rebuild {datetime.fromtimestamp(ts, UTC):%Y-%m-%d} "
                  f"games {n_games} {time.monotonic() - t0:.0f} s",
                  file=sys.stderr, flush=True)
        for r, g in batch:
            if id(r) not in scored or g is None or len(g.t1_periods) != 4:
                continue
            eo = old.expected(r.competition_id, r.home_id, r.away_id, r.ts)
            en = new.expected(r.competition_id, r.home_id, r.away_id, r.ts)
            if eo is None or en is None:
                continue
            paced = new.pace_expected(r.competition_id, r.home_id, r.away_id,
                                      r.ts) is not None
            so = old.simulate(eo[0], eo[1], seed=r.event_id, n=sims,
                              noise_mult=old.noise_mult(r.home_id, r.away_id, r.ts))
            sn = new.simulate(en[0], en[1], seed=r.event_id, n=sims,
                              noise_mult=new.noise_mult(r.home_id, r.away_id, r.ts))
            po, pn = _family_probs(so, lines), _family_probs(sn, lines)
            ys = _family_outcomes(g, lines)
            n_games += 1
            n_pace += paced
            for fam in FAMILIES:
                bo = sum((p - y) ** 2 for p, y in zip(po[fam], ys[fam], strict=True))
                bn = sum((p - y) ** 2 for p, y in zip(pn[fam], ys[fam], strict=True))
                lo = sum(_ll(p, y) for p, y in zip(po[fam], ys[fam], strict=True))
                ln = sum(_ll(p, y) for p, y in zip(pn[fam], ys[fam], strict=True))
                k = len(ys[fam])
                diffs["brier"][fam].append((bn - bo, k))
                diffs["logloss"][fam].append((ln - lo, k))
                if paced:
                    diffs_pace["brier"][fam].append((bn - bo, k))
                    diffs_pace["logloss"][fam].append((ln - lo, k))
                absolute[fam]["brier_old"] += bo
                absolute[fam]["brier_new"] += bn
                absolute[fam]["n"] += k
                if fam == "total":
                    for key, ps in (("old", po[fam]), ("new", pn[fam])):
                        for p, y in zip(ps, ys[fam], strict=True):
                            for sp, sy in ((p, y), (1 - p, 1 - y)):
                                if sp >= 0.70:
                                    calib[key].append((sp, sy))
        for r, _ in batch:
            for m in (old, new):
                m.book.update(_rated_values(r, BB))
                m.note_game(r)
                if m.recent is not None:
                    m.recent.setdefault(r.home_id, []).append(r.ts)
                    m.recent.setdefault(r.away_id, []).append(r.ts)
        i = j
    return {
        "lines": lines, "games": n_games, "games_pace_path": n_pace,
        "new_minus_old": {m: {f: boot(v[f]) for f in FAMILIES}
                          for m, v in diffs.items()},
        "new_minus_old_pace_path_only": {m: {f: boot(v[f]) for f in FAMILIES}
                                         for m, v in diffs_pace.items()},
        "absolute_brier": {f: {"old": v["brier_old"] / max(v["n"], 1),
                               "new": v["brier_new"] / max(v["n"], 1),
                               "lines": int(v["n"])}
                           for f, v in absolute.items()},
        "total_calibration_p_ge_070": {
            k: {"n": len(v), "p": sum(p for p, _ in v) / len(v),
                "realised": sum(y for _, y in v) / len(v)} if v else {"n": 0}
            for k, v in calib.items()},
    }


# --- Test B: Superbet lines ------------------------------------------------------


def _fair(runs_dir: str, dates: Sequence[str]) -> dict[tuple[Any, ...], float]:
    out: dict[tuple[Any, ...], float] = {}
    for d in dates:
        path = Path(runs_dir) / "shadow" / "basketball" / d / "settled.json"
        if not path.exists():
            continue
        doc = json.loads(path.read_text(encoding="utf-8"))
        for sb_id, entry in (doc.get("events") or {}).items():
            for g in entry.get("graded") or []:
                if isinstance(g.get("fair_p"), (int, float)):
                    out[(f"s:{d}:{sb_id}", int(g["market_id"]),
                         int(g.get("period") or 0), str(g.get("subject") or ""),
                         g.get("line"), str(g["side"]))] = float(g["fair_p"])
    return out


def _row_key(r: dict[str, Any]) -> tuple[Any, ...]:
    return (r["game"], r["market_id"], r["period"], r["subject"], r["line"],
            r["side"])


def superbet_test(db_path: str, runs_dir: str, data: Data, box: dict[int, str],
                  date_from: str, date_to: str, sims: int,
                  events_cache: str | None) -> dict[str, Any]:
    if events_cache and Path(events_cache).exists():
        events: dict[int, Any] = pickle.loads(Path(events_cache).read_bytes())
    else:
        events = load_events(db_path, BB)
        if events_cache:
            Path(events_cache).write_bytes(pickle.dumps(events))
    history = scf.parse_history(events, BB, box)
    d0 = datetime.strptime(date_from, "%Y-%m-%d")
    d1 = datetime.strptime(date_to, "%Y-%m-%d")
    dates = [(d0 + timedelta(days=k)).strftime("%Y-%m-%d")
             for k in range((d1 - d0).days + 1)]
    common: dict[str, Any] = {"freshness": True, "overtime": False,
                              "strict_league_rate": False}
    old = scf.settled_shadow_rows(runs_dir, BB, dates, events, history, sims,
                                  pace=False, **common)
    new = scf.settled_shadow_rows(runs_dir, BB, dates, events, history, sims,
                                  pace=True, **common)
    fair = _fair(runs_dir, dates)
    nmap = {_row_key(r): r for r in new}
    per_game: dict[str, dict[str, dict[str, list[float]]]] = {
        m: defaultdict(lambda: defaultdict(lambda: [0.0, 0.0])) for m in
        ("brier", "logloss")}
    main: dict[str, list[tuple[float, float, int, str]]] = defaultdict(list)
    absolute: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0, 0.0])
    changed = 0
    games: dict[str, set[str]] = defaultdict(set)
    for r in old:
        fam = r["family"]
        if fam not in FAMILIES:
            continue
        rn = nmap.get(_row_key(r))
        if rn is None:
            continue
        y = int(r["y"])
        po = min(max(float(r["p"]), 1e-4), 1 - 1e-4)
        pn = min(max(float(rn["p"]), 1e-4), 1 - 1e-4)
        changed += po != pn
        games[fam].add(r["game"])
        for m, d in (("brier", (pn - y) ** 2 - (po - y) ** 2),
                     ("logloss", _ll(pn, y) - _ll(po, y))):
            cell = per_game[m][fam][r["game"]]
            cell[0] += d
            cell[1] += 1
        absolute[fam][0] += (po - y) ** 2
        absolute[fam][1] += (pn - y) ** 2
        absolute[fam][2] += 1
        fp = fair.get(_row_key(r))
        if fp is not None and 0.45 <= fp <= 0.55:
            main[fam].append((po, pn, y, r["game"]))
    out_main: dict[str, Any] = {}
    for fam, rows in main.items():
        g: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0])
        for po, pn, y, gid in rows:
            g[gid][0] += (pn - y) ** 2 - (po - y) ** 2
            g[gid][1] += 1
        out_main[fam] = {
            "lines": len(rows), "games": len(g),
            "brier_old": sum((po - y) ** 2 for po, _, y, _ in rows) / len(rows),
            "brier_new": sum((pn - y) ** 2 for _, pn, y, _ in rows) / len(rows),
            "diff": boot([(a, int(b)) for a, b in g.values()]),
        }
    return {
        "dates": [date_from, date_to], "rows_old": len(old), "rows_new": len(new),
        "rows_with_changed_p": changed,
        "games": {f: len(v) for f, v in games.items()},
        "new_minus_old": {m: {f: boot([(a, int(b)) for a, b in v[f].values()])
                              for f in FAMILIES if f in v}
                          for m, v in per_game.items()},
        "absolute_brier": {f: {"old": v[0] / v[2], "new": v[1] / v[2],
                               "lines": int(v[2])} for f, v in absolute.items()},
        "main_lines_fair_045_055": out_main,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--mode", choices=("tune", "history", "superbet"), required=True)
    ap.add_argument("--cache", default=None, help="measure_score_history pickle")
    ap.add_argument("--box-cache", default=None)
    ap.add_argument("--events-cache", default=None)
    ap.add_argument("--tune-start", default="2025-01-01")
    ap.add_argument("--tune-end", default="2025-06-01")
    ap.add_argument("--lines-start", default="2025-01-01")
    ap.add_argument("--start", default="2025-10-01")
    ap.add_argument("--end", default="2026-06-01")
    ap.add_argument("--from", dest="date_from", default="2026-09-29")
    ap.add_argument("--to", dest="date_to", default="2026-10-12")
    ap.add_argument("--max-games", type=int, default=6000)
    ap.add_argument("--sims", type=int, default=1000)
    ap.add_argument("--alpha", default=None,
                    help="poss,ppp alphas (default: score_model.PACE_ALPHA)")
    ap.add_argument("--json-out")
    args = ap.parse_args()
    config = SofaConfig.from_env()
    data = load(config.db_path, BB, args.cache, union=True)
    box = load_box(config.db_path, data, args.box_cache)
    data = with_box(data, box)
    if args.alpha:
        a_p, a_e = (float(x) for x in args.alpha.split(","))
        ALPHA_BY_METRIC[PACE_POSS], ALPHA_BY_METRIC[PACE_PPP] = a_p, a_e
    out: dict[str, Any] = {
        "mode": args.mode, "db_path": config.db_path, "games_in_history": len(data),
        "games_with_box": sum(1 for r, _ in data if PACE_POSS in r.values),
        "alpha": {m: ALPHA_BY_METRIC.get(m) for m in PACE_METRICS},
    }
    if args.mode == "tune":
        out["tune"] = tune(data, _ts(args.tune_start), _ts(args.tune_end),
                           (0.03, 0.06, 0.10, 0.15), (0.03, 0.06, 0.10))
    elif args.mode == "history":
        out["window"] = [args.start, args.end]
        out["history"] = history_test(data, _ts(args.lines_start), _ts(args.start),
                                      _ts(args.end), args.max_games, args.sims)
    else:
        out["superbet"] = superbet_test(config.db_path, config.runs_dir, data, box,
                                        args.date_from, args.date_to, args.sims,
                                        args.events_cache)
    text = json.dumps(out, indent=1)
    print(text)
    if args.json_out:
        Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json_out).write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
