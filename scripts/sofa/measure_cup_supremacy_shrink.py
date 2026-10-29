#!/usr/bin/env python3
"""Measure a knockout shrink of the football rating's goal supremacy.

2026-10-29 (model-state.md (d)): in domestic cup ties priced across leagues
(KNOCKOUT + LINKED_BY_STRENGTH) the favourite realised -0.46 [-0.58, -0.33]
goals of margin and -0.56 of total below the rating at a predicted supremacy
>= 2 (N 2,008 from 2025-07-01) - the rating too steep there, not too shallow.
Candidate: in a knockout tie the favourite's expected goals become

    underdog + T + k x (s - T)    where s = favourite - underdog > T

(the underdog's unchanged: the margin and the total were over-predicted by
about the same amount). T and k are fitted on --fit-to (NB log-likelihood of
both sides' goals, grid) and scored out of sample on --fit-to .. --cut:
goals_for per side, goals_total, 1X2 and the favourite -2.5 handicap, NB
score grid (football_result, r = its nb_r), candidate minus rating, 95%
interval from resampling matches; domestic and international club cups
(config/sofa_cup_strength.json `competitions`) apart, never pooled.

The rows are the rating's goals_for centres (FootballForecast.centre) as
SHEET's book stands before each match: the parsed history of --db-path (a
COPY - the pickle is written next to it), the shared-league link, the cup
league strength; every KNOCKOUT match (FootballResult.knockout,
comparability.is_knockout) priced LINKED_BY_STRENGTH before its kick-off
group is fed. Read only; writes only --json-out.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_cup_supremacy_shrink.py \\
        --db-path data/refit_2026-10-30/sofa.db --json-out <f>
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

from bet.sofa import football_rating as fr
from bet.sofa.cup_strength import load as load_cup
from bet.sofa.football_result import count_pmf, load_config, market_probs, score_grid

METRIC = "goals_for"
Arr = npt.NDArray[np.float64]
_lgamma = np.vectorize(math.lgamma)


def _ts(day: str) -> int:
    return int(datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=UTC).timestamp())


def knockout_rows(history: list[fr.FootballResult], from_ts: int, cut_ts: int,
                  intl: frozenset[int], eta: dict[str, float]
                  ) -> list[dict[str, float]]:
    book = fr.RatingBook(shared_league_link=True)
    book.cup_competitions = intl
    book.cup_eta = dict(eta)
    rows: list[dict[str, float]] = []
    group: list[fr.FootballResult] = []

    def price(r: fr.FootballResult) -> None:
        if r.women or r.home_reserve or r.away_reserve or METRIC not in r.values:
            return
        status, lf = book.link(r.home_id, r.away_id, METRIC, r.competition_id)
        if status != fr.LINKED_BY_STRENGTH:
            return
        fc = fr.FootballForecast(book, r.competition_id, r.home_id, r.away_id)
        h, a = fc.centre(METRIC, "side_a"), fc.centre(METRIC, "side_b")
        if h is None or a is None:
            return
        x, y = r.values[METRIC]
        rows.append({"ts": r.ts, "eid": r.event_id, "comp": r.competition_id,
                     "intl": float(r.competition_id in intl), "lf": lf,
                     "lh": h[0], "la": a[0], "x": x, "y": y})

    def flush() -> None:
        for g in group:
            if from_ts <= g.ts < cut_ts and g.knockout:
                price(g)
        for g in group:
            book.update(g)
        group.clear()

    for r in history:
        if r.ts >= cut_ts:
            break
        if group and r.ts != group[0].ts:
            flush()
        group.append(r)
    flush()
    return rows


def nb_ll(y: Arr, mu: Arr, r: float) -> Arr:
    p = r / (r + mu)
    out = (_lgamma(y + r) - math.lgamma(r) - _lgamma(y + 1)
           + r * np.log(p) + y * np.log1p(-p))
    return np.asarray(out, dtype=float)


def shrink(lh: Arr, la: Arr, t: float, k: float) -> tuple[Arr, Arr]:
    fav_home = lh >= la
    lf = np.where(fav_home, lh, la)
    ld = np.where(fav_home, la, lh)
    s = lf - ld
    lf2 = ld + np.where(s > t, t + k * (s - t), s)
    return np.where(fav_home, lf2, ld), np.where(fav_home, ld, lf2)


def boot(v: Arr, n_boot: int = 2000, seed: int = 7) -> list[float]:
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(v), size=(n_boot, len(v)))
    means = v[idx].mean(axis=1)
    return [round(float(v.mean()), 5), round(float(np.quantile(means, 0.025)), 5),
            round(float(np.quantile(means, 0.975)), 5), len(v)]


def _cols(rows: Sequence[dict[str, float]]) -> tuple[Arr, Arr, Arr, Arr]:
    return tuple(np.array([r[k] for r in rows], dtype=float)  # type: ignore[return-value]
                 for k in ("lh", "la", "x", "y"))


def fit(rows: Sequence[dict[str, float]], r_nb: float) -> tuple[float, float, float]:
    """(log-likelihood gain, T, k) of the best grid point; T = inf: none."""
    lh, la, x, y = _cols(rows)
    base = float((nb_ll(x, lh, r_nb) + nb_ll(y, la, r_nb)).sum())
    best = (0.0, math.inf, 1.0)
    for t in np.arange(0.5, 4.01, 0.25):
        for k in np.arange(0.0, 1.001, 0.05):
            h, a = shrink(lh, la, float(t), float(k))
            gain = float((nb_ll(x, h, r_nb) + nb_ll(y, a, r_nb)).sum()) - base
            if gain > best[0]:
                best = (gain, float(t), float(k))
    return best


def score(rows: Sequence[dict[str, float]], t: float, k: float, r_nb: float
          ) -> dict[str, Any]:
    lh, la, x, y = _cols(rows)
    h, a = shrink(lh, la, t, k)
    s = np.abs(lh - la)
    big = s >= t
    g_old = score_grid(count_pmf(lh, r_nb), count_pmf(la, r_nb))
    g_new = score_grid(count_pmf(h, r_nb), count_pmf(a, r_nb))
    size = g_old.shape[1]
    i, j = np.arange(size)[:, None], np.arange(size)[None, :]
    n = np.arange(len(x))
    xi, yi = x.astype(int).clip(0, size - 1), y.astype(int).clip(0, size - 1)

    def p_total(g: Arr) -> Arr:
        out = np.zeros(len(x))
        for tot in range(2 * size - 1):
            out = np.where(xi + yi == tot, g[:, (i + j) == tot].sum(axis=1), out)
        return out

    def p_1x2(g: Arr) -> Arr:
        p = market_probs(g)
        return np.asarray(p[n, np.where(x > y, 0, np.where(x == y, 1, 2))],
                          dtype=float)

    def p_fav3(g: Arr) -> Arr:
        fav_home = lh >= la
        p = np.where(fav_home, g[:, (i - j) >= 3].sum(axis=1),
                     g[:, (j - i) >= 3].sum(axis=1))
        hit = np.where(fav_home, x - y, y - x) >= 3
        return np.asarray(np.where(hit, p, 1 - p), dtype=float)

    def nll(p: Arr) -> Arr:
        return np.asarray(-np.log(np.maximum(p, 1e-12)), dtype=float)

    diffs = {
        "goals_for": -(nb_ll(x, h, r_nb) + nb_ll(y, a, r_nb)) / 2
        + (nb_ll(x, lh, r_nb) + nb_ll(y, la, r_nb)) / 2,
        "goals_total": nll(p_total(g_new)) - nll(p_total(g_old)),
        "1x2": nll(p_1x2(g_new)) - nll(p_1x2(g_old)),
        "fav_minus_2_5": nll(p_fav3(g_new)) - nll(p_fav3(g_old)),
    }
    out: dict[str, Any] = {}
    for name, v in diffs.items():
        out[name] = {"all": boot(v), "s_ge_T": boot(v[big]) if big.any() else None}
    margin = np.where(lh >= la, x - y, y - x)
    out["margin_bias_s_ge_2"] = (boot(margin[s >= 2] - s[s >= 2])
                                 if (s >= 2).any() else None)
    return out


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db-path", required=True,
                    help="a COPY of data/sofa.db (the pickle lands next to it)")
    ap.add_argument("--from", dest="from_day", default="2025-07-01")
    ap.add_argument("--fit-to", default="2026-07-01")
    ap.add_argument("--cut", default="2026-10-29")
    ap.add_argument("--json-out", required=True)
    args = ap.parse_args(argv)
    db = Path(args.db_path)
    history = fr.without_awarded(fr.load_history(db, db.parent / "cache"))
    history = [replace(r, values={METRIC: r.values[METRIC]})
               for r in history if METRIC in r.values]
    cup = load_cup()
    r_nb = load_config().nb_r
    rows = knockout_rows(history, _ts(args.from_day), _ts(args.cut),
                         cup.competitions, dict(cup.eta))
    print(f"{len(rows)} LINKED_BY_STRENGTH knockout rows", file=sys.stderr)
    fit_to = _ts(args.fit_to)
    report: dict[str, Any] = {"db_path": str(db), "from": args.from_day,
                              "fit_to": args.fit_to, "cut": args.cut, "r_nb": r_nb}
    for scope, flag in (("domestic", 0.0), ("international", 1.0)):
        part = [r for r in rows if r["intl"] == flag]
        train = [r for r in part if r["ts"] < fit_to]
        test = [r for r in part if r["ts"] >= fit_to]
        gain, t, k = fit(train, r_nb) if train else (0.0, math.inf, 1.0)
        cell: dict[str, Any] = {"train_n": len(train), "test_n": len(test),
                                "train_gain": round(gain, 3),
                                "T": None if math.isinf(t) else t, "k": k}
        if test and not math.isinf(t):
            cell["test"] = score(test, t, k, r_nb)
        report[scope] = cell
    Path(args.json_out).write_text(json.dumps(report, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
