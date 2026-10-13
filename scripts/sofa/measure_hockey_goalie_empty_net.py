#!/usr/bin/env python3
"""Hockey shots x conversion (team save%) and the fitted empty net (audit
2026-10-13 B8) against today's goals model. Read-only evidence, never a gate.

Pre-registered in docs/sofa/evidence/hockey_goalie_empty_net_2026-10-13.md.

    --mode tune-shots     alpha grid of the shot metrics on the tune window:
                          one-step squared error of a side's regulation goals
                          on the games the shots path reads
    --mode fit-empty-net  moments of the final regulation margin on the tune
                          window against the model's pre-late Skellam margin:
                          (e1, e2, t); NHL emptyNetGoals reported as a check
    --mode history        Test A: walk forward over [--start, --end), every
                          arm rebuilt every REBUILD_DAYS and updated game by
                          game; log-loss / Brier at fixed standard lines of
                          total, team total, margin and the winner (+ the
                          regulation 1X2); paired, bootstrap by game
    --mode superbet       Test B: Superbet's settled hockey lines of
                          [--from, --to] priced by every arm built at the
                          day's 00:00Z (sport_confidence.settled_shadow_rows)

    SOFA_DB_PATH=<copy> SOFA_RUNS_DIR=<runs/sofa> PYTHONPATH=src:. \\
        .venv/bin/python scripts/sofa/measure_hockey_goalie_empty_net.py \\
        --mode history --cache <f> --box-cache <f> --json-out <f>
"""

from __future__ import annotations

import argparse
import dataclasses
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

from bet.sofa import score_model as sm  # noqa: E402
from bet.sofa import sport_confidence as scf  # noqa: E402
from bet.sofa.config import SofaConfig  # noqa: E402
from bet.sofa.football_rating import ALPHA_BY_METRIC, FootballResult  # noqa: E402
from bet.sofa.shadow import SPORTS, GameResult  # noqa: E402
from scripts.sofa.measure_score_history import load  # noqa: E402

HK = SPORTS["hockey"]
REBUILD_DAYS = scf.REBUILD_DAYS
NHL = 234
# fixed in the pre-registration, never from a price
LINES = {
    "total": [4.5, 5.5, 6.5],
    "team_total": [1.5, 2.5, 3.5],
    "margin": [-2.5, -1.5, -0.5, 0.5, 1.5, 2.5],
}
FAMILIES = ("total", "team_total", "handicap", "winner")
ARMS = ("replace", "blend", "empty_net")
Data = list[tuple[FootballResult, GameResult | None]]


def _ts(day: str) -> int:
    return int(datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=UTC).timestamp())


def boot(groups: Sequence[tuple[float, int]], reps: int = 2000,
         level: float = 0.95) -> list[float]:
    """[mean, lo, hi] of sum(diff) / sum(n), resampling games."""
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
    a = (1.0 - level) / 2
    return [tot, stats[int(a * reps)], stats[int((1 - a) * reps) - 1]]


def _ll(p: float, y: int) -> float:
    p = min(max(p, 1e-6), 1 - 1e-6)
    return -math.log(p if y else 1.0 - p)


def reg(g: GameResult) -> tuple[int, int]:
    return sum(g.t1_periods), sum(g.t2_periods)


def load_box(db_path: str, data: Data, cache: str | None) -> dict[int, str]:
    if cache and Path(cache).exists():
        got: dict[int, str] = pickle.loads(Path(cache).read_bytes())
        return got
    box = sm.load_box_scores(db_path, (r.event_id for r, _ in data))
    if cache:
        Path(cache).parent.mkdir(parents=True, exist_ok=True)
        Path(cache).write_bytes(pickle.dumps(box))
    return box


def with_shots(data: Data, box: dict[int, str]) -> Data:
    out: Data = []
    for r, g in data:
        if g is not None and r.event_id in box:
            r = sm.attach_hockey_shots(r, box[r.event_id], g.overtime)
        out.append((r, g))
    return out


