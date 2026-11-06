#!/usr/bin/env python3
"""Measure the minute-by-minute football simulator (bet.sofa.football_sim) -
read-only. Report: docs/sofa/evidence/football_sim_2026-11-06.md (rules
pre-registered in its section 0 before the hold-out was scored).

Stages (each writes only under ``--out-dir``; never the network, never a
database write):

  * ``inventory``: what timed data the cache holds per football match, by
    month and by feed (timed goals, full feed with red cards, announced added
    time, half totals per metric); caches the timed history as a pickle.
  * ``forecast``: one walk-forward pass of the football rating
    (bet.sofa.football_rating, read-only, the flags SHEET runs with on the
    measured day) - every wanted match's centres from the book BEFORE that
    match is learnt; cached as a pickle.
  * ``fit``: the state multipliers, added-time distribution, red-card
    process and per-half count model on the history before ``FIT_TO``.
  * ``history``: simulator vs the current estimator's history replay
    (``sofa_settled_row``, run_date ``cache-calibration``) on matches after
    the fit cut and before the first Superbet line.
  * ``superbet``: settled Superbet lines (live ``sofa_settled_row`` rows) and
    the unmapped prices of the path markets SHEET does not read
    (``runs/sofa/<d>/unmapped_prices``), graded on the cached result -
    simulator vs current p_central vs the de-vigged price; days split
    development / hold-out, the hold-out scored only with ``--holdout``.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_football_sim.py \\
        --out-dir data/football_sim_2026-11-06 --stage inventory
"""

from __future__ import annotations

import argparse
import json
import math
import multiprocessing as mp
import pickle
import re
import sqlite3
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

for _p in ("src", "."):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import cup_strength, dossier, epochs  # noqa: E402
from bet.sofa.football_1x2_dnb import dnb_side  # noqa: E402
from bet.sofa.football_rating import (  # noqa: E402
    RatingBook,
    assign_league_units,
    enable_form_table,
    mark_second_squads,
    parse_event,
    without_awarded,
)
from bet.sofa.football_result import count_pmf, result_probs  # noqa: E402
from bet.sofa.football_result import load_config as load_result_config  # noqa: E402
from bet.sofa.football_sim import (  # noqa: E402
    COUNT_METRICS,
    Centres,
    MarketSim,
    MinuteMatch,
    SimParams,
    SimResult,
    added_pmf,
    centres_from,
    fit_count_models,
    fit_goal_model,
    fit_red_model,
    goal_cells,
    load_minute_history,
    path_actual,
    path_outcomes,
    read_minute_match,
    red_cells,
    simulate,
    walk_forward_centres,
)
from bet.sofa.market_mapper import fold  # noqa: E402

_REPO = Path(__file__).resolve().parents[2]
DEFAULT_DB = _REPO / "data" / "sofa.db"
DEFAULT_RUNS = _REPO / "runs" / "sofa"
DEFAULT_FOOTBALL_HISTORY = _REPO / "data" / "cache" / "football_history.pkl"
HISTORY_SINCE = "2024-01-01"
# The rating's flags are SHEET's on this day (epochs, read-only).
BOOK_DAY = "2026-11-06"
FORECAST_SINCE = "2025-01-01"
LIVE_FROM = "2026-09-18"
# Fit window (the multipliers), its validation slice (goal frailty and the
# mean rescale only), and the history evaluation after the cut.
FIT_FROM = "2025-01-01"
VAL_FROM = "2026-03-01"
FIT_TO = "2026-06-01"
HIST_EVAL_TO = "2026-09-18"
VAL_MATCHES = 3000
GOAL_FRAILTY_GRID = (0.0, 0.03, 0.06, 0.10)
MATCH_MEAN_GRID = (False, True)


def ts_of(day: str) -> int:
    return int(datetime.fromisoformat(day).replace(tzinfo=UTC).timestamp())


def month_of(ts: int) -> str:
    return datetime.fromtimestamp(ts, UTC).strftime("%Y-%m")


def log(msg: str) -> None:
    print(f"[{datetime.now(UTC).strftime('%H:%M:%S')}Z] {msg}", flush=True)


# --------------------------------------------------------------------------
# Loading (cached)
# --------------------------------------------------------------------------


def load_football_history(path: Path) -> list[Any]:
    """The parsed football_rating history SHEET keeps in data/cache (read
    only; its fingerprint is not checked - a measurement of what it holds)."""
    _, history = pickle.loads(path.read_bytes())
    return list(history)


def load_minutes(args: argparse.Namespace, history: list[Any]) -> list[MinuteMatch]:
    cache = args.out_dir / "minute_history.pkl"
    if cache.exists():
        data: list[MinuteMatch] = pickle.loads(cache.read_bytes())
        return data
    t0 = time.time()
    out = load_minute_history(args.db, history, ts_of(HISTORY_SINCE))
    cache.write_bytes(pickle.dumps(out, protocol=pickle.HIGHEST_PROTOCOL))
    log(f"timed history: {len(out)} matches in {time.time() - t0:.0f}s")
    return out


# --------------------------------------------------------------------------
# Inventory
# --------------------------------------------------------------------------


def run_inventory(args: argparse.Namespace) -> dict[str, Any]:
    history = load_football_history(args.football_history)
    since = ts_of(HISTORY_SINCE)
    finished = [r for r in history if r.ts >= since and not r.awarded]
    minutes = load_minutes(args, history)
    by_month: dict[str, Counter[str]] = defaultdict(Counter)
    for r in finished:
        c = by_month[month_of(r.ts)]
        c["matches"] += 1
        if "goals_1h_for" in r.values:
            c["ht_score"] += 1
        if "corners_for" in r.values:
            c["stats"] += 1
    comp_all: Counter[int] = Counter(r.competition_id for r in finished)
    comp_timed: Counter[int] = Counter()
    for m in minutes:
        c = by_month[month_of(m.ts)]
        c["incident_list"] += 1
        if m.goals is not None:
            c["timed_goals"] += 1
            comp_timed[m.competition_id] += 1
        if m.reds is not None:
            c["full_feed"] += 1
        if m.added[0] is not None:
            c["added_1h"] += 1
        if m.added[1] is not None:
            c["added_2h"] += 1
        if m.goals is not None and m.reds is not None and m.added[1] is not None:
            c["timed_full_added"] += 1
        for metric in COUNT_METRICS:
            if metric in m.halves:
                c[f"halves_{metric}"] += 1
        if m.goals is not None and all(k in m.halves for k in COUNT_METRICS):
            c["timed_all_halves"] += 1
    totals: Counter[str] = Counter()
    for c in by_month.values():
        totals.update(c)
    # leagues: how much of each competition's matches are timed
    comps = []
    for comp, n in comp_all.most_common():
        comps.append(
            {"competition_id": comp, "matches": n, "timed": comp_timed.get(comp, 0)}
        )
    timed_comps = sum(1 for c in comps if c["timed"] >= 30)
    out = {
        "since": HISTORY_SINCE,
        "totals": dict(totals),
        "by_month": {k: dict(v) for k, v in sorted(by_month.items())},
        "competitions": len(comp_all),
        "competitions_with_30_timed": timed_comps,
        "top_competitions": comps[:60],
    }
    # added-time distribution (what the simulator draws)
    for half in (0, 1):
        dist = Counter(m.added[half] for m in minutes if m.added[half] is not None)
        out[f"added_dist_{half + 1}h"] = dict(sorted(dist.items()))
    return out


# --------------------------------------------------------------------------
# Forecast: one walk-forward pass of the rating
# --------------------------------------------------------------------------


def fresh_book(day: str = BOOK_DAY) -> RatingBook:
    """An empty RatingBook with the flags SHEET replays with on ``day``
    (run_sheet.py: link_shared, unit strength, current league domain, form
    table, cup strength)."""
    book = RatingBook(shared_league_link=epochs.link_shared_league(day))
    if epochs.football_form_table(day):
        enable_form_table(book)
    book.unit_strength_from_parent = epochs.unit_strength_from_parent(day)
    book.current_league_domain = epochs.rating_domain_current_league(day)
    if epochs.football_cup_strength(day):
        cup_strength.apply(book, cup_strength.load())
    return book


def load_forecasts(
    args: argparse.Namespace, history: list[Any], minutes: list[MinuteMatch]
) -> dict[int, dict[str, tuple[float, float]]]:
    cache = args.out_dir / "forecasts.pkl"
    if cache.exists():
        data: dict[int, dict[str, tuple[float, float]]] = pickle.loads(
            cache.read_bytes()
        )
        return data
    since, live = ts_of(FORECAST_SINCE), ts_of(LIVE_FROM)
    wanted = {m.event_id for m in minutes if m.ts >= since}
    wanted |= {int(r.event_id) for r in history if r.ts >= live}
    hist = without_awarded(history) if epochs.awarded_excluded(BOOK_DAY) else history
    t0 = time.time()
    out = walk_forward_centres(hist, wanted, fresh_book())
    cache.write_bytes(pickle.dumps(out, protocol=pickle.HIGHEST_PROTOCOL))
    log(f"forecasts: {len(out)} of {len(wanted)} wanted in {time.time() - t0:.0f}s")
    return out


