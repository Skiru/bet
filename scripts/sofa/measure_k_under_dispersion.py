#!/usr/bin/env python3
"""measure_k_under_dispersion.py - does a per-market K_CENTRE still gain once
the spread is the history-fitted dispersion (epochs.COUNT_DISPERSION)?
READ-ONLY evidence, never a gate.

Track A1 (measure_pooling.py, docs/sofa/evidence/pooling_2026-10-08.md) found
that a K per (market, kind) - 2..10 for shots and fouls instead of the pooled
15 - gains log-loss, concentrated in samples of 3-7 matches, and chose K by
squared error of the centre on rows priced with the SAMPLE variance. Track A2
(count_dispersion) removes the under-estimated variability of short samples by
a different road: variance = mu + alpha mu^2 around the centre. The K gain may
be the same effect measured twice.

What this does (same rows, same split as measure_pooling: the rows it logs,
train = the 240 days before the cut, test = after it):
  * the centre of every row for every K of K_GRID, rebuilt from the logged
    sample mean, n and the league prior (prior = what today's K=15 centre
    implies: c15 = (n mean + 15 prior) / (n + 15));
  * the ladder probabilities (calibrate_from_cache.lines_for around today's
    centre) under three spreads: `A` the fitted alpha per (market,
    competition) - what ships with the switch, `M` the market's alpha only (no
    per-competition value), `N` the sample variance (the control: today);
  * K per (market, kind) CHOSEN ON LOG-LOSS on the train rows with n >= 8 (the
    replay population), never on squared error; the gain is the test rows'
    log-loss at that K minus at K = 15, uncalibrated (`ll`) and after a
    calibration map fitted on the train rows (`lc`, measure_pooling's);
  * 95% interval: match bootstrap (measure_pooling.Boot), x1e-4 nat.

Caveat: the shipped alphas were fitted on the whole history through 2026-10-07
(validation from 2026-04-08), so the test window is in-sample for them (a
few parameters per market, and `M` has one per market).

  PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_k_under_dispersion.py \\
      --rows <rows.pkl from measure_pooling run --scratch> --out <json>
"""

from __future__ import annotations

import argparse
import json
import math
import pickle
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from scripts.sofa import measure_pooling as mp  # noqa: E402

K_TODAY = mp.K_TODAY
K_GRID = mp.K_GRID
SPREADS = ("A", "M", "N")
MIN_N = mp.MIN_SAMPLE
# a group is changed only from this many train rows (the K of a thin group is noise)
MIN_TRAIN_ROWS = 500

_TABLE: Any = None


def _init_worker(table_path: str | None) -> None:
    global _TABLE
    from bet.sofa.count_dispersion import load_table

    _TABLE = load_table(Path(table_path)) if table_path else load_table()


def dispersion_for(spread: str, table: Any, market: str, comp: int) -> Any:
    """The Dispersion one row reads under `spread`; None = the sample variance."""
    if spread == "N" or table is None:
        return None
    if spread == "M":
        return table.read("football", market, None)
    return table.read("football", market, comp or None)


def centre_at(k: float, n: float, mean: float, prior: float) -> float:
    return (n * mean + k * prior) / (n + k)


def prior_of(c15: float, n: float, mean: float) -> float:
    return (c15 * (n + K_TODAY) - n * mean) / K_TODAY


def row_probs(
    market: str, comp: int, mean: float, var: float, n: int, prior: float,
    spread: str, table: Any,
) -> tuple[Any, Any, Any]:
    """P(OVER) of the 9 rungs for every K of K_GRID ((ncols, 9)), the rung
    outcomes are the caller's; plus today's high-confidence mask (9,)."""
    from bet.sofa.engine import sheet_count_p_raw, sheet_predictive_sd
    from scripts.sofa import calibrate_from_cache as cc

    disp = dispersion_for(spread, table, market, comp)
    anchor = centre_at(K_TODAY, n, mean, prior)
    lines = cc.lines_for(anchor)
    ps = []
    for k in K_GRID:
        c = centre_at(k, n, mean, prior)
        sd = sheet_predictive_sd(market, "football", mean, var, n, c, disp)
        row = []
        for line in lines:
            p = sheet_count_p_raw(market, c, sd, line, "OVER", disp)
            row.append(min(1.0 - mp.P_CLIP, max(mp.P_CLIP, p)))
        ps.append(row)
    i15 = K_GRID.index(K_TODAY)
    hi = [max(p, 1.0 - p) >= mp.HI_CONF for p in ps[i15]]
    return ps, lines, hi