def _arm_model(ratings: Sequence[FootballResult], ts: int, arm: str
               ) -> sm.ScoreModel:
    if arm == "base":
        return sm.build_model(ratings, HK, ts, strict_league_rate=True)
    if arm == "empty_net":
        return sm.build_model(ratings, HK, ts,
                              sm.empty_net_params(None, "hockey", True),
                              strict_league_rate=True)
    return sm.build_model(ratings, HK, ts, strict_league_rate=True, shots=arm)


# --- tune ----------------------------------------------------------------------


def tune(data: Data, start: int, end: int, grid_shots: Sequence[float],
         grid_conv: Sequence[float]) -> dict[str, Any]:
    ratings = [r for r, _ in data]
    graded = {id(r) for r, g in data if g is not None}
    out: list[dict[str, Any]] = []
    for a_s in grid_shots:
        for a_c in grid_conv:
            ALPHA_BY_METRIC[sm.HK_SHOTS], ALPHA_BY_METRIC[sm.HK_CONV] = a_s, a_c
            model = sm.build_model(ratings, HK, start, strict_league_rate=True,
                                   shots="replace")
            se_new = se_old = 0.0
            n = 0
            for r in ratings:
                if r.ts < start:
                    continue
                if r.ts >= end:
                    break
                if id(r) in graded:
                    se = model.shots_expected(r.competition_id, r.home_id,
                                              r.away_id, r.ts)
                    exp = model.book.expected(
                        r.competition_id, r.home_id, r.away_id,
                        sm.REG_METRIC["hockey"],
                        *_link(model, r))
                    y = r.values.get(sm.REG_METRIC["hockey"])
                    if se is not None and exp is not None and y is not None:
                        se_new += (se[0] - y[0]) ** 2 + (se[1] - y[1]) ** 2
                        se_old += (exp[0] - y[0]) ** 2 + (exp[1] - y[1]) ** 2
                        n += 2
                model.book.update(sm._rated_values(r, HK))
                model.note_game(r)
            out.append({"alpha_shots": a_s, "alpha_conv": a_c, "sides": n,
                        "mse_shots": se_new / max(n, 1),
                        "mse_goals_same_sides": se_old / max(n, 1)})
            print(json.dumps(out[-1]), file=sys.stderr, flush=True)
    best = min(out, key=lambda x: x["mse_shots"])
    return {"grid": out, "best": best}


def _link(model: sm.ScoreModel, r: FootballResult) -> tuple[float, bool, bool]:
    status, lf = model.book.link(r.home_id, r.away_id, sm.REG_METRIC["hockey"])
    return lf, status != "LINKED", True


# --- empty net fit ---------------------------------------------------------------


def _skellam_abs(mu1: float, mu2: float, kmax: int = 4) -> list[float]:
    """P(|X - Y| = k) for k = 0..kmax-1 and P(>= kmax) last, X ~ Poisson(mu1),
    Y ~ Poisson(mu2)."""
    n = 25

    def pois(mu: float) -> list[float]:
        out = [math.exp(-mu)]
        for i in range(1, n):
            out.append(out[-1] * mu / i)
        return out

    px, py = pois(mu1), pois(mu2)
    dist = [0.0] * (kmax + 1)
    for i, a in enumerate(px):
        for j, b in enumerate(py):
            d = abs(i - j)
            dist[min(d, kmax)] += a * b
    return dist