# Dev finding (2026-11-06, before any score was read): the rating history is
# built from the teams' cached `last` pages, which lag - 2,001 of the 4,257
# Superbet events of 10-25..11-05 (509 of 11,379 before) were not in it, so
# they had neither a forecast nor a result. Each such fixture is parsed from
# its cached /event payload (sofa_event_detail, what SETTLE reads) with the
# rating's own parser and merged in time order; the merged history is frozen
# in the out dir (the shared pickle is rewritten by SHEET during the day),
# and the Superbet stage reads its own walk-forward on it.
def live_history(
    args: argparse.Namespace, history: list[Any]
) -> tuple[list[Any], list[MinuteMatch]]:
    cache = args.out_dir / "history_live.pkl"
    if cache.exists():
        hist, cached_min = pickle.loads(cache.read_bytes())
        return list(hist), list(cached_min)
    have = {int(r.event_id) for r in history}
    want: set[int] = set()
    for day in day_list(SB_FROM, SB_TO):
        want |= set(load_day(args.runs_dir, day).fixtures)
    missing = sorted(want - have)
    added: list[Any] = []
    added_min: list[MinuteMatch] = []
    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    conn.execute("PRAGMA busy_timeout = 60000")
    try:
        for i in range(0, len(missing), 500):
            chunk = missing[i : i + 500]
            q = ",".join("?" * len(chunk))
            details = dict(
                conn.execute(
                    "SELECT sofascore_event_id, detail_json FROM sofa_event_detail "
                    f"WHERE sofascore_event_id IN ({q})",
                    chunk,
                ).fetchall()
            )
            stats = {
                int(e): (s, inc)
                for e, s, inc in conn.execute(
                    "SELECT sofascore_event_id, statistics_json, incidents_json "
                    f"FROM sofa_event_stats WHERE sofascore_event_id IN ({q})",
                    chunk,
                )
            }
            for eid in chunk:
                d = details.get(eid)
                if not d:
                    continue
                event = (json.loads(d) or {}).get("event")
                if not isinstance(event, dict):
                    continue
                s_json, i_json = stats.get(eid, (None, None))
                s = json.loads(s_json) if s_json else None
                inc = json.loads(i_json) if i_json else None
                r = parse_event(event, s, inc)
                if r is None:
                    continue
                added.append(r)
                if isinstance(inc, dict) and inc and not getattr(r, "awarded", False):
                    m = read_minute_match(r, s if isinstance(s, dict) else None, inc)
                    if m is not None:
                        added_min.append(m)
    finally:
        conn.close()
    merged = assign_league_units(
        mark_second_squads(sorted([*history, *added], key=lambda r: (r.ts, r.event_id)))
    )
    log(
        f"live history: {len(missing)} fixtures missing from the rating history, "
        f"{len(added)} parsed from /event, {len(added_min)} timed"
    )
    cache.write_bytes(
        pickle.dumps((merged, added_min), protocol=pickle.HIGHEST_PROTOCOL)
    )
    return merged, added_min


def load_live_forecasts(
    args: argparse.Namespace, history: list[Any]
) -> dict[int, dict[str, tuple[float, float]]]:
    cache = args.out_dir / "forecasts_live.pkl"
    if cache.exists():
        data: dict[int, dict[str, tuple[float, float]]] = pickle.loads(
            cache.read_bytes()
        )
        return data
    live = ts_of(LIVE_FROM)
    wanted = {int(r.event_id) for r in history if r.ts >= live}
    hist = without_awarded(history) if epochs.awarded_excluded(BOOK_DAY) else history
    t0 = time.time()
    out = walk_forward_centres(hist, wanted, fresh_book())
    cache.write_bytes(pickle.dumps(out, protocol=pickle.HIGHEST_PROTOCOL))
    log(f"live forecasts: {len(out)} of {len(wanted)} in {time.time() - t0:.0f}s")
    return out


# --------------------------------------------------------------------------
# Fit
# --------------------------------------------------------------------------


def window(
    minutes: list[MinuteMatch],
    fc: dict[int, dict[str, tuple[float, float]]],
    lo: str,
    hi: str,
) -> list[tuple[MinuteMatch, Centres]]:
    a, b = ts_of(lo), ts_of(hi)
    out = []
    for m in minutes:
        if not a <= m.ts < b:
            continue
        c = centres_from(fc.get(m.event_id, {}))
        if c is not None:
            out.append((m, c))
    return out


def fit_on(
    rows: list[tuple[MinuteMatch, Centres]],
    fitted_to: str,
    goal_frailty: float = 0.0,
    match_mean: bool = False,
) -> tuple[SimParams, dict[str, Any]]:
    cards_all = sorted(c.cards[s] for _, c in rows if c.cards for s in (0, 1))
    default_cards = cards_all[len(cards_all) // 2] if cards_all else 2.2
    gcells = goal_cells((m, c.goals) for m, c in rows)
    prof, state, gse = fit_goal_model(gcells)
    rcells = red_cells((m, c.cards or (default_cards, default_cards)) for m, c in rows)
    rprof, rstate, rse = fit_red_model(rcells)
    coef, cse, alpha, cov, n_used = fit_count_models(rows)
    pmf = added_pmf(m for m, _ in rows)
    params = SimParams(
        goal_profile=prof,
        goal_state=state,
        red_profile=rprof,
        red_state=rstate,
        added_pmf=pmf,
        count_coef=coef,
        count_alpha=alpha,
        frailty_cov=cov,
        goal_frailty=goal_frailty,
        match_mean=match_mean,
        default_cards=default_cards,
        fitted_to=fitted_to,
    )
    timed = [m for m, _ in rows if m.goals is not None and m.reds is not None]
    info = {
        "matches": len(rows),
        "goal_state_matches": len(timed),
        "goals": sum(len(m.goals or ()) for m in timed),
        "reds": sum(len(m.reds or ()) for m in timed),
        "goal_se": gse,
        "red_se": rse,
        "count_se": cse,
        "count_rows": n_used,
    }
    return params, info


def score_loglik(
    params: SimParams, rows: list[tuple[MinuteMatch, Centres]], sims: int
) -> dict[str, float]:
    """Mean log-likelihood of the exact 90-minute and half-time scores and
    the mean goals per side (calibration of the rescale)."""
    ft = ht = 0.0
    mean_sim = mean_obs = 0.0
    n = 0
    for m, c in rows:
        if m.ht is None:
            continue
        res = simulate(params, c, n=sims, seed=m.event_id % (2**31))
        g = res.goals
        fh, fa = g[0, 0] + g[1, 0], g[0, 1] + g[1, 1]
        p_ft = float(np.mean((fh == m.ft[0]) & (fa == m.ft[1])))
        p_ht = float(np.mean((g[0, 0] == m.ht[0]) & (g[0, 1] == m.ht[1])))
        ft += math.log(max(p_ft, 0.5 / sims))
        ht += math.log(max(p_ht, 0.5 / sims))
        mean_sim += float(fh.mean() + fa.mean())
        mean_obs += m.ft[0] + m.ft[1]
        n += 1
    return {
        "n": n,
        "ft_loglik": ft / n,
        "ht_loglik": ht / n,
        "goals_sim": mean_sim / n,
        "goals_obs": mean_obs / n,
    }


def run_fit(args: argparse.Namespace) -> dict[str, Any]:
    history = load_football_history(args.football_history)
    minutes = load_minutes(args, history)
    fc = load_forecasts(args, history, minutes)
    # hyper-parameters: fit before VAL_FROM, score the validation slice
    early = window(minutes, fc, FIT_FROM, VAL_FROM)
    val = window(minutes, fc, VAL_FROM, FIT_TO)
    rng = np.random.default_rng(11)
    val_idx = sorted(
        rng.choice(len(val), size=min(VAL_MATCHES, len(val)), replace=False)
    )
    val_rows = [val[i] for i in val_idx]
    base, _ = fit_on(early, VAL_FROM)
    grid = []
    for gf in GOAL_FRAILTY_GRID:
        for mm in MATCH_MEAN_GRID:
            p = SimParams.from_json(
                {**base.to_json(), "goal_frailty": gf, "match_mean": mm}
            )
            sc = score_loglik(p, val_rows, args.val_sims)
            grid.append({"goal_frailty": gf, "match_mean": mm, **sc})
            log(f"validation gf={gf} match_mean={mm}: {sc}")
    best = max(grid, key=lambda g: g["ft_loglik"] + g["ht_loglik"])
    rows = window(minutes, fc, FIT_FROM, FIT_TO)
    params, info = fit_on(
        rows, FIT_TO, float(best["goal_frailty"]), bool(best["match_mean"])
    )
    (args.out_dir / "params.json").write_text(
        json.dumps(params.to_json(), indent=1), encoding="utf-8"
    )
    return {
        "validation_grid": grid,
        "chosen": {k: best[k] for k in ("goal_frailty", "match_mean")},
        "fit": info,
        "params": params.to_json(),
    }


# --------------------------------------------------------------------------
# Scoring (the tennis point model's rules, scripts/sofa/measure_tennis_point_model.py)
# --------------------------------------------------------------------------

BOOT = 2000
MIN_CONF = 0.70
MID_CONF = (0.60, 0.70)
MIN_X = 0.90
TAX = 0.12
# Non-inferiority to the de-vigged price: the upper 95% bound of
# Brier(sim) - Brier(price) at most 1% of the family's price Brier (0.002 at
# a Brier of 0.2, the tennis margin of 2026-11-05).
NONINF_REL = 0.01
MIN_LEGS = 30
PAIR_OVERROUND = (1.0, 1.30)
MULTI_OVERROUND = (1.0, 1.60)


def brier(p: float, y: int) -> float:
    return (p - y) ** 2


def logloss(p: float, y: int) -> float:
    p = min(max(p, 1e-4), 1.0 - 1e-4)
    return -math.log(p if y else 1.0 - p)


def boot_mean(
    groups: list[int], values: list[float], seed: int = 1
) -> tuple[float, float, float]:
    """Mean of values with a 95% interval resampling whole matches."""
    by: dict[int, list[float]] = defaultdict(list)
    for g, v in zip(groups, values, strict=True):
        by[g].append(v)
    keys = list(by)
    if not keys:
        return float("nan"), float("nan"), float("nan")
    sums = np.array([sum(by[k]) for k in keys])
    ns = np.array([len(by[k]) for k in keys], dtype=np.float64)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(keys), (BOOT, len(keys)))
    means = sums[idx].sum(axis=1) / ns[idx].sum(axis=1)
    return (
        float(sums.sum() / ns.sum()),
        float(np.percentile(means, 2.5)),
        float(np.percentile(means, 97.5)),
    )