def _chunk(args: tuple[Any, ...]) -> tuple[Any, Any, Any, Any]:
    import numpy as np

    rows, spread = args
    k = len(rows)
    ncols = len(K_GRID)
    ll = np.zeros((k, ncols))
    pp = np.zeros((k, ncols, 9), dtype=np.float32)
    oo = np.zeros((k, 9), dtype=np.int8)
    hh = np.zeros((k, 9), dtype=bool)
    for i, (market, comp, mean, var, n, y, prior) in enumerate(rows):
        ps, lines, hi = row_probs(market, comp, mean, var, n, prior, spread, _TABLE)
        o = [1.0 if y > line else 0.0 for line in lines]
        for c, pl in enumerate(ps):
            ll[i, c] = sum(
                -(math.log(p) if oc else math.log(1.0 - p))
                for p, oc in zip(pl, o, strict=True))
            pp[i, c] = pl
        oo[i] = o
        hh[i] = hi
    return ll, pp, oo, hh


def ladder_losses(
    meta: dict[str, Any], prior: Any, spread: str, table_path: str | None,
    procs: int, log: Any,
) -> dict[str, Any]:
    import multiprocessing as mpr

    import numpy as np

    nrows = len(meta["ev"])
    size = 2000

    def chunks() -> Any:
        for lo in range(0, nrows, size):
            rows = []
            for i in range(lo, min(lo + size, nrows)):
                rows.append((
                    mp.market_of(int(meta["base"][i]), int(meta["unit"][i])),
                    int(meta["comp"][i]), float(meta["mean"][i]),
                    float(meta["var"][i]), int(meta["n"][i]), float(meta["y"][i]),
                    float(prior[i])))
            yield (rows, spread)

    parts = []
    done = 0
    with mpr.Pool(procs, initializer=_init_worker, initargs=(table_path,)) as pool:
        for j, part in enumerate(pool.imap(_chunk, chunks())):
            parts.append(part)
            done += len(part[0])
            if j % 50 == 0:
                log(f"[{spread}] ladder {done}/{nrows}")
    return {
        "ll": np.concatenate([q[0] for q in parts]),
        "p": np.concatenate([q[1] for q in parts]),
        "o": np.concatenate([q[2] for q in parts]),
        "hi": np.concatenate([q[3] for q in parts]),
    }


def choose_k(ll: Any, mask: Any) -> tuple[float, list[float]]:
    """The K of K_GRID with the lowest summed log-loss over `mask` rows."""
    sums = ll[mask].sum(axis=0)
    best = int(sums.argmin())
    return K_GRID[best], [float(s) for s in sums]


RUNGS = 9  # half-lines per row (calibrate_from_cache.lines_for)
# a base whose K is left at 15 in the set that would be wired: goals_for's K = 10
# passes the train validation and still loses on the test rows (see the report)
EXCLUDE_BASES = frozenset({"goals"})
VAL_SHARE = 1.0 / 3.0  # the last share of the train rows (by time) validates K