def fit_empty_net(data: Data, box: dict[int, str], start: int, end: int
                  ) -> dict[str, Any]:
    ratings = [r for r, _ in data]
    games = [(r, g) for r, g in data if start <= r.ts < end and g is not None]
    by_id = {id(r): g for r, g in games}
    model = sm.build_model(ratings, HK, start, strict_league_rate=True)
    next_rebuild = start + REBUILD_DAYS * 86400
    p_sum = [0.0] * 5
    f_cnt = [0] * 5
    n = 0
    for r in ratings:
        if r.ts < start:
            continue
        if r.ts >= end:
            break
        if r.ts >= next_rebuild:
            model = sm.build_model(ratings, HK, r.ts, strict_league_rate=True)
            next_rebuild = r.ts + REBUILD_DAYS * 86400
        g = by_id.get(id(r))
        if g is not None:
            exp = model.expected(r.competition_id, r.home_id, r.away_id, r.ts)
            if exp is not None:
                dist = _skellam_abs(sum(exp[0]), sum(exp[1]))
                for k in range(5):
                    p_sum[k] += dist[k]
                a, b = reg(g)
                f_cnt[min(abs(a - b), 4)] += 1
                n += 1
        model.book.update(sm._rated_values(r, HK))
    pm = [x / n for x in p_sum]
    fm = [x / n for x in f_cnt]
    t = (fm[0] - pm[0]) / pm[1]
    e2 = (fm[3] - pm[3]) / pm[2]
    e1 = (fm[2] - pm[2] * (1 - e2 - t)) / pm[1]

    def clip(x: float) -> float:
        return min(max(x, 0.0), 0.6)

    # NHL check: the leader's empty-net goal by the margin before it
    nhl: dict[int, list[int]] = {1: [0, 0], 2: [0, 0]}
    for r, g in games:
        if r.competition_id != NHL or r.event_id not in box:
            continue
        items = sm._box_items(box[r.event_id])
        if "Shots" not in items:
            continue  # no statistics of this game at all
        en = items.get("emptyNetGoals")
        eh = int(en.get("homeValue") or 0) if en else 0
        ea = int(en.get("awayValue") or 0) if en else 0
        a, b = reg(g)
        if a == b:
            continue
        lead_en, trail_en = (eh, ea) if a > b else (ea, eh)
        if trail_en:
            continue
        pre = abs(a - b) - lead_en
        if pre in nhl:
            nhl[pre][0] += 1
            nhl[pre][1] += int(lead_en > 0)
    return {
        "games": n, "pre_late_P": pm, "history_F": fm,
        "raw": {"e1": e1, "e2": e2, "t": t},
        "fitted": {"e1": clip(e1), "e2": clip(e2), "t": clip(t)},
        "nhl_check_leader_en_by_pre_margin": {
            str(k): {"games": v[0], "with_en": v[1],
                     "share": v[1] / v[0] if v[0] else None}
            for k, v in nhl.items()},
    }


# --- Test A: history -------------------------------------------------------------


def _probs(sims: list[GameResult]) -> dict[str, list[float]]:
    n = len(sims)
    regs = [reg(s) for s in sims]

    def frac(values: Sequence[int], c: float) -> float:
        k = sum(1 for v in values if v > c)
        return (k + 0.5) / (n + 1.0)

    tot = [a + b for a, b in regs]
    t1 = [a for a, _ in regs]
    t2 = [b for _, b in regs]
    mar = [a - b for a, b in regs]
    out = {
        "total": [frac(tot, c) for c in LINES["total"]],
        "team_total": ([frac(t1, c) for c in LINES["team_total"]]
                       + [frac(t2, c) for c in LINES["team_total"]]),
        "handicap": [frac(mar, c) for c in LINES["margin"]],
    }
    w = sum(1 for s in sims if s.winner == "T1")
    out["winner"] = [(w + 0.5) / (n + 1.0)]
    h = sum(1 for m in mar if m > 0)
    d = sum(1 for m in mar if m == 0)
    out["x3"] = [(h + 0.5) / (n + 1.5), (d + 0.5) / (n + 1.5),
                 (n - h - d + 0.5) / (n + 1.5)]
    return out


def _outcomes(g: GameResult) -> dict[str, list[int]]:
    a, b = reg(g)
    return {
        "total": [int(a + b > c) for c in LINES["total"]],
        "team_total": ([int(a > c) for c in LINES["team_total"]]
                       + [int(b > c) for c in LINES["team_total"]]),
        "handicap": [int(a - b > c) for c in LINES["margin"]],
        "winner": [int(g.winner == "T1")],
        "x3": [int(a > b), int(a == b), int(a < b)],
    }


