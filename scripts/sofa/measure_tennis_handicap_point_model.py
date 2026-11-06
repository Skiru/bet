#!/usr/bin/env python3
"""Measure tennis games handicap from the bottom-up point model - read-only.
Report: docs/sofa/evidence/tennis_handicap_point_model_2026-11-06.md (rules
pre-registered in its section 0 before the first run).

One walk-forward of bet.sofa.tennis_point_model over the cached history
feeds three things:

  * ``curves``: the model's own history curves of ``handicap_games`` and the
    per-set handicaps, fitted as fit_tennis_point_curves.py fits its keys
    (2026-01-01 .. 2026-10-20, half lines with p in [0.10, 0.90], both
    sides), written to --out-dir only - never config/;
  * ``history``: the model against the current estimator's history replay
    rows (cache-calibration ``handicap_games`` of --replay-db, one line per
    match: the home side's line with the current p nearest 0.5);
  * ``superbet``: every settled Superbet handicap pair (live
    ``sofa_settled_row`` rows = 07_settled.json), model vs current
    ``p_central`` vs the de-vigged price, raw and after curves; the hold-out
    days only with ``--holdout``.

    PYTHONPATH=src:. taskpolicy -b nice -n 10 .venv/bin/python \\
        scripts/sofa/measure_tennis_handicap_point_model.py \\
        --history-cache <pkl> --out-dir <dir> [--holdout] [--workers 2]

Never the network; the databases are opened with ``mode=ro``.
"""

from __future__ import annotations

import argparse
import json
import math
import multiprocessing
import pickle
import random
import sqlite3
import sys
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa.tennis_handicap_point import (  # noqa: E402
    HANDICAP_MARKETS,
    p_handicap,
)
from bet.sofa.tennis_point_model import (  # noqa: E402
    MatchForecast,
    PointMatch,
    load_point_history,
    market_sim,
    walk_forward,
)
from scripts.sofa.fit_confidence import (  # noqa: E402
    EDGES,
    MIN_MARKET_BUCKET,
    MIN_THIN_BUCKET,
    bucket_of,
    wilson_lo,
)
from scripts.sofa.measure_tennis_point_model import (  # noqa: E402
    boot_mean,
    load_fixtures,
    orient,
    side_of,
)

DEFAULT_DB = _REPO / "data" / "sofa.db"
DEFAULT_REPLAY_DB = _REPO / "data" / "refit_2026-10-17" / "sofa_replay.db"
DEFAULT_CAL = _REPO / "config" / "sofa_confidence_calibration.json"

# Pre-registered (report section 0).
NONINFERIORITY_BRIER = 0.002
OVERROUND = (1.0, 1.30)
LIVE_FROM = "2026-09-18"
HOLDOUT_FROM = "2026-10-20"
HOLDOUT_TO = "2026-11-05"
CURVE_FROM = "2026-01-01"
CURVE_BEFORE = "2026-10-20"
HIST_FROM = "2026-01-01"
HIST_TO = "2026-10-16"
HIST_MAX = 15000
EXTRA_GAMES = 20000
SEED_EXTRA = 11
SEED_HIST = 5
LINE_P_LO, LINE_P_HI = 0.10, 0.90
MIN_LEGS = 30
TAX = 0.88
BANDS = (("p>=0.70", 0.70, 1.01), ("0.60-0.70", 0.60, 0.70))
FAMILY = {"handicap_games": "handicap_games",
          "handicap_games_won_set1": "handicap_set",
          "handicap_games_won_set2": "handicap_set"}
FAMILY_ORDER = ("handicap_games", "handicap_set")


def _ts(day: str) -> int:
    return int(datetime.fromisoformat(day).replace(tzinfo=UTC).timestamp())


