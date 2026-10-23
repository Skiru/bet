#!/usr/bin/env python3
"""C3 - tennis OUTCOME markets from the statistics: evidence, not a price.

Read-only evidence (a ``measure_*`` script): nothing here writes a config, a
curve, a run artifact or a database. The question (PLAN_NOC_2026-10-12, C3):
can the as-of tennis rating SHEET already prices with
(``tennis_rating.AsOfRating``, scoped tier x gender table and tier start,
epochs.TENNIS_SCOPED_TABLE_FROM_UTC) price the outcome markets Superbet posts
and sofa leaves unmapped -

    match_winner   the home player wins the match           (p_home)
    set1_winner    the home player wins set 1               (neighbours)
    set2_winner    the home player wins set 2               (neighbours;
                   added 2026-10-14 - Superbet's "X. set - zwycięzca")
    deciding_set   a third set is played = exact sets is 3 (neighbours)
    set_score      2-0 / 2-1 / 1-2 / 0-2 from the home side (neighbours)

- and does it carry information beyond the class's base rate, as of each match?

Method. Walk forward over the cached singles history
(``tennis_rating.load_history``, the sheet's own population): every test match
is forecast from the model at its UTC day start (``AsOfRating.model_at(day)``,
as run_sheet and calibrate_from_cache build one model per day), so ratings and
the neighbour table hold only matches before that day. The base rate is the
match's class (tier x gender) rate over the same as-of history (Laplace).
A second, analytic reading of the set markets - sets i.i.d. with the set
probability ``s`` solving ``p_home = s^2 (3 - 2 s)`` - is the yardstick the
neighbour read must beat to be worth its 600 rows.

Population. Completed best-of-three singles (the neighbour table's own rule,
``tennis_rating._outcomes``: best-of-five and retirements are skipped - the
sheet does not price best-of-five and Superbet refunds a retirement), both
players rated (``MIN_RATED``), team cups and exhibitions out
(``confidence.match_class`` == CLASS_TENNIS_TEAM_CUP; they still feed the
ratings, as in the sheet).

Two coefficient variants:

  live   config/tennis_rating.json as SHEET reads it (V5: ``lp_t``,
         ``tier_start``). It was fitted on history to 2026-10-01, so its 9
         numbers a tier saw the test window - the replay's known look-ahead
         (calibrate_from_cache).
  clean  ``tier_start`` and the coefficients refitted on history strictly
         before the test window (``fit_tier_start`` + the Newton logistic of
         ``fit_coefficients``, here in numpy): no look-ahead at all.

Probabilities read off 600 neighbours are smoothed (k + 0.5) / (n + K/2) so
an empty cell never scores an infinite log-loss. Confidence intervals are a
match bootstrap (one row per match and market, so a resample of matches).

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_tennis_outcome_model.py \\
        [--db data/refit_2026-10-12/sofa_replay.db] [--test-from 2026-06-09] \\
        [--test-to 2026-10-07] [--variants live,clean] [--boot 1000] \\
        [--out-dir data/refit_2026-10-12/c3]

Writes ``rows_<variant>.csv``, ``results.json`` and ``report.md`` into
``--out-dir``. Exit 0 OK, 2 on a failure.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import time
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import tennis_rating as tr  # noqa: E402
from bet.sofa.confidence import CLASS_TENNIS_TEAM_CUP, match_class  # noqa: E402

FloatArr = npt.NDArray[np.float64]

DEFAULT_DB = "data/refit_2026-10-12/sofa_replay.db"
DEFAULT_OUT = "data/refit_2026-10-12/c3"
MARKETS: tuple[str, ...] = (
    "match_winner", "set1_winner", "set2_winner", "deciding_set", "set_score")
BINARY = ("match_winner", "set1_winner", "set2_winner", "deciding_set")
SCORES: tuple[str, ...] = ("2-0", "2-1", "1-2", "0-2")
BIN_EDGES: tuple[float, ...] = (0.5, 0.6, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 1.0001)
SCORE_EDGES: tuple[float, ...] = (0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 1.0001)
PRINT_FLOOR = 0.70
# The wiring bar (2026-10-14): at p >= PRINT_FLOOR |realised - p| <= 2 pp
# with n >= 300.
CAL_GAP_PP = 2.0
CAL_MIN_N = 300
EPS = 1e-6


# ---------------------------------------------------------------- pure parts


def smoothed(k: int, n: int, classes: int) -> float:
    """(k + 0.5) / (n + classes / 2): a neighbour share that is never 0 or 1."""
    return (k + 0.5) / (n + 0.5 * classes)


def set_prob_from_match(p_match: float) -> float:
    """The set probability ``s`` with s^2 (3 - 2 s) = p_match (best of three,
    sets i.i.d.); monotone on [0, 1], solved by bisection."""
    lo, hi = 0.0, 1.0
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if mid * mid * (3.0 - 2.0 * mid) < p_match:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def iid_scores(p_match: float) -> tuple[float, float, float, float]:
    """P(2-0, 2-1, 1-2, 0-2) from the home side, sets i.i.d."""
    s = set_prob_from_match(p_match)
    q = 1.0 - s
    return s * s, 2.0 * s * s * q, 2.0 * q * q * s, q * q


def score_code(sets: Sequence[tuple[int, int]]) -> int:
    """Index into SCORES of a completed best-of-three, home side."""
    home = sum(1 for a, b in sets if a > b)
    away = sum(1 for a, b in sets if b > a)
    return {(2, 0): 0, (2, 1): 1, (1, 2): 2, (0, 2): 3}[(home, away)]


def is_team_cup(text: str) -> bool:
    return match_class("tennis", text) == CLASS_TENNIS_TEAM_CUP


def class_label(tier: str, female: bool) -> str:
    return f"{tier}-{'W' if female else 'M'}"


def ll_binary(p: FloatArr, y: FloatArr) -> FloatArr:
    q = np.clip(p, EPS, 1.0 - EPS)
    out: FloatArr = -(y * np.log(q) + (1.0 - y) * np.log(1.0 - q))
    return out


def ll_multi(p: FloatArr, code: npt.NDArray[np.int64]) -> FloatArr:
    """p: (n, K) rows summing to one; code: the realised class."""
    picked = p[np.arange(len(code)), code]
    out: FloatArr = -np.log(np.clip(picked, EPS, 1.0))
    return out


def boot_ci(
    delta: FloatArr, boot: int, seed: int = 20261012
) -> tuple[float, float]:
    """95% match-bootstrap interval of mean(delta) (one row per match)."""
    n = len(delta)
    if n == 0:
        return math.nan, math.nan
    rng = np.random.default_rng(seed)
    means = np.empty(boot)
    for b in range(boot):
        means[b] = delta[rng.integers(0, n, n)].mean()
    lo, hi = np.percentile(means, [2.5, 97.5])
    return float(lo), float(hi)


def wilson_lower(k: float, n: int, z: float = 1.96) -> float:
    """Wilson 95% lower bound of a realised rate k / n."""
    if n <= 0:
        return math.nan
    p = k / n
    den = 1.0 + z * z / n
    centre = p + z * z / (2 * n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (centre - half) / den


def bucket_table(
    p: FloatArr, y: FloatArr, edges: Sequence[float]
) -> list[dict[str, float]]:
    """n, mean p, realised, its Wilson lower bound and gap per [edge, next
    edge)."""
    out: list[dict[str, float]] = []
    for lo, hi in zip(edges[:-1], edges[1:], strict=True):
        m = (p >= lo) & (p < hi)
        n = int(m.sum())
        if n == 0:
            continue
        mp, ry = float(p[m].mean()), float(y[m].mean())
        out.append({"lo": lo, "hi": min(hi, 1.0), "n": n, "p": mp,
                    "realised": ry, "wilson_lo": wilson_lower(ry * n, n),
                    "gap_pp": 100.0 * (ry - mp)})
    return out


def favoured(p: FloatArr, y: FloatArr) -> tuple[FloatArr, FloatArr]:
    """Each binary row as its favoured selection: (max(p, 1-p), its outcome)."""
    flip = p < 0.5
    pf: FloatArr = np.where(flip, 1.0 - p, p)
    yf: FloatArr = np.where(flip, 1.0 - y, y)
    return pf, yf


@dataclass
class BaseRates:
    """As-of class counts: home wins, home set-1 wins, third sets, scores."""

    n: int = 0
    home: int = 0
    set1: int = 0
    set2: int = 0
    third: int = 0
    scores: tuple[int, int, int, int] = (0, 0, 0, 0)

    def add(self, home_won: bool, set1_home: bool, code: int,
            set2_home: bool = False) -> None:
        self.n += 1
        self.home += home_won
        self.set1 += set1_home
        self.set2 += set2_home
        self.third += code in (1, 2)
        s = list(self.scores)
        s[code] += 1
        self.scores = (s[0], s[1], s[2], s[3])

    def rates(self) -> dict[str, Any]:
        return {
            "match_winner": smoothed(self.home, self.n, 2),
            "set1_winner": smoothed(self.set1, self.n, 2),
            "set2_winner": smoothed(self.set2, self.n, 2),
            "deciding_set": smoothed(self.third, self.n, 2),
            "set_score": [smoothed(k, self.n, 4) for k in self.scores],
        }


def fit_logistic_np(x: FloatArr, y: FloatArr) -> list[float]:
    """tennis_rating.fit_logistic (Newton, intercept, 1e-6 on the diagonal),
    vectorised: the same fixed point, minutes instead of an hour."""
    xs = np.hstack([np.ones((len(x), 1)), x])
    w = np.zeros(xs.shape[1])
    for _ in range(30):
        p = 1.0 / (1.0 + np.exp(-(xs @ w)))
        grad = xs.T @ (y - p)
        hess = (xs * (p * (1.0 - p))[:, None]).T @ xs
        hess += 1e-6 * np.eye(len(w))
        step = np.linalg.solve(hess, grad)
        w = w + step
        if np.max(np.abs(step)) < 1e-9:
            break
    return [float(v) for v in w]


# ---------------------------------------------------------------- history


def load(db: str) -> tuple[list[tr.TennisResult], dict[int, tuple[str, str]]]:
    """load_history, plus each parsed event's (category name, full text)."""
    meta: dict[int, tuple[str, str]] = {}
    original = tr.parse_event

    def capture(event: Mapping[str, Any], *,
                score_winner: bool = False) -> tr.TennisResult | None:
        r = original(event, score_winner=score_winner)
        if r is not None:
            t = event.get("tournament") or {}
            cat = str((t.get("category") or {}).get("name", ""))
            ut = (t.get("uniqueTournament") or {}).get("name", "")
            meta[r.event_id] = (cat, f"{cat} | {t.get('name', '')} | {ut}")
        return r

    tr.parse_event = capture
    try:
        history = tr.load_history(db)
    finally:
        tr.parse_event = original
    return history, meta


