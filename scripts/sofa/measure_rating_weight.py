"""Measure the football rating's weight per market (audit 2026-10-13 B14,
epochs.FOOTBALL_RATING_WEIGHT).

Pre-registered in docs/sofa/evidence/rating_weight_2026-10-13.md. One step
ahead on the cached football history (bet.sofa.centre_replay): the centre
W x rating + (1 - W) x shrunk sample with W walk-forward per market (the grid
W of rating_weight.W_GRID with the lowest mean NB log-loss on the rows
strictly before each month's first day - rating_weight.fit_weight's rule,
vectorised here and checked against it on a sample) against W =
W_FOOTBALL_RATING (0.5). Rows without a rating are not scored (W does not
touch them).

Primary metric: NB log-loss of the observed count (alpha from the installed
config/sofa_count_dispersion.json, market x competition), new minus old per
row, 95% from resampling matches (2000, seed 0).

The history is read from the parsed pickle, read-only. Writes nothing the
pipeline reads.

    SOFA_DB_PATH=... PYTHONPATH=src:. .venv/bin/python \\
        scripts/sofa/measure_rating_weight.py [--from 2025-08-01] \\
        [--to 2026-10-12] [--train-from 2024-10-01] [--json-out <file>]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO / "src"), str(_REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import football_rating as fr  # noqa: E402
from bet.sofa import rating_weight as rw  # noqa: E402
from scripts.sofa.measure_season_phase import (  # noqa: E402
    Rows,
    boot_by_match,
    collect,
    load_history,
    months,
    nb_logloss_vec,
    ts_of,
)

F64 = NDArray[np.float64]


def rated_markets(scope: frozenset[str] = frozenset()) -> tuple[str, ...]:
    """Every `_for` / `_total` market of BASE_METRICS the rating prices
    (UNRATED_MARKETS out unless in `scope`)."""
    out = []
    for base in fr.BASE_METRICS:
        for m in (base, base[: -len("_for")] + "_total"):
            if m in fr.UNRATED_MARKETS and m not in scope:
                continue
            out.append(m)
    return tuple(out)


def loss_grid(rows: Rows) -> F64:
    """(len(W_GRID), rows) NB log-loss of every row at every grid W."""
    return np.vstack([
        nb_logloss_vec(rows.y, w * rows.rating + (1 - w) * rows.sample, rows.alpha)
        for w in rw.W_GRID])


def measure_market(rows: Rows, market: str, start: str, end: str) -> dict[str, Any]:
    rows = rows.subset(np.isfinite(rows.rating))
    if not len(rows.y):
        return {"rows": 0}
    grid = loss_grid(rows)
    i_half = rw.W_GRID.index(fr.W_FOOTBALL_RATING)
    tie = np.array([abs(w - fr.W_FOOTBALL_RATING) for w in rw.W_GRID])
    chosen = np.full(len(rows.y), i_half)
    in_eval = np.zeros(len(rows.y), dtype=bool)
    w_by_month: dict[str, float] = {}
    for label, lo, hi in months(start, end):
        before = rows.ts < lo
        if before.sum() == 0:
            i = i_half
        else:
            mean = grid[:, before].mean(axis=1)
            # rating_weight.fit_weight's order: lowest loss, then nearest 0.5
            i = int(np.lexsort((tie, mean))[0])
        w_by_month[label] = rw.W_GRID[i]
        cur = (rows.ts >= lo) & (rows.ts < hi)
        chosen[cur] = i
        in_eval |= cur
    idx = np.arange(len(rows.y))
    d = grid[chosen, idx] - grid[i_half, idx]
    ev = rows.subset(in_eval)
    de = d[in_eval]
    w_e = np.array([rw.W_GRID[i] for i in chosen[in_eval]])
    c_old = 0.5 * ev.rating + 0.5 * ev.sample
    c_new = w_e * ev.rating + (1 - w_e) * ev.sample
    split = ts_of("2026-03-01")
    halves = {name: list(boot_by_match(ev.event[m], de[m]))
              for name, m in (("2025-08..2026-02", ev.ts < split),
                              ("2026-03..2026-10", ev.ts >= split))}
    full_mean = grid[:, in_eval].mean(axis=1)
    return {
        "d_logloss": list(boot_by_match(ev.event, de)),
        "rows": int(len(de)),
        "logloss_old": float(grid[i_half, in_eval].mean()),
        "logloss_new": float((grid[chosen, idx])[in_eval].mean()),
        "mse_old": float(((c_old - ev.y) ** 2).mean()),
        "mse_new": float(((c_new - ev.y) ** 2).mean()),
        "w_by_month": w_by_month,
        # in-sample curve over the evaluation window (reported, not the test)
        "logloss_by_w_eval_window": {str(w): float(v) for w, v in
                                     zip(rw.W_GRID, full_mean, strict=True)},
        "halves": halves,
    }


def check_fit_rule(rows: Rows) -> None:
    """The vectorised choice equals rating_weight.fit_weight on a sample."""
    sub = rows.subset(np.isfinite(rows.rating))
    sub = sub.subset(np.arange(len(sub.y)) < 3000)
    if not len(sub.y):
        return
    w_ref, _ = rw.fit_weight(sub.rating.tolist(), sub.sample.tolist(),
                             sub.y.tolist(), sub.alpha.tolist())
    grid = loss_grid(sub).mean(axis=1)
    tie = np.array([abs(w - fr.W_FOOTBALL_RATING) for w in rw.W_GRID])
    w_vec = rw.W_GRID[int(np.lexsort((tie, grid))[0])]
    assert abs(w_ref - w_vec) < 1e-12, (w_ref, w_vec)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start", default="2025-08-01")
    ap.add_argument("--to", dest="end", default="2026-10-12")
    ap.add_argument("--train-from", default="2024-10-01")
    ap.add_argument("--history", help="the parsed history pickle (read-only)")
    ap.add_argument("--markets", nargs="+",
                    default=list(rated_markets(fr.RATED_SCOPE_MARKETS)))
    ap.add_argument("--json-out")
    args = ap.parse_args()
    history = load_history(Path(args.history) if args.history else None)
    print(f"history {len(history)}", flush=True)
    rows = collect(history, args.train_from, args.end, args.markets)
    del history
    out: dict[str, Any] = {"window": [args.start, args.end],
                           "train_from": args.train_from,
                           "rated_today": list(rated_markets())}
    for m in args.markets:
        check_fit_rule(rows[m])
        out[m] = measure_market(rows[m], m, args.start, args.end)
        print(m, json.dumps({k: out[m].get(k) for k in ("d_logloss", "rows")}),
              json.dumps(out[m].get("w_by_month")), flush=True)
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(out, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