# --------------------------------------------------------------------------
# Superbet pairs
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Pair:
    """One Superbet handicap pair, carried by the subject giving games
    (negative line): y = 1 when that subject covered."""

    day: str
    eid: int
    market: str
    subject: str  # the negative-line subject
    partner: str
    line: float  # < 0
    y: int
    odds: float
    odds_partner: float
    p_cur: float  # p_central of the subject's row
    p_cur_partner: float  # p_central of the partner's row
    side: int | None = None  # history orientation of `subject`: 0 home / 1 away
    female: bool = False
    p_new: float | None = None

    @property
    def family(self) -> str:
        return FAMILY[self.market]

    @property
    def p_price(self) -> float:
        a, b = 1.0 / self.odds, 1.0 / self.odds_partner
        return a / (a + b)


def load_pairs(db: Path) -> tuple[list[Pair], dict[str, int]]:
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    marks = ",".join("?" * len(HANDICAP_MARKETS))
    rows = conn.execute(
        "SELECT run_date, sofascore_event_id, market, subject, line, p_central, "
        "offered_odds, outcome FROM sofa_settled_row "
        "WHERE run_date >= ? AND run_date < 'c' AND sport = 'tennis' "
        f"AND direction = 'OVER' AND market IN ({marks}) "
        "AND outcome IN ('WIN', 'LOSS')",
        (LIVE_FROM, *HANDICAP_MARKETS),
    ).fetchall()
    conn.close()
    by: dict[tuple[int, str, float], list[tuple[Any, ...]]] = defaultdict(list)
    for day, eid, market, subject, line, p, odds, outcome in rows:
        by[(int(eid), str(market), abs(float(line)))].append(
            (str(day), str(subject), float(line), float(p), odds, str(outcome)))
    out: list[Pair] = []
    drop: dict[str, int] = defaultdict(int)
    for (eid, market, _), group in by.items():
        neg = [g for g in group if g[2] < 0]
        pos = [g for g in group if g[2] > 0]
        if len(neg) != 1 or len(pos) != 1 or neg[0][1] == pos[0][1]:
            drop["not_a_pair"] += 1
            continue
        a, b = neg[0], pos[0]
        if not a[4] or not b[4] or a[4] <= 1.0 or b[4] <= 1.0:
            drop["no_price"] += 1
            continue
        over_round = 1.0 / a[4] + 1.0 / b[4]
        if not OVERROUND[0] <= over_round <= OVERROUND[1]:
            drop["overround"] += 1
            continue
        if (a[5] == "WIN") == (b[5] == "WIN"):
            drop["grades_disagree"] += 1
            continue
        out.append(Pair(day=a[0], eid=eid, market=market, subject=a[1],
                        partner=b[1], line=a[2], y=1 if a[5] == "WIN" else 0,
                        odds=float(a[4]), odds_partner=float(b[4]), p_cur=a[3],
                        p_cur_partner=b[3]))
    return out, dict(drop)


# --------------------------------------------------------------------------
# Workers (fork: the module globals are the parent's)
# --------------------------------------------------------------------------

_JOBS: dict[int, tuple[PointMatch, MatchForecast]] = {}
SIMS = 4000


def _ladder(ms: Any, market: str, side: int) -> list[tuple[float, float]]:
    span = 25 if market == "handicap_games" else 7
    out: list[tuple[float, float]] = []
    for k in range(-span, span):
        line = k + 0.5
        p = p_handicap(ms, market, side, line)
        if p is not None and LINE_P_LO <= p <= LINE_P_HI:
            out.append((line, p))
    return out


def actual_margin(m: PointMatch, market: str, side: int) -> int | None:
    scope = HANDICAP_MARKETS[market]
    if scope == 0:
        own = sum(s[side] for s in m.sets)
        opp = sum(s[1 - side] for s in m.sets)
        return own - opp
    if len(m.sets) < scope:
        return None
    s = m.sets[scope - 1]
    return s[side] - s[1 - side]