@dataclass(frozen=True)
class Leg:
    """One selection: its outcome, the simulator's p, the current p (SHEET
    p_central, or the history's current estimator), the de-vigged price p
    and the price. ``scored``: the row Brier / log-loss read (one per pair
    - the OVER - and every outcome of a multi-way market)."""

    eid: int
    day: str
    family: str
    y: int
    p_sim: float
    p_cur: float | None = None
    p_price: float | None = None
    odds: float | None = None
    scored: bool = True
    detail: str = ""


def family_scores(legs: list[Leg], with_price: bool) -> dict[str, Any]:
    rows = [x for x in legs if x.scored]
    g = [x.eid for x in rows]
    out: dict[str, Any] = {
        "n_rows": len(rows),
        "n_matches": len(set(g)),
        "n_legs": len(legs),
    }
    if not rows:
        return out
    for name, f in (("brier", brier), ("logloss", logloss)):
        sim = [f(x.p_sim, x.y) for x in rows]
        sc: dict[str, Any] = {"sim": sum(sim) / len(sim)}
        if all(x.p_cur is not None for x in rows):
            cur = [f(x.p_cur or 0.0, x.y) for x in rows]
            sc["current"] = sum(cur) / len(cur)
            sc["sim_minus_current"] = boot_mean(
                g, [a - b for a, b in zip(sim, cur, strict=True)]
            )
        if with_price and all(x.p_price is not None for x in rows):
            prc = [f(x.p_price or 0.0, x.y) for x in rows]
            sc["price"] = sum(prc) / len(prc)
            sc["sim_minus_price"] = boot_mean(
                g, [a - b for a, b in zip(sim, prc, strict=True)]
            )
            if "current" in sc:
                cur = [f(x.p_cur or 0.0, x.y) for x in rows]
                sc["current_minus_price"] = boot_mean(
                    g, [a - b for a, b in zip(cur, prc, strict=True)]
                )
        out[name] = sc
    for who in ("sim", "cur", "price"):
        out[f"high_{who}"] = band_stats(legs, who, MIN_CONF, 1.01)
        out[f"mid_{who}"] = band_stats(legs, who, *MID_CONF)
    out["roi_sim"] = roi_stats(legs)
    out["calibration_sim"] = calibration(legs, "sim")
    return out


def _p_of(x: Leg, who: str) -> float | None:
    return x.p_sim if who == "sim" else x.p_cur if who == "cur" else x.p_price


def band_stats(legs: list[Leg], who: str, lo: float, hi: float) -> dict[str, Any]:
    cell = [(x, p) for x in legs if (p := _p_of(x, who)) is not None and lo <= p < hi]
    if not cell:
        return {"n": 0}
    g = [x.eid for x, _ in cell]
    return {
        "n": len(cell),
        "matches": len(set(g)),
        "claimed": sum(p for _, p in cell) / len(cell),
        "realised": boot_mean(g, [float(x.y) for x, _ in cell]),
        "gap": boot_mean(g, [x.y - p for x, p in cell]),
    }


def roi_stats(legs: list[Leg]) -> dict[str, Any]:
    cell = [
        x for x in legs if x.odds and x.p_sim >= MIN_CONF and x.p_sim * x.odds >= MIN_X
    ]
    if not cell:
        return {"n": 0}
    g = [x.eid for x in cell]
    return {
        "n": len(cell),
        "matches": len(set(g)),
        "claimed": sum(x.p_sim for x in cell) / len(cell),
        "realised": boot_mean(g, [float(x.y) for x in cell]),
        "price_nv": (
            sum(x.p_price for x in cell if x.p_price is not None)
            / max(1, sum(1 for x in cell if x.p_price is not None))
        ),
        "roi": boot_mean(g, [(x.odds or 0.0) * x.y - 1.0 for x in cell]),
        "roi_after_tax": boot_mean(
            g, [(1 - TAX) * (x.odds or 0.0) * x.y - 1.0 for x in cell]
        ),
    }


def calibration(legs: list[Leg], who: str) -> list[dict[str, Any]]:
    rows = []
    for i in range(10):
        lo, hi = i / 10, (i + 1) / 10 + (1e-9 if i == 9 else 0.0)
        st = band_stats(legs, who, lo, hi)
        if st.get("n"):
            rows.append({"bucket": f"{i / 10:.1f}-{(i + 1) / 10:.1f}", **st})
    return rows


def verdict(sc: dict[str, Any]) -> dict[str, str]:
    """The pre-registered words (report section 0)."""
    out: dict[str, str] = {}
    b = sc.get("brier", {})
    if "sim_minus_price" in b:
        margin = NONINF_REL * b["price"]
        out["as_good_as_price"] = "tak" if b["sim_minus_price"][2] <= margin else "nie"
        out["better_than_price"] = "tak" if b["sim_minus_price"][2] < 0 else "nie"
    if "sim_minus_current" in b:
        lo, hi = b["sim_minus_current"][1:]
        out["vs_current"] = "lepszy" if hi < 0 else "gorszy" if lo > 0 else "remis"
    h = sc.get("high_sim", {})
    if h.get("n", 0) < MIN_LEGS:
        out["no_overpromise_070"] = "za mało nóg"
    else:
        out["no_overpromise_070"] = "tak" if h["gap"][2] >= 0 else "nie"
    if "as_good_as_price" in out:
        out["verdict"] = (
            "co najmniej tak dobry jak Superbet"
            if out["as_good_as_price"] == "tak" and out["no_overpromise_070"] != "nie"
            else "nie"
        )
    return out


