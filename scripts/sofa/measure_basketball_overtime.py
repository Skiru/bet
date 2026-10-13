#!/usr/bin/env python3
"""Basketball overtime: length by the league's quarter (audit 2026-10-13 A3)
and the regulation tie pull (C8), measured together - and the noise variants
of A8 (`--variant a8_*`). Read-only evidence, never a gate.

Pre-registered in docs/sofa/evidence/basketball_overtime_2026-10-13.md (A3 +
C8) and docs/sofa/evidence/basketball_noise_2026-10-13.md (A8).

Walk forward over the cached history (score_model's own read): the model is
built before --train-start; through [--train-start, --start) each game is
forecast and simulated with the old rule (the tie-pull probability is fitted
there by moments: the history's regulation draw share against the
simulation's, over the simulation's mass within the window); through
[--start, --end) every n-th game is scored under the old and the new rule
with the same seed. The book is updated after each game.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_basketball_overtime.py \\
        --cache data/audit_2026-10-13/bb_history.pkl [--json-out f]
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import math
import random
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO / "src"), str(_REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa.config import SofaConfig  # noqa: E402
from bet.sofa.score_model import (  # noqa: E402
    ScoreModel,
    SimParams,
    _rated_values,
    build_model,
    quarter_minutes_for,
)
from bet.sofa.shadow import SPORTS, GameResult  # noqa: E402
from scripts.sofa.measure_score_history import load  # noqa: E402

BB = SPORTS["basketball"]


def _ts(day: str) -> int:
    return int(datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=UTC).timestamp())


def reg(g: GameResult) -> tuple[int, int]:
    return sum(g.t1_periods), sum(g.t2_periods)


def three_way(sims: list[GameResult]) -> tuple[float, float, float]:
    n = len(sims)
    h = d = 0
    for s in sims:
        a, b = reg(s)
        h += a > b
        d += a == b
    # +0.5 smoothing: a simulated zero is not a certainty
    return ((h + 0.5) / (n + 1.5), (d + 0.5) / (n + 1.5),
            (n - h - d + 0.5) / (n + 1.5))


def boot(groups: list[float], reps: int = 2000) -> list[float]:
    if not groups:
        return [float("nan")] * 3
    rng = random.Random(0)
    m = len(groups)
    stats = sorted(sum(groups[rng.randrange(m)] for _ in range(m)) / m
                   for _ in range(reps))
    return [sum(groups) / m, stats[int(0.025 * reps)], stats[int(0.975 * reps) - 1]]


def variant_params(name: str, base: SimParams, pull: float) -> tuple[SimParams, bool]:
    """(params, A3 quarter length on?) of a variant."""
    if name == "a3c8":
        return dataclasses.replace(base, bb_tie_pull=pull), True
    if name == "a8_no_fresh":
        return dataclasses.replace(base, bb_fresh_mult=(1.0, 1.0)), False
    if name == "a8_level_power":
        return dataclasses.replace(base, bb_sd_level_power=0.5), False
    if name == "a8_one_step":
        return base, False  # its own model: build_model(bb_resid_one_step)
    raise ValueError(name)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--train-start", default="2025-10-01")
    ap.add_argument("--start", default="2026-02-01")
    ap.add_argument("--end", default="2026-06-01")
    ap.add_argument("--max-games", type=int, default=3000)
    ap.add_argument("--max-train-games", type=int, default=2000)
    ap.add_argument("--sims", type=int, default=600)
    ap.add_argument("--cache", default=None)
    ap.add_argument("--variant", default="a3c8",
                    choices=("a3c8", "a8_no_fresh", "a8_level_power",
                             "a8_one_step"))
    ap.add_argument("--freshness", action="store_true",
                    help="old rule with bb_fresh_mult applied (the live rule)")
    ap.add_argument("--json-out")
    args = ap.parse_args()
    data = load(SofaConfig.from_env().db_path, BB, args.cache, union=True)
    t_train = _ts(args.train_start)
    t0, t1 = _ts(args.start), _ts(args.end)
    model = build_model([r for r, _ in data], BB, t_train)
    base = model.params
    train = [(r, g) for r, g in data if t_train <= r.ts < t0]
    window = [(r, g) for r, g in data if t0 <= r.ts < t1]
    tstep = max(1, len(train) // args.max_train_games)
    step = max(1, len(window) // args.max_games)
    d_obs = d_mod = m_w = 0.0
    n_train = 0
    totals: list[int] = []

    def fresh(m: ScoreModel, r: Any) -> float:
        return m.noise_mult(r.home_id, r.away_id, r.ts) if args.freshness else 1.0

    others: list[ScoreModel] = []

    def advance(r: Any) -> None:
        for m in (model, *others):
            m.book.update(_rated_values(r, BB))
            if m.recent is not None:
                for team in (r.home_id, r.away_id):
                    m.recent.setdefault(team, []).append(r.ts)

    for i, (r, g) in enumerate(train):
        if i % tstep == 0 and g is not None and len(g.t1_periods) == 4:
            exp = model.expected(r.competition_id, r.home_id, r.away_id, r.ts)
            if exp is not None:
                sims = model.simulate(exp[0], exp[1], seed=r.event_id, n=args.sims,
                                      noise_mult=fresh(model, r))
                a, b = reg(g)
                d_obs += a == b
                d_mod += sum(1 for s in sims if reg(s)[0] == reg(s)[1]) / len(sims)
                m_w += sum(1 for s in sims
                           if 1 <= abs(reg(s)[0] - reg(s)[1]) <= base.bb_tie_window
                           ) / len(sims)
                n_train += 1
                totals.append(g.t1_full + g.t2_full)
        advance(r)
    pull = 0.0
    if n_train and m_w > 0:
        pull = min(max((d_obs - d_mod) / m_w, 0.0), 1.0)
    totals.sort()
    t_line = float(totals[len(totals) // 2]) + 0.5 if totals else 160.5
    new_params, a3 = variant_params(args.variant, base, pull)
    new_model = dataclasses.replace(model, params=new_params)
    if args.variant == "a8_one_step":
        # its own book, replayed to the same point, noise fitted one step ahead
        new_model = build_model([r for r, _ in data], BB, t_train,
                                SimParams(bb_resid_one_step=True))
        for r, _ in train:
            new_model.book.update(_rated_values(r, BB))
            if new_model.recent is not None:
                for team in (r.home_id, r.away_id):
                    new_model.recent.setdefault(team, []).append(r.ts)
    if new_model.book is not model.book:
        others.append(new_model)
    ll_diff: list[float] = []
    tot_diff: list[float] = []
    win_diff: list[float] = []
    draws = {"actual": 0.0, "old": 0.0, "new": 0.0}
    calib: dict[str, list[tuple[float, int]]] = {"old": [], "new": []}
    n_games = 0
    for i, (r, g) in enumerate(window):
        if i % step == 0 and g is not None and len(g.t1_periods) == 4:
            exp = model.expected(r.competition_id, r.home_id, r.away_id, r.ts)
            if exp is not None:
                nm = fresh(model, r)
                so = model.simulate(exp[0], exp[1], seed=r.event_id, n=args.sims,
                                    noise_mult=nm)
                exp_n = (exp if new_model.book is model.book else
                         new_model.expected(r.competition_id, r.home_id, r.away_id,
                                            r.ts))
                if exp_n is None:
                    advance(r)
                    continue
                sn = new_model.simulate(
                    exp_n[0], exp_n[1], seed=r.event_id, n=args.sims,
                    noise_mult=fresh(new_model, r),
                    quarter_minutes=(quarter_minutes_for(r.competition_id)
                                     if a3 else None))
                a, b = reg(g)
                k = 0 if a > b else (1 if a == b else 2)
                po, pn = three_way(so), three_way(sn)
                ll_diff.append(-math.log(pn[k]) + math.log(po[k]))
                y_tot = 1.0 if g.t1_full + g.t2_full > t_line else 0.0
                qo = sum(1 for s in so if s.t1_full + s.t2_full > t_line) / len(so)
                qn = sum(1 for s in sn if s.t1_full + s.t2_full > t_line) / len(sn)
                tot_diff.append((qn - y_tot) ** 2 - (qo - y_tot) ** 2)
                if g.winner is not None:
                    yw = 1.0 if g.winner == "T1" else 0.0
                    wo = sum(1 for s in so if s.winner == "T1") / len(so)
                    wn = sum(1 for s in sn if s.winner == "T1") / len(sn)
                    win_diff.append((wn - yw) ** 2 - (wo - yw) ** 2)
                    for key, p_ in (("old", wo), ("new", wn)):
                        for side_p, side_y in ((p_, yw), (1 - p_, 1 - yw)):
                            if side_p >= 0.70:
                                calib[key].append((side_p, int(side_y)))
                draws["actual"] += k == 1
                draws["old"] += po[1]
                draws["new"] += pn[1]
                n_games += 1
        advance(r)
    out: dict[str, Any] = {
        "variant": args.variant, "train": [args.train_start, args.start],
        "window": [args.start, args.end], "train_games": n_train,
        "games": n_games, "tie_pull_fitted": round(pull, 4),
        "train_draw_share": {"history": d_obs / max(n_train, 1),
                             "simulated": d_mod / max(n_train, 1),
                             "within_window_mass": m_w / max(n_train, 1)},
        "window_draw_share": {k: v / max(n_games, 1) for k, v in draws.items()},
        "logloss_1x2_reg_new_minus_old": boot(ll_diff),
        "brier_total_incl_ot_new_minus_old": boot(tot_diff), "total_line": t_line,
        "brier_winner_new_minus_old": boot(win_diff),
        "winner_calibration_p_ge_070": {
            k: {"n": len(v), "p": sum(p for p, _ in v) / len(v),
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