def curve_job(task: tuple[int, tuple[tuple[float, int], ...]]) -> dict[str, Any]:
    """Ladder rows of one fitted match and the model's p at the history
    test's replay lines ((line, home side) pairs)."""
    eid, test_lines = task
    m, forecast = _JOBS[eid]
    ms = market_sim(forecast, n=SIMS, seed=eid % (2 ** 31))
    rows: list[tuple[str, float, int]] = []
    for market in HANDICAP_MARKETS:
        for side in (0, 1):
            margin = actual_margin(m, market, side)
            if margin is None:
                continue
            for line, p in _ladder(ms, market, side):
                rows.append((market, round(p, 5), 1 if margin + line > 0 else 0))
    test = [(line, side, p_handicap(ms, "handicap_games", side, line))
            for line, side in test_lines]
    return {"eid": eid, "female": m.female, "rows": rows, "test": test}


def price_job(eid: int) -> tuple[int, Any]:
    _, forecast = _JOBS[eid]
    ms = market_sim(forecast, n=SIMS, seed=eid % (2 ** 31))
    return eid, {(mk, s, ln): p_handicap(ms, mk, s, ln)
                 for mk in HANDICAP_MARKETS for s in (0, 1)
                 for ln in [k + 0.5 for k in range(-25, 25)]}


def _pool(workers: int) -> ProcessPoolExecutor:
    return ProcessPoolExecutor(max_workers=workers,
                               mp_context=multiprocessing.get_context("fork"))


# --------------------------------------------------------------------------
# Curves
# --------------------------------------------------------------------------

Counts = dict[str, dict[int, list[int]]]


def _curve(counts: Mapping[int, Sequence[int]], floor: int,
           below: int | None = None) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for b, (k, n) in sorted(counts.items()):
        if n < floor or (below is not None and n >= below):
            continue
        out[f"{EDGES[b]:.3f}-{EDGES[b + 1]:.3f}"] = {
            "n": n, "realised": round(k / n, 4),
            "realised_lo95": round(wilson_lo(k, n), 4)}
    return out


def curve_sections(counts: Counts) -> dict[str, Any]:
    return {
        "by_market_direction": {f"{m}|OVER": c for m, cs in sorted(counts.items())
                                if (c := _curve(cs, MIN_MARKET_BUCKET))},
        "thin_by_market_direction": {
            f"{m}|OVER": c for m, cs in sorted(counts.items())
            if (c := _curve(cs, MIN_THIN_BUCKET, below=MIN_MARKET_BUCKET))},
    }


def lookup(section: Mapping[str, Any] | None, market: str, p: float) -> float | None:
    """realised_lo95 of p's bucket: by_market_direction, else the thin
    section; None = no curve (the leg reads nothing)."""
    if not section:
        return None
    key = f"{market}|OVER"
    for name in ("by_market_direction", "thin_by_market_direction"):
        curve = (section.get(name) or {}).get(key) or {}
        for label, entry in curve.items():
            lo, hi = (float(x) for x in label.split("-"))
            if lo <= p < hi:
                return float(entry["realised_lo95"])
    return None


def confidence(cal: Mapping[str, Any] | None, market: str, p: float,
               female: bool) -> float | None:
    if cal is None:
        return None
    if female:
        return lookup((cal.get("by_class") or {}).get("tennis_women"), market, p)
    return lookup(cal, market, p)


# --------------------------------------------------------------------------
# Scoring
# --------------------------------------------------------------------------


def brier(p: float, y: int) -> float:
    return (p - y) ** 2


def logloss(p: float, y: int) -> float:
    p = min(max(p, 1e-4), 1.0 - 1e-4)
    return -math.log(p if y else 1.0 - p)


def fmt(t: Sequence[float], digits: int = 4) -> str:
    return f"{t[0]:+.{digits}f} [{t[1]:+.{digits}f}, {t[2]:+.{digits}f}]"


@dataclass(frozen=True)
class Leg:
    eid: int
    p: float
    odds: float
    y: int
    p_price: float


def _diff(a: Sequence[float], b: Sequence[float]) -> list[float]:
    return [x - y for x, y in zip(a, b, strict=True)]