def validated_k(
    meta: dict[str, Any], ll: Any, group: Any, train: Any, ok: Any, reps: int,
    min_train_rows: int,
) -> dict[int, tuple[float, dict[str, Any]]]:
    """K per group chosen WITHOUT the test rows and gated: K is the lowest
    summed log-loss on the first part of the train rows (n >= 8); it is kept
    only when it beats K = 15 on the last VAL_SHARE of the train rows with the
    95% match bootstrap entirely below zero, else the group stays at 15.  The
    pre-registered rule for what could be wired: a K that is noise on the
    train rows does not reach the test."""
    import numpy as np

    ts_train = meta["ts"][train & ok]
    cut = float(np.quantile(ts_train, 1.0 - VAL_SHARE)) if len(ts_train) else 0.0
    fit_rows = train & ok & (meta["ts"] < cut)
    val_rows = train & ok & (meta["ts"] >= cut)
    i15 = K_GRID.index(K_TODAY)
    boot = mp.Boot(meta["ev"].astype(np.int64), reps=reps, seed=11)
    ones = np.ones(len(group))
    out: dict[int, tuple[float, dict[str, Any]]] = {}
    for g in np.unique(group):
        sel = fit_rows & (group == g)
        vsel = val_rows & (group == g)
        info: dict[str, Any] = {"fit_rows": int(sel.sum()), "val_rows": int(vsel.sum())}
        if int(sel.sum()) < min_train_rows or int(vsel.sum()) < 200:
            out[int(g)] = (K_TODAY, {**info, "kept": False, "why": "thin"})
            continue
        k, _ = choose_k(ll, sel)
        info["K_fit"] = k
        if k == K_TODAY:
            out[int(g)] = (K_TODAY, {**info, "kept": False, "why": "K_fit = 15"})
            continue
        d = ll[:, K_GRID.index(k)] - ll[:, i15]
        r = boot.ratio(d, ones * float(RUNGS), vsel)
        info["val_d_ll"] = r
        kept = r["hi"] < 0.0
        info["kept"] = bool(kept)
        out[int(g)] = (k if kept else K_TODAY, info)
    return out