def clean_config(
    history: Sequence[tr.TennisResult], cut_ts: int
) -> tuple[dict[str, list[float]], dict[str, float]]:
    """V5 coefficients and tier start from matches before ``cut_ts`` only."""
    tier_start = tr.fit_tier_start(history, cut_ts)
    _, rated = tr.replay(history, cut_ts, tier_start)
    names = tr.V5_FEATURES
    by: dict[str, tuple[list[list[float]], list[float]]] = defaultdict(
        lambda: ([], []))
    for r, f in rated:
        if len(r.sets) <= 3:
            by[r.tier][0].append([f[k] for k in names])
            by[r.tier][1].append(1.0 if r.home_won else 0.0)
    coefficients = {
        tier: fit_logistic_np(np.array(xs, dtype=float), np.array(ys, dtype=float))
        for tier, (xs, ys) in by.items()
    }
    return coefficients, tier_start


# ---------------------------------------------------------------- the walk


def walk(
    history: Sequence[tr.TennisResult],
    meta: Mapping[int, tuple[str, str]],
    coefficients: Mapping[str, Sequence[float]],
    names: Sequence[str],
    tier_start: Mapping[str, float] | None,
    test_from: int,
    test_to: int,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    rating = tr.AsOfRating(history, coefficients, names, True, tier_start)
    base: dict[str, BaseRates] = defaultdict(BaseRates)
    skips: dict[str, int] = defaultdict(int)
    rows: list[dict[str, Any]] = []
    j = 0  # base-rate pointer: matches before the current day
    for r in history:
        if r.ts < test_from:
            continue
        if r.ts >= test_to:
            break
        day = r.ts - r.ts % 86400
        while j < len(history) and history[j].ts < day:
            h = history[j]
            j += 1
            text = meta.get(h.event_id, ("", ""))[1]
            if (h.completed and len(h.sets) <= 3
                    and max(sum(a > b for a, b in h.sets),
                            sum(b > a for a, b in h.sets)) == 2
                    and not is_team_cup(text)):
                base[class_label(h.tier, h.female)].add(
                    h.home_won, h.sets[0][0] > h.sets[0][1], score_code(h.sets),
                    h.sets[1][0] > h.sets[1][1])
        cat, text = meta.get(r.event_id, ("", ""))
        if is_team_cup(text):
            skips["team_cup"] += 1
            continue
        if not r.completed:
            skips["not_completed"] += 1
            continue
        won = max(sum(a > b for a, b in r.sets), sum(b > a for a, b in r.sets))
        if won != 2 or len(r.sets) > 3:
            skips["best_of_five"] += 1
            continue
        model = rating.model_at(day)
        fc = model.forecast(r.home_id, r.away_id, cat, r.surface,
                            datetime.fromtimestamp(r.ts, UTC))
        if fc is None or not fc.neighbours_home:
            skips["unrated"] += 1
            continue
        pool = fc.neighbours_home
        n = len(pool)
        k_set1 = sum(1 for o in pool if o.set1[0] > o.set1[1])
        k_set2 = sum(1 for o in pool if o.set2[0] > o.set2[1])
        k_third = sum(1 for o in pool if o.sets == 3)
        ks = [0, 0, 0, 0]
        for o in pool:
            won_it = _won_match(o)
            if o.sets == 2:
                ks[0 if won_it else 3] += 1
            else:
                ks[1 if won_it else 2] += 1
        cls = class_label(r.tier, r.female)
        br = base[cls].rates()
        iid = iid_scores(fc.p_home)
        code = score_code(r.sets)
        rows.append({
            "event_id": r.event_id, "ts": r.ts, "cls": cls,
            "scope": fc.table_scope, "base_n": base[cls].n,
            "y_match": int(r.home_won), "y_set1": int(r.sets[0][0] > r.sets[0][1]),
            "y_set2": int(r.sets[1][0] > r.sets[1][1]),
            "y_third": int(len(r.sets) == 3), "y_score": code,
            "p_match": fc.p_home,
            "p_match_nb": smoothed(sum(1 for o in pool if _won_match(o)), n, 2),
            "p_set1": smoothed(k_set1, n, 2),
            "p_set2": smoothed(k_set2, n, 2),
            "p_third": smoothed(k_third, n, 2),
            **{f"p_s{i}": smoothed(ks[i], n, 4) for i in range(4)},
            "iid_set1": set_prob_from_match(fc.p_home),
            "iid_set2": set_prob_from_match(fc.p_home),
            "iid_third": iid[1] + iid[2],
            **{f"iid_s{i}": iid[i] for i in range(4)},
            "b_match": br["match_winner"], "b_set1": br["set1_winner"],
            "b_set2": br["set2_winner"],
            "b_third": br["deciding_set"],
            **{f"b_s{i}": br["set_score"][i] for i in range(4)},
        })
    return rows, dict(skips)


def _won_match(o: tr.Outcome) -> bool:
    """A neighbour outcome's player won the match: two sets of three."""
    won = (o.set1[0] > o.set1[1]) + (o.set2[0] > o.set2[1])
    if o.sets == 2:
        return won == 2
    # A three-setter is decided by set three, whose games are the match's
    # minus sets one and two (a match tiebreak is one game, tennis_score).
    third_for = o.games_for - o.set1[0] - o.set2[0]
    third_against = o.games_against - o.set1[1] - o.set2[1]
    return third_for > third_against


# ---------------------------------------------------------------- scoring


def score_rows(rows: Sequence[Mapping[str, Any]], boot: int) -> dict[str, Any]:
    """Per market: n, log-loss (model / base / i.i.d.), bootstrap CI of the
    differences, calibration buckets, share at p >= PRINT_FLOOR."""
    out: dict[str, Any] = {"n": len(rows)}
    if not rows:
        return out

    def col(name: str) -> FloatArr:
        return np.array([float(r[name]) for r in rows])

    spec = {
        "match_winner": ("y_match", "p_match", "b_match", None),
        "set1_winner": ("y_set1", "p_set1", "b_set1", "iid_set1"),
        "set2_winner": ("y_set2", "p_set2", "b_set2", "iid_set2"),
        "deciding_set": ("y_third", "p_third", "b_third", "iid_third"),
    }
    for market, (yk, pk, bk, ik) in spec.items():
        y, p, b = col(yk), col(pk), col(bk)
        llm, llb = ll_binary(p, y), ll_binary(b, y)
        res: dict[str, Any] = {
            "ll_model": float(llm.mean()), "ll_base": float(llb.mean()),
            "d_vs_base": float((llm - llb).mean()),
            "ci_vs_base": boot_ci(llm - llb, boot),
            "base_rate_realised": float(y.mean()),
        }
        if market == "match_winner":
            lln = ll_binary(col("p_match_nb"), y)
            res["ll_nb_share"] = float(lln.mean())
        if ik is not None:
            lli = ll_binary(col(ik), y)
            res["ll_iid"] = float(lli.mean())
            res["d_vs_iid"] = float((llm - lli).mean())
            res["ci_vs_iid"] = boot_ci(llm - lli, boot)
        pf, yf = favoured(p, y)
        res["buckets"] = bucket_table(pf, yf, BIN_EDGES)
        hi = pf >= PRINT_FLOOR
        res["share_ge_070"] = float(hi.mean())
        res["n_ge_070"] = int(hi.sum())
        res["p_ge_070"] = float(pf[hi].mean()) if hi.any() else math.nan
        res["realised_ge_070"] = float(yf[hi].mean()) if hi.any() else math.nan
        res.update(_verdict(pf, yf))
        out[market] = res
    code = np.array([int(r["y_score"]) for r in rows], dtype=np.int64)
    pm = np.stack([col(f"p_s{i}") for i in range(4)], axis=1)
    pm = pm / pm.sum(axis=1, keepdims=True)
    pb = np.stack([col(f"b_s{i}") for i in range(4)], axis=1)
    pi = np.stack([col(f"iid_s{i}") for i in range(4)], axis=1)
    llm, llb, lli = ll_multi(pm, code), ll_multi(pb, code), ll_multi(pi, code)
    flat_p = pm.reshape(-1)
    flat_y = (np.arange(4)[None, :] == code[:, None]).astype(float).reshape(-1)
    hi = flat_p >= PRINT_FLOOR
    out["set_score"] = {
        "ll_model": float(llm.mean()), "ll_base": float(llb.mean()),
        "ll_iid": float(lli.mean()),
        "d_vs_base": float((llm - llb).mean()), "ci_vs_base": boot_ci(llm - llb, boot),
        "d_vs_iid": float((llm - lli).mean()), "ci_vs_iid": boot_ci(llm - lli, boot),
        "realised_shares": [float((code == i).mean()) for i in range(4)],
        "buckets": bucket_table(flat_p, flat_y, SCORE_EDGES),
        "share_ge_070": float(hi.mean()), "n_ge_070": int(hi.sum()),
        "p_ge_070": float(flat_p[hi].mean()) if hi.any() else math.nan,
        "realised_ge_070": float(flat_y[hi].mean()) if hi.any() else math.nan,
        **_verdict(flat_p, flat_y),
    }
    return out


def _verdict(p: FloatArr, y: FloatArr) -> dict[str, Any]:
    """The wiring bar at p >= PRINT_FLOOR: Wilson lower bound of the
    realised rate and whether |realised - p| <= CAL_GAP_PP with n >=
    CAL_MIN_N."""
    hi = p >= PRINT_FLOOR
    n = int(hi.sum())
    if n == 0:
        return {"wilson_lo_ge_070": math.nan, "gap_ge_070_pp": math.nan,
                "calibrated": False}
    k = float(y[hi].sum())
    gap = 100.0 * (k / n - float(p[hi].mean()))
    return {"wilson_lo_ge_070": wilson_lower(k, n), "gap_ge_070_pp": gap,
            "calibrated": bool(n >= CAL_MIN_N and abs(gap) <= CAL_GAP_PP)}


# ---------------------------------------------------------------- report


def _ci(c: Sequence[float]) -> str:
    return f"[{1e4 * c[0]:+.0f}, {1e4 * c[1]:+.0f}]"


def render(results: Mapping[str, Any]) -> str:
    lines = ["# C3 - tennis outcome markets from the rating (measurement)", ""]
    lines.append(f"Test window {results['test_from']} .. {results['test_to']} "
                 f"(UTC day cut). Log-loss differences in 1e-4 nats; negative = "
                 f"model better. CI = match bootstrap 95% ({results['boot']}).")
    for variant, vres in results["variants"].items():
        lines += ["", f"## Variant `{variant}`", "",
                  f"Skips: {vres['skips']}", ""]
        lines.append("| class | market | n | LL model | LL base | d vs base [CI] "
                     "| d vs iid [CI] | share p>=.70 | p / realised at >=.70 "
                     "| Wilson lo | bar |")
        lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
        for cls, cres in vres["classes"].items():
            for market in MARKETS:
                m = cres.get(market)
                if m is None:
                    continue
                iid = (f"{1e4 * m['d_vs_iid']:+.0f} {_ci(m['ci_vs_iid'])}"
                       if "d_vs_iid" in m else "-")
                lines.append(
                    f"| {cls} | {market} | {cres['n']} | {m['ll_model']:.4f} | "
                    f"{m['ll_base']:.4f} | {1e4 * m['d_vs_base']:+.0f} "
                    f"{_ci(m['ci_vs_base'])} | {iid} | "
                    f"{100 * m['share_ge_070']:.1f}% | "
                    f"{m['p_ge_070']:.3f} / {m['realised_ge_070']:.3f} | "
                    f"{m['wilson_lo_ge_070']:.3f} | "
                    f"{'PASS' if m['calibrated'] else 'no'} |")
        lines += ["", "### Calibration (all classes, favoured selection)", ""]
        allres = vres["classes"]["ALL"]
        for market in MARKETS:
            lines += [f"**{market}**", "",
                      "| p bucket | n | mean p | realised | Wilson lo | gap pp |",
                      "|---|---|---|---|---|---|"]
            for b in allres[market]["buckets"]:
                lines.append(f"| {b['lo']:.2f}-{b['hi']:.2f} | {b['n']} | "
                             f"{b['p']:.3f} | {b['realised']:.3f} | "
                             f"{b['wilson_lo']:.3f} | {b['gap_pp']:+.1f} |")
            lines.append("")
    return "\n".join(lines) + "\n"


def _day_ts(day: str) -> int:
    return int(datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=UTC).timestamp())


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--test-from", default="2026-06-09")
    ap.add_argument("--test-to", default="2026-10-07")
    ap.add_argument("--variants", default="live,clean")
    ap.add_argument("--boot", type=int, default=1000)
    ap.add_argument("--out-dir", default=DEFAULT_OUT)
    args = ap.parse_args(argv)
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    test_from, test_to = _day_ts(args.test_from), _day_ts(args.test_to)
    history, meta = load(args.db)
    print(f"history {len(history)} matches ({time.time() - t0:.0f}s)", flush=True)
    results: dict[str, Any] = {
        "db": args.db, "test_from": args.test_from, "test_to": args.test_to,
        "boot": args.boot, "variants": {},
    }
    for variant in args.variants.split(","):
        if variant == "live":
            loaded = tr.load_coefficients()
            if loaded is None:
                print("no config/tennis_rating.json", file=sys.stderr)
                return 2
            coefficients, cfg = loaded
            names: Sequence[str] = cfg["features"]
            tier_start = cfg.get("tier_start")
        elif variant == "clean":
            coefficients, tier_start = clean_config(history, test_from)
            names = tr.V5_FEATURES
        else:
            print(f"unknown variant {variant}", file=sys.stderr)
            return 2
        rows, skips = walk(history, meta, coefficients, names, tier_start,
                           test_from, test_to)
        print(f"{variant}: {len(rows)} rows, skips {skips} "
              f"({time.time() - t0:.0f}s)", flush=True)
        with (out / f"rows_{variant}.csv").open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        by: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for r in rows:
            by[r["cls"]].append(r)
        classes = {"ALL": score_rows(rows, args.boot)}
        for cls in sorted(by):
            classes[cls] = score_rows(by[cls], args.boot)
        results["variants"][variant] = {
            "skips": skips, "coefficients": coefficients,
            "tier_start": tier_start, "features": list(names), "classes": classes,
        }
    (out / "results.json").write_text(json.dumps(results, indent=1))
    (out / "report.md").write_text(render(results))
    print(f"wrote {out} ({time.time() - t0:.0f}s)", flush=True)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"FAILED: {exc!r}", file=sys.stderr)
        raise SystemExit(2) from exc