def pair_scores(pairs: Sequence[Pair]) -> dict[str, Any]:
    g = [x.eid for x in pairs]
    out: dict[str, Any] = {"pairs": len(pairs), "matches": len(set(g))}
    if not pairs:
        return out
    for name, f in (("brier", brier), ("logloss", logloss)):
        new = [f(x.p_new or 0.0, x.y) for x in pairs]
        cur = [f(x.p_cur, x.y) for x in pairs]
        prc = [f(x.p_price, x.y) for x in pairs]
        out[name] = {
            "new": sum(new) / len(new), "current": sum(cur) / len(cur),
            "price": sum(prc) / len(prc),
            "new_minus_price": boot_mean(g, _diff(new, prc)),
            "new_minus_current": boot_mean(g, _diff(new, cur)),
            "current_minus_price": boot_mean(g, _diff(cur, prc)),
        }
    return out


def leg_sets(pairs: Sequence[Pair], cal_cur: Mapping[str, Any] | None,
             cal_new: Mapping[str, Any] | None) -> dict[str, list[Leg]]:
    """Both sides of every pair as legs, per arm (an arm without a value for
    a leg - no curve - leaves the leg out of that arm)."""
    arms: dict[str, list[Leg]] = {"current_p": [], "model_p": [],
                                  "current_conf": [], "model_conf": []}
    for x in pairs:
        pn = x.p_new if x.p_new is not None else 0.0
        for p_cur, p_new, odds, y, pp in (
                (x.p_cur, pn, x.odds, x.y, x.p_price),
                (x.p_cur_partner, 1.0 - pn, x.odds_partner, 1 - x.y, 1.0 - x.p_price)):
            arms["current_p"].append(Leg(x.eid, p_cur, odds, y, pp))
            arms["model_p"].append(Leg(x.eid, p_new, odds, y, pp))
            cc = (confidence(cal_cur, x.market, p_cur, x.female)
                  if x.market == "handicap_games" else None)
            if cc is not None:
                arms["current_conf"].append(Leg(x.eid, cc, odds, y, pp))
            cn = confidence(cal_new, x.market, p_new, x.female)
            if cn is not None:
                arms["model_conf"].append(Leg(x.eid, cn, odds, y, pp))
    return arms


def band_stats(legs: Sequence[Leg], lo: float, hi: float) -> dict[str, Any]:
    cell = [x for x in legs if lo <= x.p < hi]
    if not cell:
        return {"n": 0}
    g = [x.eid for x in cell]
    printable = [x for x in cell if x.p * x.odds >= 0.90]
    out: dict[str, Any] = {
        "n": len(cell), "matches": len(set(g)),
        "claimed": sum(x.p for x in cell) / len(cell),
        "realised": boot_mean(g, [float(x.y) for x in cell]),
        "gap": boot_mean(g, [x.y - x.p for x in cell]),
        "price_nv": sum(x.p_price for x in cell) / len(cell),
        "gap_vs_price": boot_mean(g, [x.y - x.p_price for x in cell]),
    }
    if printable:
        gp = [x.eid for x in printable]
        out["x_ge_090"] = {
            "n": len(printable), "matches": len(set(gp)),
            "roi": boot_mean(gp, [x.odds - 1.0 if x.y else -1.0 for x in printable]),
            "roi_after_tax": boot_mean(
                gp, [TAX * x.odds - 1.0 if x.y else -1.0 for x in printable]),
        }
    return out


def family_report(pairs: Sequence[Pair], cal_cur: Mapping[str, Any] | None,
                  cal_new: Mapping[str, Any] | None) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for fam in FAMILY_ORDER:
        sel = [x for x in pairs if x.family == fam]
        if not sel:
            continue
        arms = leg_sets(sel, cal_cur, cal_new)
        out[fam] = {
            "days": [min(x.day for x in sel), max(x.day for x in sel)],
            "scores": pair_scores(sel),
            "bands": {arm: {name: band_stats(lg, lo, hi) for name, lo, hi in BANDS}
                      for arm, lg in arms.items()},
        }
    return out