def report(
    legs: list[Leg], families: tuple[str, ...], with_price: bool
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for fam in (*families, "all"):
        sel = [x for x in legs if fam == "all" or x.family == fam]
        if not sel:
            continue
        sc = family_scores(sel, with_price)
        sc["verdict"] = verdict(sc)
        sc["days"] = [min(x.day for x in sel), max(x.day for x in sel)]
        out[fam] = sc
    return out


# --------------------------------------------------------------------------
# The "current" constructions the simulator is compared with on history
# --------------------------------------------------------------------------


def nb_halves_result(
    c: Centres,
    half_goals: tuple[tuple[float, float], tuple[float, float]],
    r: float,
    n: int,
    seed: int,
) -> SimResult:
    """Independent NB goals per side and half at the rating's goals_1h /
    goals_2h centres (r = SHEET's result dispersion), goals spread evenly
    over their half - what today's SHEET pieces imply for a path market."""
    rng = np.random.default_rng(seed)
    goals = np.zeros((2, 2, n), dtype=np.int64)
    for h in (0, 1):
        for s in (0, 1):
            mu = max(half_goals[h][s], 1e-6)
            lam = rng.gamma(r, mu / r, n)
            goals[h, s] = rng.poisson(lam)
    first = np.full(n, -1, dtype=np.int64)
    last = np.full(n, -1, dtype=np.int64)
    first_min = np.full(n, np.nan)
    for h in (0, 1):
        tot = goals[h, 0] + goals[h, 1]
        has = tot > 0
        # the first goal of the half: the earliest of `tot` uniform minutes,
        # its side home with share goals_home / tot
        u = rng.random(n)
        t = 45.0 * (1.0 - u ** (1.0 / np.maximum(tot, 1)))
        side = (rng.random(n) >= goals[h, 0] / np.maximum(tot, 1)).astype(np.int64)
        fresh = has & (first < 0)
        first = np.where(fresh, side, first)
        first_min = np.where(fresh, h * 45 + np.minimum(t, 44.999), first_min)
        side_last = (rng.random(n) >= goals[h, 0] / np.maximum(tot, 1)).astype(np.int64)
        last = np.where(has, side_last, last)
    del c
    return SimResult(
        n=n,
        goals=goals,
        reds=np.zeros((2, 2, n), dtype=np.int64),
        first_goal=first,
        first_goal_minute=first_min,
        last_goal=last,
    )


def nb_result_probs(mu: tuple[float, float], r: float) -> dict[str, float]:
    """SHEET's 1X2 / DC price: independent NB goals on the pure rating
    centres (bet.sofa.football_result.result_probs)."""
    return result_probs(mu[0], mu[1], r)


def nb_total_over(mu: tuple[float, float], r: float, line: float) -> float:
    ph = count_pmf(np.array([mu[0]]), r)[0]
    pa = count_pmf(np.array([mu[1]]), r)[0]
    tot = np.convolve(ph, pa)
    k = int(math.floor(line)) + 1
    return float(tot[k:].sum())


# --------------------------------------------------------------------------
# Worker: one match's simulator (and baseline) probabilities
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Ask:
    """What one match needs read off its paths."""

    eid: int
    centres: Centres
    # (key, market, subject, line, direction, side)
    selections: tuple[tuple[str, str, str, float, str, int | None], ...] = ()
    # (key, kind, param)
    paths: tuple[tuple[str, str, Any], ...] = ()
    # (key, selection key a, selection key b) - both must be in selections
    joints: tuple[tuple[str, str, str], ...] = ()
    baseline_halves: tuple[tuple[float, float], tuple[float, float]] | None = None


_PARAMS: SimParams | None = None
_SIMS = 4000
_R = 7.586


def _init_worker(params_json: dict[str, Any], sims: int, r: float) -> None:
    global _PARAMS, _SIMS, _R
    _PARAMS = SimParams.from_json(params_json)
    _SIMS = sims
    _R = r


def answer(ask: Ask) -> tuple[int, dict[str, Any]]:
    assert _PARAMS is not None
    seed = ask.eid % (2**31)
    res = simulate(_PARAMS, ask.centres, n=_SIMS, seed=seed)
    ms = MarketSim(res)
    out: dict[str, Any] = {}
    events: dict[str, Any] = {}
    for key, market, subject, line, direction, side in ask.selections:
        ev = ms.selection(market, subject, line, direction, side)
        if ev is None:
            continue
        events[key] = ev
        out[key] = ms.conditional_p(market, ev)
    for key, a, b in ask.joints:
        if a in events and b in events:
            out[key] = float(np.mean(events[a] & events[b]))
    for key, kind, param in ask.paths:
        out[key] = {
            k: float(v.mean()) for k, v in path_outcomes(ms, kind, param).items()
        }
    if ask.baseline_halves is not None:
        base = MarketSim(
            nb_halves_result(ask.centres, ask.baseline_halves, _R, _SIMS, seed + 7)
        )
        for key, kind, param in ask.paths:
            out["base:" + key] = {
                k: float(v.mean()) for k, v in path_outcomes(base, kind, param).items()
            }
    return ask.eid, out


def run_asks(
    asks: list[Ask], params: SimParams, sims: int, r: float, workers: int
) -> dict[int, dict[str, Any]]:
    t0 = time.time()
    out: dict[int, dict[str, Any]] = {}
    if workers <= 1:
        _init_worker(params.to_json(), sims, r)
        for i, a in enumerate(asks):
            eid, got = answer(a)
            out[eid] = got
            if i % 500 == 0:
                log(f"  simulated {i}/{len(asks)}")
    else:
        with mp.get_context("fork").Pool(
            workers, initializer=_init_worker, initargs=(params.to_json(), sims, r)
        ) as pool:
            for i, (eid, got) in enumerate(
                pool.imap_unordered(answer, asks, chunksize=8)
            ):
                out[eid] = got
                if i % 1000 == 0:
                    log(f"  simulated {i}/{len(asks)}")
    log(
        f"simulated {len(asks)} matches in {time.time() - t0:.0f}s "
        f"({(time.time() - t0) / max(1, len(asks)) * workers:.3f}s a match a worker)"
    )
    return out


def load_params(args: argparse.Namespace) -> SimParams:
    return SimParams.from_json(json.loads((args.out_dir / "params.json").read_text()))


def minute_match_of(r: Any, timed: dict[int, MinuteMatch]) -> MinuteMatch | None:
    """The timed path when cached, else the listing's scores only; None for
    a result without a 90-minute score."""
    m = timed.get(int(r.event_id))
    if m is not None:
        return m
    g = r.values.get("goals_for")
    if g is None:
        return None
    first = r.values.get("goals_1h_for")
    return MinuteMatch(
        event_id=int(r.event_id),
        ts=int(r.ts),
        competition_id=int(r.competition_id),
        home_id=int(r.home_id),
        away_id=int(r.away_id),
        women=bool(r.women),
        ft=(int(g[0]), int(g[1])),
        ht=None if first is None else (int(first[0]), int(first[1])),
        goals=None,
        reds=None,
        added=(None, None),
        halves={},
    )


# --------------------------------------------------------------------------
# History: simulator vs the current estimator, after the fit cut
# --------------------------------------------------------------------------

HIST_MATCHES = 6000
REPLAY_MARKETS = (
    "goals_total",
    "goals_for",
    "corners_total",
    "corners_for",
    "cards_points_total",
    "fouls_total",
    "shots_total",
    "shots_on_target_total",
)
HIST_FAMILY = {
    "goals_total": "c2_goals_total",
    "goals_for": "c3_goals_for",
    "corners_total": "c5_corners",
    "corners_for": "c5_corners",
    "cards_points_total": "c6_cards",
    "fouls_total": "c7_fouls",
    "shots_total": "c8_shots",
    "shots_on_target_total": "c8_shots",
}
PATH_FAMILY = {
    "htft": "a1_htft",
    "half_result": "a2_half_result",
    "higher_half": "a3_higher_half",
    "team_both_halves": "a4_goal_both_halves",
    "btts_halves": "a4_goal_both_halves",
    "btts_any_half": "a4_goal_both_halves",
    "first_goal_band15": "a5_first_goal",
    "first_goal_1h": "a5_first_goal",
    "last_goal": "a5_first_goal",
    "half_totals": "a6_half_goals",
    "odd_even": "x_odd_even",
    "exact_goals": "x_exact_goals",
    "correct_score": "x_correct_score",
}
HIST_PATHS: tuple[tuple[str, Any], ...] = (
    ("htft", None),
    ("half_result", 1),
    ("half_result", 2),
    ("higher_half", None),
    ("team_both_halves", 0),
    ("team_both_halves", 1),
    ("btts_halves", None),
    ("btts_any_half", None),
    ("first_goal_band15", None),
    ("first_goal_1h", None),
    ("last_goal", None),
    ("half_totals", (0.5, 0.5)),
    ("half_totals", (0.5, 1.5)),
    ("half_totals", (1.5, 1.5)),
    ("odd_even", None),
    ("exact_goals", None),
    ("correct_score", 2),
)


def load_replay_rows(
    db: Path, eids: list[int]
) -> list[tuple[int, str, str, float, float, int]]:
    """(event, market, subject, line, p_central of OVER, OVER won) of the
    history replay's rows of these matches (read-only, by the event index)."""
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    conn.execute("PRAGMA busy_timeout = 60000")
    out = []
    marks_m = ",".join("?" * len(REPLAY_MARKETS))
    try:
        for i in range(0, len(eids), 400):
            chunk = eids[i : i + 400]
            marks_e = ",".join("?" * len(chunk))
            q = (
                "SELECT sofascore_event_id, market, subject, line, p_central, outcome "
                f"FROM sofa_settled_row WHERE sofascore_event_id IN ({marks_e}) "
                # "+run_date": keep the planner off the run_date index (a scan
                # of every replay row per chunk) and on (event, market)
                "AND +run_date = 'cache-calibration' AND direction = 'OVER' "
                f"AND market IN ({marks_m}) AND outcome IN ('WIN', 'LOSS')"
            )
            for e, m, s, li, p, o in conn.execute(q, (*chunk, *REPLAY_MARKETS)):
                out.append(
                    (int(e), str(m), str(s), float(li), float(p), int(o == "WIN"))
                )
    finally:
        conn.close()
    return out


def run_history(args: argparse.Namespace) -> dict[str, Any]:
    history = load_football_history(args.football_history)
    minutes = load_minutes(args, history)
    fc = load_forecasts(args, history, minutes)
    params = load_params(args)
    r_nb = load_result_config().nb_r
    timed = {m.event_id: m for m in minutes}
    a, b = ts_of(FIT_TO), ts_of(HIST_EVAL_TO)
    pool = [
        r
        for r in history
        if a <= r.ts < b
        and not r.awarded
        and "goals_for" in fc.get(int(r.event_id), {})
    ]
    rng = np.random.default_rng(5)
    pick = sorted(
        rng.choice(len(pool), size=min(args.hist_matches, len(pool)), replace=False)
    )
    chosen = [pool[i] for i in pick]
    log(f"history evaluation: {len(chosen)} of {len(pool)} matches")
    replay = load_replay_rows(args.db, [int(r.event_id) for r in chosen])
    best: dict[tuple[int, str, str], tuple[float, float, int]] = {}
    for e, m, s, li, p, y in replay:
        if li != math.floor(li) + 0.5:
            continue
        bkey = (e, m, s)
        if bkey not in best or abs(p - 0.5) < abs(best[bkey][1] - 0.5):
            best[bkey] = (li, p, y)
    by_eid: dict[int, list[tuple[str, str, float, float, int]]] = defaultdict(list)
    for (e, m, s), (li, p, y) in best.items():
        by_eid[e].append((m, s, li, p, y))
    asks = []
    for r in chosen:
        eid = int(r.event_id)
        c = centres_from(fc[eid])
        if c is None:
            continue
        sels = []
        for m, s, li, _, _ in by_eid.get(eid, []):
            side = None
            if m.endswith("_for"):
                side = 0 if s == str(r.home_id) else 1 if s == str(r.away_id) else None
                if side is None:
                    continue
            sels.append((f"{m}|{s}|{li}", m, s, li, "OVER", side))
        for subj in ("1", "X", "2"):
            sels.append((f"1x2|{subj}", "result_1x2", subj, 0.5, "OVER", None))
        sels.append(("gt25", "goals_total", "", 2.5, "OVER", None))
        hv = fc[eid]
        halves = None
        if "goals_1h_for" in hv and "goals_2h_for" in hv:
            halves = (hv["goals_1h_for"], hv["goals_2h_for"])
        paths = tuple((f"{k}|{p}", k, p) for k, p in HIST_PATHS)
        asks.append(
            Ask(
                eid=eid,
                centres=c,
                selections=tuple(sels),
                paths=paths,
                baseline_halves=halves,
            )
        )
    got = run_asks(asks, params, args.sims, r_nb, args.workers)
    by_id = {int(r.event_id): r for r in chosen}
    legs: list[Leg] = []
    for eid, out in got.items():
        r = by_id[eid]
        day = datetime.fromtimestamp(r.ts, UTC).strftime("%Y-%m-%d")
        mu = centres_from(fc[eid])
        assert mu is not None
        # control (c): the replay's rows
        for m, s, li, p_cur, y in by_eid.get(eid, []):
            pv = out.get(f"{m}|{s}|{li}")
            if pv is None:
                continue
            fam = HIST_FAMILY[m]
            legs.append(Leg(eid, day, fam, y, pv, p_cur))
            legs.append(Leg(eid, day, fam, 1 - y, 1.0 - pv, 1.0 - p_cur, scored=False))
        # 1X2 and over 2.5 against SHEET's NB formula on the same centres
        g = r.values["goals_for"]
        res = "1" if g[0] > g[1] else "2" if g[1] > g[0] else "X"
        nb = nb_result_probs(mu.goals, r_nb)
        for subj in ("1", "X", "2"):
            pv = out.get(f"1x2|{subj}")
            if pv is not None:
                legs.append(Leg(eid, day, "c1_result", int(res == subj), pv, nb[subj]))
        pv = out.get("gt25")
        if pv is not None:
            yv = int(g[0] + g[1] > 2.5)
            pc = nb_total_over(mu.goals, r_nb, 2.5)
            legs.append(Leg(eid, day, "c2_goals_total_nb", yv, pv, pc))
            legs.append(
                Leg(eid, day, "c2_goals_total_nb", 1 - yv, 1 - pv, 1 - pc, scored=False)
            )
        # path markets (a) against independent NB halves
        mm = minute_match_of(r, timed)
        for k, prm in HIST_PATHS if mm is not None else ():
            pkey = f"{k}|{prm}"
            sim, base = out.get(pkey), out.get("base:" + pkey)
            win = None if mm is None else path_actual(mm, k, prm)
            if sim is None or base is None or win is None:
                continue
            fam = PATH_FAMILY[k]
            for outcome, p in sim.items():
                legs.append(
                    Leg(
                        eid,
                        day,
                        fam,
                        int(outcome == win),
                        p,
                        base.get(outcome, 0.0),
                        detail=k,
                    )
                )
            if k == "correct_score" and win not in sim:
                legs.append(Leg(eid, day, fam, 1, 0.0, base.get(win, 0.0), detail=k))
    with (args.out_dir / "history_legs.jsonl").open("w", encoding="utf-8") as fh:
        for x in legs:
            fh.write(json.dumps(x.__dict__) + "\n")
    fams = tuple(sorted({x.family for x in legs}))
    return {
        "matches": len(got),
        "replay_rows": len(best),
        "families": report(legs, fams, with_price=False),
    }


# --------------------------------------------------------------------------
# Superbet: settled lines and the path markets SHEET does not read
# --------------------------------------------------------------------------

SB_FROM = "2026-10-07"
SB_TO = "2026-11-06"  # exclusive
UNMAPPED_FROM = "2026-10-14"
HOLDOUT_FROM = "2026-10-25"
LIVE_DB_NAME = "live_rows.db"

LIVE_FAMILIES: tuple[tuple[str, str], ...] = (
    # (regex on market, family) - first match wins
    (r"^(result_1x2|double_chance|draw_no_bet)$", "c1_result"),
    (r"^goals_total$", "c2_goals_total"),
    (r"^goals_for$", "c3_goals_for"),
    (
        r"^(both_over_goals|btts_or_over|result_or_over|result_or_under|result_or_btts"
        r"|result_or_clean_sheet|result_handicap|dc_and_over|dc_and_under)$",
        "c4_score_combos",
    ),
    (r"^goals_(1h|2h)_(total|for)$|^both_over_goals_(1h|2h)$", "a6_half_goals"),
    (r"^first_goal$", "a5_first_goal"),
    (r"corners", "c5_corners"),
    (r"cards_points|red_cards", "c6_cards"),
    (r"fouls", "c7_fouls"),
    (r"shots", "c8_shots"),
)
SB_FAMILIES = (
    "a1_htft",
    "a2_half_result",
    "a3_higher_half",
    "a4_goal_both_halves",
    "a5_first_goal",
    "a6_half_goals",
    "c1_result",
    "c2_goals_total",
    "c3_goals_for",
    "c4_score_combos",
    "c5_corners",
    "c6_cards",
    "c7_fouls",
    "c8_shots",
    "x_odd_even",
    "x_exact_goals",
    "x_correct_score",
)


def live_family(market: str) -> str | None:
    # player props are not team counts ("player_shots_for" would match "shots")
    if market.startswith("player_"):
        return None
    for pat, fam in LIVE_FAMILIES:
        if re.search(pat, market):
            return fam
    return None


def _json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def day_list(lo: str, hi: str) -> list[str]:
    out = []
    t = ts_of(lo)
    while t < ts_of(hi):
        out.append(datetime.fromtimestamp(t, UTC).strftime("%Y-%m-%d"))
        t += 86400
    return out


GROUP_MARKETS = re.compile(r"^(first_goal|most_[a-z_0-9]+|handicap_[a-z_0-9]+)$")


def group_price(
    book: DayBook, eid: int, market: str, subject: str, line: float
) -> float | None:
    """The de-vigged p of a one-sided rung read with the rest of its set: the
    three selections of a first goal / most market, or a handicap with the
    other side's opposite handicap."""
    me = fold(subject)
    if market.startswith("handicap_"):
        mine = book.groups.get((eid, market, line), {}).get(me)
        other = {
            k: v
            for k, v in book.groups.get((eid, market, -line), {}).items()
            if k != me
        }
        if mine is None or len(other) != 1:
            return None
        odds = [mine, *other.values()]
    else:
        g = book.groups.get((eid, market, line), {})
        if me not in g or len(g) != 3:
            return None
        mine, odds = g[me], list(g.values())
    tot = sum(1.0 / o for o in odds)
    lo, hi = PAIR_OVERROUND if len(odds) == 2 else MULTI_OVERROUND
    if not lo <= tot <= hi:
        return None
    return (1.0 / mine) / tot


@dataclass
class DayBook:
    """One day's fixtures, board side names and offer rungs."""

    fixtures: dict[int, dict[str, Any]]
    board: dict[str, tuple[str, str]]  # superbet event id -> (side_a, side_b)
    rungs: dict[tuple[int, str, str, float], tuple[float | None, float | None]]
    # (event, market, line) -> {folded subject: over odds}: the one-sided
    # rungs of a multi-way market (first goal, most, handicap) priced as a set
    groups: dict[tuple[int, str, float], dict[str, float]] = field(default_factory=dict)


def load_day(runs: Path, day: str) -> DayBook:
    fixtures: dict[int, dict[str, Any]] = {}
    fx = _json(runs / day / "02_fixtures.json")
    for f in (fx if isinstance(fx, list) else (fx or {}).get("fixtures", [])) or []:
        if f.get("sport") == "football" and f.get("sofascore_event_id"):
            fixtures[int(f["sofascore_event_id"])] = f
    board: dict[str, tuple[str, str]] = {}
    bd = _json(runs / day / "01_board.json")
    for e in (bd if isinstance(bd, list) else []) or []:
        if e.get("sport") == "football":
            board[str(e.get("superbet_event_id"))] = (
                str(e.get("side_a") or ""),
                str(e.get("side_b") or ""),
            )
    rungs: dict[tuple[int, str, str, float], tuple[float | None, float | None]] = {}
    groups: dict[tuple[int, str, float], dict[str, float]] = {}
    off = _json(runs / day / "04_offer.json")
    for e in (off if isinstance(off, list) else []) or []:
        eid = e.get("sofascore_event_id")
        if not isinstance(eid, int) or eid not in fixtures:
            continue
        for r in e.get("rungs") or []:
            try:
                key = (
                    eid,
                    str(r["market"]),
                    fold(str(r.get("subject") or "")),
                    float(r["line"]),
                )
            except (KeyError, TypeError, ValueError):
                continue
            oo, uo = r.get("over_odds"), r.get("under_odds")
            rungs[key] = (float(oo) if oo else None, float(uo) if uo else None)
            if oo and GROUP_MARKETS.match(key[1]):
                groups.setdefault((eid, key[1], key[3]), {})[key[2]] = float(oo)
    return DayBook(fixtures, board, rungs, groups)


def board_names(book: DayBook, eid: int) -> tuple[str, str] | None:
    f = book.fixtures.get(eid) or {}
    for sid in f.get("superbet_event_ids") or []:
        if str(sid) in book.board:
            return book.board[str(sid)]
    return None


def team_side(name: str, book: DayBook, eid: int) -> int | None:
    """0 / 1 for a selection naming exactly one side (board names first,
    then Sofascore's), else None - never guessed."""
    names = board_names(book, eid)
    if names is not None:
        got = dnb_side(name, names[0], names[1])
        if got is not None:
            return 0 if got == "1" else 1
    f = book.fixtures.get(eid) or {}
    got = dnb_side(name, f.get("home_name"), f.get("away_name"))
    return None if got is None else 0 if got == "1" else 1


@dataclass(frozen=True)
class LiveRow:
    day: str
    eid: int
    market: str
    subject: str
    line: float
    direction: str
    p_cur: float
    odds: float
    y: int
    side: int | None


def load_live_rows(out_dir: Path) -> list[tuple[Any, ...]]:
    conn = sqlite3.connect(f"file:{out_dir / LIVE_DB_NAME}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            "SELECT run_date, eid, market, subject, line, direction, p_central, "
            "offered_odds, outcome FROM r WHERE run_date >= ? AND run_date < ? "
            "AND outcome IN ('WIN', 'LOSS') AND offered_odds > 1",
            (SB_FROM, SB_TO),
        ).fetchall()
    finally:
        conn.close()
    return rows


_NEEDS_HALF_LINE = re.compile(
    r"^(goals|corners|cards_points|fouls|shots|shots_on_target|red_cards)(_1h|_2h)?_(for|total)$"
    r"|^both_over_|^handicap_|^result_handicap$|^(result_or|btts_or|dc_and)_"
)


# Path markets in Superbet's words (unmapped_prices marketName) -> kind.
_HALF_TOTALS = re.compile(r"^(powyżej|poniżej) (\d+\.5) & (powyżej|poniżej) (\d+\.5)$")
_BAND = {
    "0:00 - 14:59 minuty": "0",
    "15:00 - 29:59 minuty": "1",
    "30:00 - 45:00+": "2",
    "45:00 - 59 minuty:59 minuty": "3",
    "60:00 - 74:59 minuty": "4",
    "75:00 - 90:00+": "5",
    "Brak goli w meczu": "none",
}
PATH_MARKETS = {
    "1. połowa/mecz": "htft",
    "1.połowa - 1X2": "half_result:1",
    "2.połowa - 1X2": "half_result:2",
    "Połowa z większą liczbą goli": "higher_half",
    "Obie drużyny strzelą gola - 1.połowa/2.połowa": "btts_halves",
    "Obie drużyny strzelą w przynajmniej jednej połowie meczu": "btts_any_half",
    "1.połowa liczba goli & 2.połowa liczba goli": "half_totals",
    "1. gol (przedziały 15-minutowe)": "first_goal_band15",
    "1. połowa - 1. gol": "first_goal_1h",
    "Ostatni gol": "last_goal",
    "Nieparzysta/parzysta liczba goli": "odd_even",
    "Dokładna liczba goli": "exact_goals",
    "Dokładny wynik": "correct_score:2",
    "1.połowa - dokładny wynik": "correct_score:0",
    "2. połowa - dokładny wynik": "correct_score:1",
}
TEAM_BOTH_HALVES = " zdobędzie gola w obu połowach"
EXPECTED: dict[str, set[str]] = {
    "htft": {f"{a}/{b}" for a in "1X2" for b in "1X2"},
    "half_result": {"1", "X", "2"},
    "higher_half": {"1H", "X", "2H"},
    "btts_halves": {"Tak/Tak", "Tak/Nie", "Nie/Tak", "Nie/Nie"},
    "btts_any_half": {"tak", "nie"},
    "team_both_halves": {"tak", "nie"},
    "half_totals": {"O/O", "O/U", "U/O", "U/U"},
    "first_goal_band15": {"0", "1", "2", "3", "4", "5", "none"},
    "first_goal_1h": {"1", "2", "none"},
    "last_goal": {"1", "2", "none"},
    "odd_even": {"odd", "even"},
    "exact_goals": {"0", "1", "2", "3", "4", "5", "6+"},
}


def path_key(
    market: str, name: str, book: DayBook, eid: int
) -> tuple[str, Any, str] | None:
    """(kind, param, outcome key) of one unmapped odd, or None."""
    if market.endswith(TEAM_BOTH_HALVES):
        side = team_side(market[: -len(TEAM_BOTH_HALVES)], book, eid)
        if side is None or name not in ("tak", "nie"):
            return None
        return "team_both_halves", side, name
    spec = PATH_MARKETS.get(market)
    if spec is None:
        return None
    kind, _, prm = spec.partition(":")
    param: Any = int(prm) if prm else None
    if kind == "htft":
        return (kind, None, name) if name in EXPECTED["htft"] else None
    if kind in ("half_result", "first_goal_1h", "last_goal"):
        if name in ("remis", "nikt"):
            return kind, param, "X" if kind == "half_result" else "none"
        side = team_side(name, book, eid)
        return None if side is None else (kind, param, "1" if side == 0 else "2")
    if kind == "higher_half":
        key = {"1.Połowa": "1H", "2.Połowa": "2H", "remis": "X"}.get(name)
        return None if key is None else (kind, None, key)
    if kind in ("btts_halves", "btts_any_half"):
        return (kind, None, name) if name in EXPECTED[kind] else None
    if kind == "half_totals":
        m = _HALF_TOTALS.match(name)
        if m is None:
            return None
        first = "O" if m.group(1) == "powyżej" else "U"
        second = "O" if m.group(3) == "powyżej" else "U"
        return kind, (float(m.group(2)), float(m.group(4))), f"{first}/{second}"
    if kind == "first_goal_band15":
        key = _BAND.get(name)
        return None if key is None else (kind, None, key)
    if kind == "odd_even":
        key = {"nieparzysta": "odd", "parzysta": "even"}.get(name)
        return None if key is None else (kind, None, key)
    if kind == "exact_goals":
        return (kind, None, name) if name in EXPECTED["exact_goals"] else None
    if kind == "correct_score":
        return (kind, param, name) if re.match(r"^\d+:\d+$", name) else None
    return None


def load_unmapped(
    runs: Path, days: list[str], books: dict[str, DayBook], drops: Counter[str]
) -> dict[int, list[tuple[str, str, Any, dict[str, float]]]]:
    """Per event: (day, kind, param, {outcome: price}) of the latest
    pre-match snapshot that carried each path market (the de-vig needs one
    snapshot's prices)."""
    import gzip

    wanted_names = set(PATH_MARKETS)
    latest: dict[tuple[int, str, str], tuple[str, dict[str, float]]] = {}
    for day in days:
        book = books[day]
        files = sorted((runs / day / "unmapped_prices").glob("2026*.jsonl.gz"))
        for f in files:
            tmp: dict[tuple[int, str, str], dict[str, float]] = defaultdict(dict)
            with gzip.open(f, "rt", encoding="utf-8") as fh:
                for line in fh:
                    if '"marketName": "' not in line:
                        continue
                    d = json.loads(line)
                    mkt = d.get("marketName")
                    if mkt not in wanted_names and not str(mkt).endswith(
                        TEAM_BOTH_HALVES
                    ):
                        continue
                    eid = d.get("sofascore_event_id")
                    price = d.get("price")
                    if (
                        not isinstance(eid, int)
                        or eid not in book.fixtures
                        or not isinstance(price, int | float)
                        or price <= 1.0
                        or d.get("status") not in (None, "active")
                    ):
                        continue
                    tmp[(eid, str(mkt), str(d.get("specialBetValue")))][
                        str(d["name"])
                    ] = float(price)
            for key, prices in tmp.items():
                latest[key] = (day, prices)
    out: dict[int, list[tuple[str, str, Any, dict[str, float]]]] = defaultdict(list)
    for (eid, mkt, _), (day, prices) in latest.items():
        groups: dict[tuple[str, Any], dict[str, float]] = defaultdict(dict)
        for name, price in prices.items():
            got = path_key(mkt, name, books[day], eid)
            if got is None:
                drops["path_outcome_unread"] += 1
                continue
            kind, param, okey = got
            groups[(kind, param)][okey] = price
        for (kind, param), g in groups.items():
            exp = EXPECTED.get(kind)
            if exp is not None and set(g) != exp:
                drops["path_group_incomplete"] += 1
                continue
            over = sum(1.0 / v for v in g.values())
            lo, hi = PAIR_OVERROUND if len(g) == 2 else MULTI_OVERROUND
            if kind != "correct_score" and not lo <= over <= hi:
                drops["path_overround"] += 1
                continue
            out[eid].append((day, kind, param, g))
    return out


# --- joint_history (bet.sofa.dossier.joint_history), as of the kickoff ------

JH_MIN_N = 5


class DossierKN:
    """k / n of a set of legs together in the two sides' newest games -
    exactly ``dossier.joint_history``'s count (its own game reader
    ``_metric_games`` and leg grader ``_leg_hit``, read-only), the games of
    one fixture fetched once for every pair of that fixture."""

    def __init__(self, db: Path) -> None:
        self.con = dossier.connect(db)

    def close(self) -> None:
        self.con.close()

    def per_event(
        self, fx: dict[str, Any], pairs: list[list[dict[str, Any]]]
    ) -> list[tuple[int, int] | None]:
        home, away = fx.get("home_entity_id"), fx.get("away_entity_id")
        kickoff = dossier._parse_ts(fx.get("kickoff_utc"))
        if not isinstance(home, int) or not isinstance(away, int) or kickoff is None:
            return [None for _ in pairs]
        names = {"home": fx.get("home_name"), "away": fx.get("away_name")}
        metrics = sorted(
            {
                found[0]
                for legs in pairs
                for x in legs
                if (found := dossier.leg_metric(str(x.get("market"))))
            }
        )
        cache: dict[tuple[int, int], dict[str, Any]] = {}
        out_of = dossier.awarded_out_at(kickoff)
        lists = {
            "home": dossier._metric_games(
                self.con, home, kickoff, metrics, cache, out_of
            ),
            "away": dossier._metric_games(
                self.con, away, kickoff, metrics, cache, out_of
            ),
        }
        out: list[tuple[int, int] | None] = []
        for legs in pairs:
            if any(dossier.leg_metric(str(x.get("market"))) is None for x in legs):
                out.append(None)
                continue
            k = n = 0
            seen: set[int] = set()
            for owner, games in lists.items():
                for g in games:
                    if g["_event"] in seen:
                        continue
                    seen.add(g["_event"])
                    hits = [dossier._leg_hit(x, g, owner, names) for x in legs]
                    if any(h is None for h in hits):
                        continue
                    n += 1
                    k += all(hits)
            out.append((k, n) if n else None)
        return out


def dossier_leg(row: LiveRow, fx: dict[str, Any]) -> dict[str, Any]:
    """A settled row as the dossier reads a leg; a side leg names the side
    by its Sofascore name (the side is already mapped)."""
    subject = row.subject
    if row.side is not None:
        subject = str(fx.get("home_name") if row.side == 0 else fx.get("away_name"))
    return {
        "sofascore_event_id": row.eid,
        "market": row.market,
        "subject": subject,
        "line": row.line,
        "direction": row.direction,
    }


JOINT_TYPES: tuple[tuple[str, str, str], ...] = (
    # (name, market a, market b); a "_for" pair is read on one side
    ("goals_total+corners_total", "goals_total", "corners_total"),
    ("goals_total+cards_points_total", "goals_total", "cards_points_total"),
    ("result_1x2+goals_total", "result_1x2", "goals_total"),
    ("result_1x2+cards_points_total", "result_1x2", "cards_points_total"),
    ("result_1x2+corners_total", "result_1x2", "corners_total"),
    ("both_over_goals+goals_total", "both_over_goals", "goals_total"),
    ("goals_for+corners_for", "goals_for", "corners_for"),
    ("corners_total+cards_points_total", "corners_total", "cards_points_total"),
    ("goals_1h_total+goals_2h_total", "goals_1h_total", "goals_2h_total"),
    ("shots_on_target_total+goals_total", "shots_on_target_total", "goals_total"),
)
JOINT_TARGET = 0.70


def pick_leg(
    rows: list[LiveRow], market: str, side: int | None = None
) -> LiveRow | None:
    cand = [r for r in rows if r.market == market and (side is None or r.side == side)]
    if market in ("result_1x2",):
        cand = [r for r in cand if r.subject in ("1", "2")]
    if not cand:
        return None
    return min(cand, key=lambda r: (abs(r.p_cur - JOINT_TARGET), r.line, r.direction))


def run_superbet(args: argparse.Namespace) -> dict[str, Any]:
    history, added_min = live_history(
        args, load_football_history(args.football_history)
    )
    minutes = [*load_minutes(args, history), *added_min]
    fc = load_live_forecasts(args, history)
    params = load_params(args)
    r_nb = load_result_config().nb_r
    timed = {m.event_id: m for m in minutes}
    by_id = {int(r.event_id): r for r in history}
    drops: Counter[str] = Counter()
    days = day_list(SB_FROM, SB_TO)
    books = {d: load_day(args.runs_dir, d) for d in days}
    log(f"day books loaded: {len(books)}")

    # orientation: the fixture's home must be the history's home
    def orient(eid: int, book: DayBook) -> bool | None:
        f, r = book.fixtures.get(eid), by_id.get(eid)
        if f is None or r is None:
            return None
        if (f.get("home_entity_id"), f.get("away_entity_id")) == (r.home_id, r.away_id):
            return False
        if (f.get("home_entity_id"), f.get("away_entity_id")) == (r.away_id, r.home_id):
            return True
        return None

    live: list[LiveRow] = []
    for day, eid, market, subject, line, direction, p, odds, outcome in load_live_rows(
        args.out_dir
    ):
        book = books.get(day)
        if book is None or eid not in book.fixtures:
            drops["live_no_fixture"] += 1
            continue
        if live_family(market) is None:
            drops["live_market_not_read"] += 1
            continue
        if _NEEDS_HALF_LINE.search(market) and float(line) == math.floor(float(line)):
            drops["live_integer_line"] += 1
            continue
        swap = orient(eid, book)
        if swap is None:
            drops["live_sides_disagree"] += 1
            continue
        side: int | None = None
        if subject and subject not in (
            "1",
            "X",
            "2",
            "1X",
            "X2",
            "12",
            "nikt",
            "__draw__",
        ):
            side = team_side(subject, book, eid)
            if side is None:
                drops["live_subject_unmapped"] += 1
                continue
            if swap:
                side = 1 - side
        if swap and market in (
            "result_1x2",
            "double_chance",
            "draw_no_bet",
            "result_or_over",
            "result_or_under",
            "result_or_btts",
            "result_or_clean_sheet",
            "result_handicap",
            "dc_and_over",
            "dc_and_under",
        ):
            drops["live_swapped_result_market"] += 1
            continue
        live.append(
            LiveRow(
                day,
                int(eid),
                market,
                subject,
                float(line),
                direction,
                float(p),
                float(odds),
                int(outcome == "WIN"),
                side,
            )
        )
    log(f"live rows kept: {len(live)}; drops {dict(drops)}")
    paths = load_unmapped(args.runs_dir, day_list(UNMAPPED_FROM, SB_TO), books, drops)
    n_groups = sum(len(v) for v in paths.values())
    log(f"path markets: {n_groups} groups on {len(paths)} events")
    by_event: dict[int, list[LiveRow]] = defaultdict(list)
    for row in live:
        by_event[row.eid].append(row)
    events = sorted(set(by_event) | set(paths))
    holdout_days = set(day_list(HOLDOUT_FROM, SB_TO))
    asks: list[Ask] = []
    joints_meta: dict[int, list[tuple[str, LiveRow, LiveRow]]] = defaultdict(list)
    for eid in events:
        c = centres_from(fc.get(eid, {}))
        if c is None or eid not in by_id:
            drops["event_no_forecast"] += 1
            continue
        rows = by_event.get(eid, [])
        if not args.holdout:
            rows = [r for r in rows if r.day not in holdout_days]
        sels = tuple(
            (
                f"{r.market}|{r.subject}|{r.line}|{r.direction}",
                r.market,
                r.subject,
                r.line,
                r.direction,
                r.side,
            )
            for r in rows
        )
        jl = []
        for name, ma, mb in JOINT_TYPES:
            if ma.endswith("_for"):
                la = pick_leg(rows, ma)
                lb = None if la is None else pick_leg(rows, mb, la.side)
            else:
                la, lb = pick_leg(rows, ma), pick_leg(rows, mb)
            if la is None or lb is None:
                continue
            ka = f"{la.market}|{la.subject}|{la.line}|{la.direction}"
            kb = f"{lb.market}|{lb.subject}|{lb.line}|{lb.direction}"
            jl.append((f"joint|{name}", ka, kb))
            joints_meta[eid].append((name, la, lb))
        pth = tuple(
            (f"{kind}|{param}|{day}", kind, param)
            for day, kind, param, _ in paths.get(eid, [])
            if args.holdout or day not in holdout_days
        )
        if not sels and not pth:
            continue
        asks.append(
            Ask(eid=eid, centres=c, selections=sels, paths=pth, joints=tuple(jl))
        )
    log(f"asks: {len(asks)} events")
    got = run_asks(asks, params, args.sims, r_nb, args.workers)
    jh = DossierKN(args.db)
    legs: list[Leg] = []
    jlegs: list[dict[str, Any]] = []
    for eid, out in got.items():
        rows = by_event.get(eid, [])
        # live rows (SHEET's markets); the price from the day's offer rung
        for r in rows:
            key = f"{r.market}|{r.subject}|{r.line}|{r.direction}"
            p = out.get(key)
            if p is None:
                drops["live_not_simulated"] += 1
                continue
            rung = books[r.day].rungs.get((eid, r.market, fold(r.subject), r.line))
            p_price = None
            if rung is not None and rung[0] and rung[1]:
                io, iu = 1.0 / rung[0], 1.0 / rung[1]
                if PAIR_OVERROUND[0] <= io + iu <= PAIR_OVERROUND[1]:
                    p_price = (
                        io / (io + iu) if r.direction == "OVER" else iu / (io + iu)
                    )
            if p_price is None and GROUP_MARKETS.match(r.market):
                p_price = group_price(books[r.day], eid, r.market, r.subject, r.line)
                if p_price is not None and r.direction == "UNDER":
                    p_price = 1.0 - p_price
            if p_price is None:
                drops["live_no_pair_price"] += 1
                continue
            fam = live_family(r.market) or "?"
            # one scored row per rung: the OVER when it settled, else the UNDER
            scored = r.direction == "OVER" or not any(
                x.market == r.market
                and x.subject == r.subject
                and x.line == r.line
                and x.direction == "OVER"
                for x in rows
            )
            legs.append(
                Leg(
                    eid,
                    r.day,
                    fam,
                    r.y,
                    p,
                    r.p_cur,
                    p_price,
                    r.odds,
                    scored=scored,
                    detail=r.market,
                )
            )
        # path markets: de-vigged over the whole set of outcomes
        rr = by_id[eid]
        mm = minute_match_of(rr, timed)
        if mm is None and paths.get(eid):
            drops["path_no_score"] += len(paths[eid])
        for day, kind, param, prices in paths.get(eid, []) if mm is not None else []:
            key = f"{kind}|{param}|{day}"
            sim = out.get(key)
            if sim is None:
                continue
            win = None if mm is None else path_actual(mm, kind, param)
            if win is None:
                drops["path_ungraded"] += 1
                continue
            tot = sum(1.0 / v for v in prices.values())
            fam = PATH_FAMILY[kind]
            for outcome, price in prices.items():
                legs.append(
                    Leg(
                        eid,
                        day,
                        fam,
                        int(outcome == win),
                        sim.get(outcome, 0.0),
                        None,
                        (1.0 / price) / tot,
                        price,
                        detail=kind,
                    )
                )
        # joints
        jm = joints_meta.get(eid, [])
        fx = books[jm[0][1].day].fixtures.get(eid, {}) if jm else {}
        kns = (
            jh.per_event(
                fx, [[dossier_leg(la, fx), dossier_leg(lb, fx)] for _, la, lb in jm]
            )
            if jm
            else []
        )
        for (name, la, lb), kn in zip(jm, kns, strict=True):
            pj = out.get(f"joint|{name}")
            ka = f"{la.market}|{la.subject}|{la.line}|{la.direction}"
            kb = f"{lb.market}|{lb.subject}|{lb.line}|{lb.direction}"
            pa, pb = out.get(ka), out.get(kb)
            if pj is None or pa is None or pb is None:
                continue
            jlegs.append(
                {
                    "eid": eid,
                    "day": la.day,
                    "type": name,
                    "y": la.y * lb.y,
                    "p_joint": pj,
                    "p_product": pa * pb,
                    "p_cur_product": la.p_cur * lb.p_cur,
                    "p_a": pa,
                    "p_b": pb,
                    "y_a": la.y,
                    "y_b": lb.y,
                    "k": None if kn is None else kn[0],
                    "n": None if kn is None else kn[1],
                    "legs": [ka, kb],
                }
            )
    with (
        args.out_dir
        / ("superbet_legs_holdout.jsonl" if args.holdout else "superbet_legs_dev.jsonl")
    ).open("w", encoding="utf-8") as fh:
        for x in legs:
            fh.write(json.dumps(x.__dict__) + "\n")
    with (
        args.out_dir / ("joints_holdout.jsonl" if args.holdout else "joints_dev.jsonl")
    ).open("w", encoding="utf-8") as fh:
        for j in jlegs:
            fh.write(json.dumps(j) + "\n")
    dev = [x for x in legs if x.day not in holdout_days]
    out_doc: dict[str, Any] = {
        "drops": dict(drops),
        "events": len(got),
        "dev": report(dev, SB_FAMILIES, with_price=True),
        "joints_dev": joint_report([j for j in jlegs if j["day"] not in holdout_days]),
    }
    if args.holdout:
        hold = [x for x in legs if x.day in holdout_days]
        out_doc["holdout"] = report(hold, SB_FAMILIES, with_price=True)
        out_doc["joints_holdout"] = joint_report(
            [j for j in jlegs if j["day"] in holdout_days]
        )
    return out_doc


def joint_report(jlegs: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    types = sorted({j["type"] for j in jlegs})
    for t in (*types, "all"):
        sel = [j for j in jlegs if t == "all" or j["type"] == t]
        if not sel:
            continue
        g = [j["eid"] for j in sel]
        b_joint = [brier(j["p_joint"], j["y"]) for j in sel]
        b_prod = [brier(j["p_product"], j["y"]) for j in sel]
        b_cur = [brier(j["p_cur_product"], j["y"]) for j in sel]
        rec: dict[str, Any] = {
            "n": len(sel),
            "matches": len(set(g)),
            "realised": sum(j["y"] for j in sel) / len(sel),
            "mean_joint": sum(j["p_joint"] for j in sel) / len(sel),
            "mean_product": sum(j["p_product"] for j in sel) / len(sel),
            "mean_cur_product": sum(j["p_cur_product"] for j in sel) / len(sel),
            "brier_joint": sum(b_joint) / len(sel),
            "joint_minus_product": boot_mean(
                g, [a - b for a, b in zip(b_joint, b_prod, strict=True)]
            ),
            "joint_minus_cur_product": boot_mean(
                g, [a - b for a, b in zip(b_joint, b_cur, strict=True)]
            ),
            "gap_joint": boot_mean(g, [j["y"] - j["p_joint"] for j in sel]),
            "gap_product": boot_mean(g, [j["y"] - j["p_product"] for j in sel]),
            "gap_cur_product": boot_mean(g, [j["y"] - j["p_cur_product"] for j in sel]),
        }
        kn = [j for j in sel if j["n"] is not None and j["n"] >= JH_MIN_N]
        if kn:
            gk = [j["eid"] for j in kn]
            rec["jh_n"] = len(kn)
            rec["jh_joint_minus_kn"] = boot_mean(
                gk,
                [
                    brier(j["p_joint"], j["y"]) - brier(j["k"] / j["n"], j["y"])
                    for j in kn
                ],
            )
            rec["jh_mean_kn"] = sum(j["k"] / j["n"] for j in kn) / len(kn)
            rec["jh_realised"] = sum(j["y"] for j in kn) / len(kn)
            rec["jh_brier_kn"] = sum(brier(j["k"] / j["n"], j["y"]) for j in kn) / len(
                kn
            )
            rec["jh_brier_joint"] = sum(brier(j["p_joint"], j["y"]) for j in kn) / len(
                kn
            )
        out[t] = rec
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    ap.add_argument("--runs-dir", type=Path, default=DEFAULT_RUNS)
    ap.add_argument("--football-history", type=Path, default=DEFAULT_FOOTBALL_HISTORY)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--val-sims", type=int, default=2000)
    ap.add_argument("--sims", type=int, default=4000)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--hist-matches", type=int, default=HIST_MATCHES)
    ap.add_argument(
        "--holdout",
        action="store_true",
        help="also score the Superbet hold-out days (once)",
    )
    ap.add_argument(
        "--stage",
        choices=("inventory", "forecast", "fit", "history", "superbet"),
        required=True,
    )
    args = ap.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    if args.stage == "inventory":
        res = run_inventory(args)
        (args.out_dir / "inventory.json").write_text(
            json.dumps(res, indent=1), encoding="utf-8"
        )
        print(json.dumps(res["totals"], indent=1))
    if args.stage == "forecast":
        history = load_football_history(args.football_history)
        minutes = load_minutes(args, history)
        fc = load_forecasts(args, history, minutes)
        with_goals = sum(1 for v in fc.values() if "goals_for" in v)
        log(f"forecasts with a goals centre: {with_goals} / {len(fc)}")
    if args.stage == "fit":
        res = run_fit(args)
        (args.out_dir / "fit.json").write_text(
            json.dumps(res, indent=1), encoding="utf-8"
        )
        print(json.dumps({k: res[k] for k in ("chosen", "fit")}, indent=1)[:4000])
    if args.stage == "history":
        res = run_history(args)
        (args.out_dir / "history.json").write_text(
            json.dumps(res, indent=1), encoding="utf-8"
        )
        print(
            json.dumps(
                {f: v.get("verdict") for f, v in res["families"].items()}, indent=1
            )
        )
    if args.stage == "superbet":
        res = run_superbet(args)
        name = "superbet_holdout.json" if args.holdout else "superbet_dev.json"
        (args.out_dir / name).write_text(json.dumps(res, indent=1), encoding="utf-8")
        key = "holdout" if args.holdout else "dev"
        print(json.dumps({f: v.get("verdict") for f, v in res[key].items()}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