def history_test(data: Data, start: int, end: int, max_games: int, sims: int,
                 arms: Sequence[str]) -> dict[str, Any]:
    ratings = [r for r, _ in data]
    window = [(r, g) for r, g in data if start <= r.ts < end]
    step = max(1, len(window) // max_games)
    scored = {id(r) for i, (r, _) in enumerate(window) if i % step == 0}
    fams = (*FAMILIES, "x3")
    diffs: dict[str, dict[str, dict[str, list[tuple[float, int]]]]] = {
        a: {m: defaultdict(list) for m in ("brier", "logloss")} for a in arms}
    diffs_path: dict[str, dict[str, list[tuple[float, int]]]] = {
        a: defaultdict(list) for a in arms}
    absolute: dict[str, dict[str, list[float]]] = {
        a: defaultdict(lambda: [0.0, 0.0, 0.0]) for a in ("base", *arms)}
    calib: dict[str, list[tuple[float, int]]] = defaultdict(list)
    n_games = 0
    n_path: dict[str, int] = defaultdict(int)
    models: dict[str, sm.ScoreModel] = {}
    next_rebuild = start
    t0 = time.monotonic()
    i = 0
    while i < len(window):
        ts = window[i][0].ts
        j = i
        while j < len(window) and window[j][0].ts == ts:
            j += 1
        batch = window[i:j]
        if not models or ts >= next_rebuild:
            models = {a: _arm_model(ratings, ts, a) for a in ("base", *arms)}
            next_rebuild = ts + REBUILD_DAYS * 86400
            print(f"rebuild {datetime.fromtimestamp(ts, UTC):%Y-%m-%d} "
                  f"games {n_games} {time.monotonic() - t0:.0f} s",
                  file=sys.stderr, flush=True)
        for r, g in batch:
            if id(r) not in scored or g is None:
                continue
            exps = {a: m.expected(r.competition_id, r.home_id, r.away_id, r.ts)
                    for a, m in models.items()}
            if any(e is None for e in exps.values()):
                continue
            probs = {}
            for a, m in models.items():
                e = exps[a]
                assert e is not None
                probs[a] = _probs(m.simulate(e[0], e[1], seed=r.event_id, n=sims))
            ys = _outcomes(g)
            n_games += 1
            for a in arms:
                on_path = (a != "empty_net" and models[a].shots_expected(
                    r.competition_id, r.home_id, r.away_id, r.ts) is not None)
                n_path[a] += on_path
                for fam in fams:
                    po, pn, y = probs["base"][fam], probs[a][fam], ys[fam]
                    if fam == "x3":
                        lo = -math.log(sum(p * yy for p, yy in zip(po, y, strict=True)))
                        ln = -math.log(sum(p * yy for p, yy in zip(pn, y, strict=True)))
                        bo = sum((p - yy) ** 2 for p, yy in zip(po, y, strict=True))
                        bn = sum((p - yy) ** 2 for p, yy in zip(pn, y, strict=True))
                        k = 1
                    else:
                        bo = sum((p - yy) ** 2 for p, yy in zip(po, y, strict=True))
                        bn = sum((p - yy) ** 2 for p, yy in zip(pn, y, strict=True))
                        lo = sum(_ll(p, yy) for p, yy in zip(po, y, strict=True))
                        ln = sum(_ll(p, yy) for p, yy in zip(pn, y, strict=True))
                        k = len(y)
                    diffs[a]["brier"][fam].append((bn - bo, k))
                    diffs[a]["logloss"][fam].append((ln - lo, k))
                    if on_path:
                        diffs_path[a][fam].append((ln - lo, k))
            for a, pr in probs.items():
                for fam in fams:
                    if fam == "x3":
                        continue
                    cell = absolute[a][fam]
                    pairs = list(zip(pr[fam], ys[fam], strict=True))
                    cell[0] += sum((p - yy) ** 2 for p, yy in pairs)
                    cell[1] += sum(_ll(p, yy) for p, yy in pairs)
                    cell[2] += len(ys[fam])
                    for p, yy in zip(pr[fam], ys[fam], strict=True):
                        for sp, sy in ((p, yy), (1 - p, 1 - yy)):
                            if sp >= 0.70:
                                calib[f"{a}|{fam}"].append((sp, sy))
        for r, _ in batch:
            for m in models.values():
                m.book.update(sm._rated_values(r, HK))
                m.note_game(r)
        i = j
    res: dict[str, Any] = {"lines": LINES, "games": n_games,
                           "games_on_shots_path": dict(n_path)}
    for a in arms:
        level = 0.975 if a in ("replace", "blend") else 0.95
        res[a] = {
            "interval_level": level,
            "minus_base": {m: {f: boot(v[f], level=level) for f in fams}
                           for m, v in diffs[a].items()},
            "logloss_minus_base_shots_path_only": {
                f: boot(diffs_path[a][f], level=level) for f in fams
                if diffs_path[a][f]},
        }
    res["absolute"] = {a: {f: {"brier": v[0] / v[2], "logloss": v[1] / v[2],
                               "lines": int(v[2])} for f, v in d.items()}
                       for a, d in absolute.items()}
    res["calibration_p_ge_070"] = {
        k: {"n": len(v), "p": sum(p for p, _ in v) / len(v),
            "realised": sum(y for _, y in v) / len(v)}
        for k, v in sorted(calib.items()) if v}
    return res


# --- Test B: Superbet lines ------------------------------------------------------


def _fair(runs_dir: str, dates: Sequence[str]) -> dict[tuple[Any, ...], float]:
    out: dict[tuple[Any, ...], float] = {}
    for d in dates:
        path = Path(runs_dir) / "shadow" / "hockey" / d / "settled.json"
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


def superbet_test(db_path: str, runs_dir: str, box: dict[int, str],
                  date_from: str, date_to: str, sims: int,
                  events_cache: str | None, arms: Sequence[str]
                  ) -> dict[str, Any]:
    if events_cache and Path(events_cache).exists():
        events: dict[int, Any] = pickle.loads(Path(events_cache).read_bytes())
    else:
        events = sm.load_events(db_path, HK)
        if events_cache:
            Path(events_cache).write_bytes(pickle.dumps(events))
    history = scf.parse_history(events, HK, box)
    d0 = datetime.strptime(date_from, "%Y-%m-%d")
    d1 = datetime.strptime(date_to, "%Y-%m-%d")
    dates = [(d0 + timedelta(days=k)).strftime("%Y-%m-%d")
             for k in range((d1 - d0).days + 1)]
    common: dict[str, Any] = {"freshness": False, "overtime": False,
                              "strict_league_rate": True, "pace": False,
                              "pace_level": False}
    base = scf.settled_shadow_rows(runs_dir, HK, dates, events, history, sims,
                                   hk_shots="off", hk_empty_net=False, **common)
    fair = _fair(runs_dir, dates)
    out: dict[str, Any] = {"dates": [date_from, date_to], "rows_base": len(base)}
    for a in arms:
        kw: dict[str, Any] = ({"hk_shots": "off", "hk_empty_net": True}
                              if a == "empty_net"
                              else {"hk_shots": a, "hk_empty_net": False})
        new = scf.settled_shadow_rows(runs_dir, HK, dates, events, history, sims,
                                      **kw, **common)
        nmap = {_row_key(r): r for r in new}
        per_game: dict[str, dict[str, dict[str, list[float]]]] = {
            m: defaultdict(lambda: defaultdict(lambda: [0.0, 0.0]))
            for m in ("brier", "logloss")}
        main: dict[str, dict[str, list[float]]] = defaultdict(
            lambda: defaultdict(lambda: [0.0, 0.0]))
        main_abs: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0, 0.0])
        changed = 0
        games: dict[str, set[str]] = defaultdict(set)
        for r in base:
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
            fp = fair.get(_row_key(r))
            if fp is not None and 0.45 <= fp <= 0.55:
                c = main[fam][r["game"]]
                c[0] += _ll(pn, y) - _ll(po, y)
                c[1] += 1
                ma = main_abs[fam]
                ma[0] += (po - y) ** 2
                ma[1] += (pn - y) ** 2
                ma[2] += 1
        out[a] = {
            "rows": len(new), "rows_with_changed_p": changed,
            "games": {f: len(v) for f, v in games.items()},
            "minus_base": {m: {f: boot([(x, int(n)) for x, n in v[f].values()])
                               for f in FAMILIES if f in v}
                           for m, v in per_game.items()},
            "main_lines_fair_045_055": {
                f: {"lines": int(main_abs[f][2]),
                    "brier_base": main_abs[f][0] / main_abs[f][2],
                    "brier_new": main_abs[f][1] / main_abs[f][2],
                    "logloss_diff": boot([(x, int(n)) for x, n in v.values()])}
                for f, v in main.items() if main_abs[f][2]},
        }
        print(f"superbet arm {a} done", file=sys.stderr, flush=True)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--mode", choices=("tune-shots", "fit-empty-net", "history",
                                       "superbet", "coverage"), required=True)
    ap.add_argument("--arms", default=",".join(ARMS))
    ap.add_argument("--cache", default=None, help="measure_score_history pickle")
    ap.add_argument("--box-cache", default=None)
    ap.add_argument("--events-cache", default=None)
    ap.add_argument("--tune-start", default="2024-10-01")
    ap.add_argument("--tune-end", default="2025-06-01")
    ap.add_argument("--start", default="2025-10-01")
    ap.add_argument("--end", default="2026-06-01")
    ap.add_argument("--from", dest="date_from", default="2026-09-29")
    ap.add_argument("--to", dest="date_to", default="2026-10-12")
    ap.add_argument("--max-games", type=int, default=6000)
    ap.add_argument("--sims", type=int, default=1000)
    ap.add_argument("--alpha", default=None,
                    help="shots,conv alphas (default: score_model.SHOTS_ALPHA)")
    ap.add_argument("--empty-net", default=None,
                    help="e1,e2,t (default: score_model.HK_EMPTY_NET)")
    ap.add_argument("--json-out")
    args = ap.parse_args()
    config = SofaConfig.from_env()
    data = load(config.db_path, HK, args.cache, union=True)
    box = load_box(config.db_path, data, args.box_cache)
    data = with_shots(data, box)
    if args.alpha:
        a_s, a_c = (float(x) for x in args.alpha.split(","))
        ALPHA_BY_METRIC[sm.HK_SHOTS], ALPHA_BY_METRIC[sm.HK_CONV] = a_s, a_c
    if args.empty_net:
        e1, e2, t = (float(x) for x in args.empty_net.split(","))
        sm.HK_EMPTY_NET = (e1, e2, t)
    arms = [a for a in args.arms.split(",") if a]
    out: dict[str, Any] = {
        "mode": args.mode, "db_path": config.db_path, "games_in_history": len(data),
        "games_with_shots": sum(1 for r, _ in data if sm.HK_SHOTS in r.values),
        "alpha": {m: ALPHA_BY_METRIC.get(m) for m in sm.SHOT_METRICS},
        "empty_net": list(sm.HK_EMPTY_NET),
        "sim_params_base": dataclasses.asdict(sm.SimParams()),
    }
    if args.mode == "coverage":
        months: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        for r, _ in data:
            c = months[datetime.fromtimestamp(r.ts, UTC).strftime("%Y-%m")]
            c[0] += 1
            c[1] += sm.HK_SHOTS in r.values
        out["months_games_with_shots"] = dict(sorted(months.items()))
    elif args.mode == "tune-shots":
        out["tune"] = tune(data, _ts(args.tune_start), _ts(args.tune_end),
                           (0.02, 0.05, 0.10), (0.01, 0.02, 0.05))
    elif args.mode == "fit-empty-net":
        out["fit"] = fit_empty_net(data, box, _ts(args.tune_start),
                                   _ts(args.tune_end))
    elif args.mode == "history":
        out["window"] = [args.start, args.end]
        out["history"] = history_test(data, _ts(args.start), _ts(args.end),
                                      args.max_games, args.sims, arms)
    else:
        out["superbet"] = superbet_test(config.db_path, config.runs_dir, box,
                                        args.date_from, args.date_to, args.sims,
                                        args.events_cache, arms)
    text = json.dumps(out, indent=1)
    print(text)
    if args.json_out:
        Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json_out).write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