def verdict(fam: Mapping[str, Any]) -> dict[str, str]:
    s = fam["scores"]
    hi_p = s["brier"]["new_minus_price"][2]
    hi_c = s["brier"]["new_minus_current"][2]
    b = fam["bands"]["model_conf"]["p>=0.70"]
    if b.get("n", 0) < MIN_LEGS:
        cal = "za mało nóg"
    else:
        cal = "tak" if b["gap"][2] >= 0 else "nie"
    return {"as_good_as_price": "tak" if hi_p <= NONINFERIORITY_BRIER else "nie",
            "no_overpromise_after_curve": cal,
            "better_than_current": "tak" if hi_c < 0 else "nie"}


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------


def load_history(args: argparse.Namespace) -> list[PointMatch]:
    if args.history_cache and Path(args.history_cache).exists():
        with open(args.history_cache, "rb") as fh:
            data: list[PointMatch] = pickle.load(fh)
        return data
    return load_point_history(args.db)


def replay_lines(replay_db: Path, events: Iterable[PointMatch]
                 ) -> dict[int, tuple[float, float, int]]:
    """event -> (line, current p, y) of the home side's handicap_games row
    whose current p is nearest 0.5 (the replay's subject is the team id)."""
    conn = sqlite3.connect(f"file:{replay_db}?mode=ro", uri=True)
    out: dict[int, tuple[float, float, int]] = {}
    for m in events:
        rows = conn.execute(
            "SELECT line, p_central, outcome FROM sofa_settled_row "
            "WHERE sofascore_event_id = ? AND market = 'handicap_games' "
            "AND subject = ? AND direction = 'OVER' "
            "AND run_date = 'cache-calibration' AND outcome IN ('WIN', 'LOSS')",
            (m.event_id, str(m.home_id))).fetchall()
        if not rows:
            continue
        line, p, outcome = min(rows, key=lambda r: abs(float(r[1]) - 0.5))
        out[m.event_id] = (float(line), float(p), 1 if outcome == "WIN" else 0)
    conn.close()
    return out