def analyse(
    meta: dict[str, Any], loss: dict[str, Any], reps: int, log: Any,
    min_train_rows: int = MIN_TRAIN_ROWS,
) -> dict[str, Any]:
    import numpy as np

    train = meta["train"] == 1
    test = ~train
    group = meta["base"] * 2 + (meta["unit"] == 2)
    ok = meta["nmin"] >= MIN_N
    # calibration maps on the train rows of every column
    lc_all, lc_hi = mp.calibrated_losses(loss, train & ok, test, group)
    i15 = K_GRID.index(K_TODAY)
    hi_n = loss["hi"].sum(axis=1).astype(float)
    ones = np.full(len(group), float(loss["o"].shape[1]))
    boot = mp.Boot(meta["ev"].astype(np.int64), reps=reps)
    rows_idx = np.arange(len(group))
    ll_15 = loss["ll"][:, i15]
    lc_15 = lc_all[:, i15]
    lch_15 = lc_hi[:, i15]

    def name_of(g: int) -> str:
        return f"{mp.BASES[g // 2]}_{'total' if g % 2 else 'for'}"

    plain: dict[int, float] = {}
    detail: dict[str, Any] = {}
    for g in np.unique(group):
        sel = train & ok & (group == g)
        if int(sel.sum()) < min_train_rows:
            plain[int(g)] = K_TODAY
            detail[name_of(int(g))] = {"K": K_TODAY, "train_rows": int(sel.sum()),
                                       "note": "too thin, K stays 15"}
            continue
        k, sums = choose_k(loss["ll"], sel)
        plain[int(g)] = k
        detail[name_of(int(g))] = {
            "K": k, "train_rows": int(sel.sum()),
            "train_ll_by_k": dict(zip(map(str, K_GRID), sums, strict=True))}
    valid = validated_k(meta, loss["ll"], group, train, ok, reps, min_train_rows)
    for g, (k, info) in valid.items():
        detail[name_of(g)]["K_validated"] = k
        detail[name_of(g)]["validation"] = info
    out: dict[str, Any] = {"chosen": detail, "strata": {}}

    validated = {g: k for g, (k, _i) in valid.items()}
    # what would be wired: the validated K, goals left at 15 (see EXCLUDE_BASES)
    wired = {g: (K_TODAY if mp.BASES[g // 2] in EXCLUDE_BASES else k)
             for g, k in validated.items()}
    out["wired_k"] = {name_of(g): k for g, k in wired.items()}
    for tag, chosen in (("", plain), ("V:", validated), ("W:", wired)):
        col = np.array([K_GRID.index(chosen[int(g)]) for g in group])
        ll_k = loss["ll"][rows_idx, col]
        lc_k = lc_all[rows_idx, col]
        lch_k = lc_hi[rows_idx, col]

        def stratum(name: str, mask: Any, ll_k: Any = ll_k, lc_k: Any = lc_k,
                    lch_k: Any = lch_k, tag: str = tag) -> None:
            if int(mask.sum()) < 200:
                return
            out["strata"][tag + name] = {
                "n_units": int(mask.sum()),
                "today_lc_all": boot.ratio(lc_15, ones, mask),
                "d_ll_all": boot.ratio(ll_k - ll_15, ones, mask),
                "d_lc_all": boot.ratio(lc_k - lc_15, ones, mask),
                "d_lc_hi": boot.ratio(lch_k - lch_15, np.maximum(hi_n, 0.0), mask),
            }

        moved = np.array([chosen[int(g)] != K_TODAY for g in group])
        half = meta["ts"] >= float(np.median(meta["ts"][test]))
        for gi, gname in enumerate(("for", "total")):
            kind = (meta["unit"] == 2) == bool(gi)
            stratum(f"ALL_{gname}|n>=8", test & ok & kind)
            stratum(f"ALL_{gname}|n>=8|first half of test", test & ok & kind & ~half)
            stratum(f"ALL_{gname}|n>=8|second half of test", test & ok & kind & half)
            stratum(f"ALL_{gname}|n 3-7", test & (meta["nmin"] < MIN_N) & kind)
            stratum(f"MOVED_{gname}|n>=8", test & ok & kind & moved)
            for bi, base in enumerate(mp.BASES):
                stratum(f"{base}_{gname}|n>=8",
                        test & ok & kind & (meta["base"] == bi))
                stratum(f"{base}_{gname}|n 3-7",
                        test & (meta["nmin"] < MIN_N) & kind & (meta["base"] == bi))
        log(f"strata {tag or 'plain'} done")
    return out


def run(args: argparse.Namespace) -> int:
    import numpy as np

    status = Path(args.status) if args.status else None

    def log(msg: str) -> None:
        mp._status(msg, status)

    meta_l, cols = pickle.loads(Path(args.rows).read_bytes())
    meta = {k: np.asarray(v) for k, v in meta_l.items()}
    today = np.asarray(cols["today_F"])
    del meta_l, cols
    prior = np.array([prior_of(c, n, m) for c, n, m in
                      zip(today, meta["n"], meta["mean"], strict=True)])
    keep = np.ones(len(prior), dtype=bool)
    if args.stride > 1:  # a smoke run: every stride-th MATCH
        keep = (meta["ev"].astype(np.int64) % args.stride) == 0
    meta = {k: v[keep] for k, v in meta.items()}
    prior = prior[keep]
    log(f"rows {len(prior)} (train {(meta['train'] == 1).sum()}); "
        f"table {args.table or 'config'}")
    result: dict[str, Any] = {
        "meta": {
            "rows": int(len(prior)), "K_GRID": list(K_GRID), "K_TODAY": K_TODAY,
            "reps": args.reps, "min_n": MIN_N, "min_train_rows": MIN_TRAIN_ROWS,
            "table": args.table or "config/sofa_count_dispersion.json",
            "generated_at": datetime.now(UTC).isoformat(),
        },
        "spreads": {},
    }
    for spread in args.spreads.split(","):
        loss = ladder_losses(meta, prior, spread, args.table, args.procs, log)
        result["spreads"][spread] = analyse(meta, loss, args.reps, log)
        del loss
        Path(args.out).write_text(json.dumps(result, indent=1, default=float),
                                  encoding="utf-8")
        log(f"[{spread}] done")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--rows", required=True,
                    help="rows.pkl of measure_pooling run --scratch")
    ap.add_argument("--out", required=True)
    ap.add_argument("--table", help="count dispersion config (default: shipped)")
    ap.add_argument("--spreads", default=",".join(SPREADS))
    ap.add_argument("--procs", type=int, default=3)
    ap.add_argument("--reps", type=int, default=300)
    ap.add_argument("--stride", type=int, default=1,
                    help="keep one match in this many (a smoke run)")
    ap.add_argument("--status")
    return run(ap.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