def run(args: argparse.Namespace) -> dict[str, Any]:
    history = load_history(args)
    by_id = {m.event_id: m for m in history}
    print(f"history {len(history)}", flush=True)
    # -- the populations ---------------------------------------------------
    lo, hi = _ts(CURVE_FROM), _ts(CURVE_BEFORE)
    window = [m for m in history if lo <= m.ts < hi and m.completed
              and m.best_of != 5 and len(m.sets) >= 2]
    with_serve = [m for m in window if m.home is not None and m.away is not None]
    without = [m for m in window if m.home is None or m.away is None]
    extra = random.Random(SEED_EXTRA).sample(without, min(EXTRA_GAMES, len(without)))
    fitted = {m.event_id: m for m in with_serve + extra}
    hlo, hhi = _ts(HIST_FROM), _ts(HIST_TO) + 86400
    hist_pool = [m for m in window if hlo <= m.ts < hhi]
    replay = replay_lines(args.replay_db, hist_pool)
    hist_events = sorted(replay)
    if len(hist_events) > HIST_MAX:
        hist_events = sorted(random.Random(SEED_HIST).sample(hist_events, HIST_MAX))
    for eid in hist_events:
        fitted.setdefault(eid, by_id[eid])
    print(f"curve matches {len(fitted)}, history test {len(hist_events)} "
          f"(replay rows for {len(replay)})", flush=True)
    pairs, drops = load_pairs(args.db)
    days_used = [d for d in sorted({x.day for x in pairs})
                 if d < HOLDOUT_FROM or (args.holdout and d <= HOLDOUT_TO)]
    pairs = [x for x in pairs if x.day in set(days_used)]
    fixtures = load_fixtures(args.runs_dir)
    wanted = set(fitted) | {x.eid for x in pairs}
    forecasts = walk_forward(history, wanted)
    _JOBS.clear()
    for eid in wanted:
        if eid in forecasts and eid in by_id:
            _JOBS[eid] = (by_id[eid], forecasts[eid])
    # -- curves + history test --------------------------------------------
    every: Counts = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    women: Counts = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    hist_set = set(hist_events)
    tasks = []
    for eid in sorted(fitted):
        if eid not in _JOBS:
            continue
        test: tuple[tuple[float, int], ...] = ()
        if eid in hist_set:
            test = ((replay[eid][0], 0),)
        tasks.append((eid, test))
    hist_rows: list[dict[str, Any]] = []
    n_rows = 0
    cache = args.out_dir / "tennis_curve_pass.pkl"
    if cache.exists():
        # the curve pass of an earlier run (same code, same history): reused
        with cache.open("rb") as fh:
            every_d, women_d, hist_rows, n_rows = pickle.load(fh)
        for src, dst in ((every_d, every), (women_d, women)):
            for mk, cells in src.items():
                for b, kn in cells.items():
                    dst[mk][b] = list(kn)
        tasks_to_run: list[tuple[int, tuple[tuple[float, int], ...]]] = []
    else:
        tasks_to_run = tasks
    with _pool(args.workers) as pool:
        for i, res in enumerate(pool.map(curve_job, tasks_to_run, chunksize=64)):
            for market, p, y in res["rows"]:
                b = bucket_of(min(max(p, 0.0), 1.0))
                every[market][b][0] += y
                every[market][b][1] += 1
                if res["female"]:
                    women[market][b][0] += y
                    women[market][b][1] += 1
            n_rows += len(res["rows"])
            for _line, _side, p in res["test"]:
                if p is None:
                    continue
                line, p_cur, y = replay[res["eid"]]
                hist_rows.append({"eid": res["eid"], "line": line, "p_cur": p_cur,
                                  "p_new": p, "y": y})
            if (i + 1) % 5000 == 0:
                print(f"{i + 1} / {len(tasks)} matches, {n_rows} rows", flush=True)
    if tasks_to_run:
        with cache.open("wb") as fh:
            pickle.dump(({k: dict(v) for k, v in every.items()},
                         {k: dict(v) for k, v in women.items()}, hist_rows, n_rows), fh)
    cal_new: dict[str, Any] = {
        **curve_sections(every),
        "by_class": {"tennis_women": curve_sections(women)},
        "fitted_from": {"window": [CURVE_FROM, CURVE_BEFORE],
                        "matches": len(tasks), "rows": n_rows,
                        "lines": f"half lines with p in [{LINE_P_LO}, {LINE_P_HI}], "
                                 "both sides",
                        "estimator": f"tennis_point_model, {SIMS} sims, "
                                     "seed = event id"},
    }
    (args.out_dir / "tennis_handicap_curves.json").write_text(
        json.dumps(cal_new, indent=1), encoding="utf-8")
    hist = history_report(hist_rows)
    # -- Superbet ----------------------------------------------------------
    priced: list[Pair] = []
    sb_events = sorted({x.eid for x in pairs if x.eid in _JOBS})
    table: dict[int, Any] = {}
    with _pool(args.workers) as pool:
        for eid, ps in pool.map(price_job, sb_events, chunksize=16):
            table[eid] = ps
    for x in pairs:
        m = by_id.get(x.eid)
        if m is None or x.eid not in table:
            drops["not_in_history"] = drops.get("not_in_history", 0) + 1
            continue
        if not m.completed or m.best_of == 5:
            drops["retired_or_bo5"] = drops.get("retired_or_bo5", 0) + 1
            continue
        fx = fixtures.get(x.eid)
        swap = orient(m, fx)
        if swap is None or fx is None:
            drops["sides_disagree"] = drops.get("sides_disagree", 0) + 1
            continue
        side = side_of(x.subject, str(fx.get("home_name") or ""),
                       str(fx.get("away_name") or ""))
        other = side_of(x.partner, str(fx.get("home_name") or ""),
                        str(fx.get("away_name") or ""))
        if side is None or other is None or side == other:
            drops["subject_unmapped"] = drops.get("subject_unmapped", 0) + 1
            continue
        hist_side = 1 - side if swap else side
        p = table[x.eid].get((x.market, hist_side, x.line))
        if p is None:
            drops["not_priced"] = drops.get("not_priced", 0) + 1
            continue
        # the model's own record of the result agrees with Superbet's grade?
        margin = actual_margin(m, x.market, hist_side)
        if margin is not None and (margin + x.line > 0) != bool(x.y):
            drops["grade_disagrees_with_history"] = drops.get(
                "grade_disagrees_with_history", 0) + 1
            continue
        priced.append(replace(x, side=hist_side, female=m.female, p_new=p))
    cal_cur = json.loads(Path(args.calibration).read_text(encoding="utf-8"))
    dev = [x for x in priced if x.day < HOLDOUT_FROM]
    hold = [x for x in priced if x.day >= HOLDOUT_FROM]
    out: dict[str, Any] = {
        "pairs_loaded": len(pairs), "drops": drops, "history": hist,
        "curves": {"matches": len(tasks), "rows": n_rows},
        "dev": family_report(dev, cal_cur, cal_new),
    }
    out["dev_verdicts"] = {f: verdict(r) for f, r in out["dev"].items()}
    if args.holdout:
        out["holdout"] = family_report(hold, cal_cur, cal_new)
        out["holdout_verdicts"] = {f: verdict(r) for f, r in out["holdout"].items()}
    with (args.out_dir / ("tennis_pairs_holdout.jsonl" if args.holdout
                          else "tennis_pairs_dev.jsonl")).open("w") as fh:
        for x in priced:
            fh.write(json.dumps({**x.__dict__, "p_price": x.p_price}) + "\n")
    return out


def history_report(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"lines": 0}
    g = [r["eid"] for r in rows]
    out: dict[str, Any] = {"lines": len(rows), "matches": len(set(g))}
    for name, f in (("brier", brier), ("logloss", logloss)):
        new = [f(r["p_new"], r["y"]) for r in rows]
        cur = [f(r["p_cur"], r["y"]) for r in rows]
        out[name] = {"new": sum(new) / len(new), "current": sum(cur) / len(cur),
                     "new_minus_current": boot_mean(
                         g, [a - b for a, b in zip(new, cur, strict=True)])}
    for arm in ("p_new", "p_cur"):
        legs = [Leg(r["eid"], r[arm], 2.0, r["y"], 0.5) for r in rows] + [
            Leg(r["eid"], 1.0 - r[arm], 2.0, 1 - r["y"], 0.5) for r in rows]
        out[f"bands_{arm}"] = {name: {k: v for k, v in band_stats(legs, lo, hi).items()
                                      if k not in ("x_ge_090", "price_nv",
                                                   "gap_vs_price")}
                               for name, lo, hi in BANDS}
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    ap.add_argument("--replay-db", type=Path, default=DEFAULT_REPLAY_DB)
    ap.add_argument("--calibration", type=Path, default=DEFAULT_CAL)
    ap.add_argument("--runs-dir", type=Path, default=_REPO / "runs" / "sofa")
    ap.add_argument("--history-cache", default=None)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--holdout", action="store_true")
    ap.add_argument("--workers", type=int, default=2)
    args = ap.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    res = run(args)
    name = "tennis_holdout.json" if args.holdout else "tennis_dev.json"
    (args.out_dir / name).write_text(json.dumps(res, indent=1), encoding="utf-8")
    key = "holdout_verdicts" if args.holdout else "dev_verdicts"
    print(json.dumps({"history": {k: res["history"].get(k) for k in ("lines", "brier")},
                      key: res.get(key)}, indent=1), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
