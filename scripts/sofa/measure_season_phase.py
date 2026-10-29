"""Measure the season-phase term of the football goals centre (audit
2026-10-13 C1, epochs.SEASON_PHASE).

Pre-registered in docs/sofa/evidence/season_phase_2026-10-13.md. One step
ahead on the cached football history (bet.sofa.centre_replay): SHEET's live
centre (W_FOOTBALL_RATING x rating + (1 - W) x shrunk sample where rated)
against the same centre x exp(c[market][phase]), the phase as of the kickoff
(season_phase.phases_by_event), c fitted walk-forward: for every month of the
window on the rows strictly before that month's first day
(season_phase.fit_coefficients' closed form, computed here from cumulative
sums - checked against the function on the first month).

Primary metric: NB log-loss of the observed count (alpha from the installed
config/sofa_count_dispersion.json, market x competition), new minus old per
row (a row without a phase or a coefficient: 0), 95% from resampling matches
(2000, seed 0). Secondary: the same on phased rows only, bias by phase,
halves of the window, coefficients per month.

The history is read from the parsed pickle, read-only (never re-parsed or
rewritten here). Writes nothing the pipeline reads.

    SOFA_DB_PATH=... PYTHONPATH=src:. .venv/bin/python \\
        scripts/sofa/measure_season_phase.py [--from 2025-08-01] \\
        [--to 2026-10-12] [--train-from 2024-10-01] [--json-out <file>]
"""

from __future__ import annotations

import argparse
import json
import math
import pickle
import sys
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO / "src"), str(_REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import centre_replay as cr  # noqa: E402
from bet.sofa import count_dispersion  # noqa: E402
from bet.sofa import football_rating as fr  # noqa: E402
from bet.sofa import season_phase as sp  # noqa: E402
from bet.sofa.config import SofaConfig, config_path  # noqa: E402
from bet.sofa.per_market_k import k_for_market  # noqa: E402

F64 = NDArray[np.float64]
I64 = NDArray[np.int64]
PHASE_CODE: dict[str | None, int] = {None: -1}
PHASE_CODE.update({p: i for i, p in enumerate(sp.PHASES)})
N_BOOT = 2000


def ts_of(day: str) -> int:
    return int(datetime.fromisoformat(day).replace(tzinfo=UTC).timestamp())


def months(start: str, end: str) -> list[tuple[str, int, int]]:
    """(label, first ts, next month's first ts) covering [start, end]."""
    d = date.fromisoformat(start).replace(day=1)
    stop = date.fromisoformat(end) + timedelta(days=1)
    out = []
    while d < stop:
        nxt = (d.replace(day=28) + timedelta(days=4)).replace(day=1)
        lo = max(d, date.fromisoformat(start))
        out.append((d.strftime("%Y-%m"), ts_of(lo.isoformat()),
                    ts_of(min(nxt, stop).isoformat())))
        d = nxt
    return out


def load_history(path: Path | None = None,
                 awarded_out: bool = False) -> list[fr.FootballResult]:
    """The parsed history pickle SHEET keeps, read-only; `awarded_out`
    (--awarded-excluded, epochs.AWARDED_EXCLUDED as SHEET from 2026-10-30)
    leaves results awarded at the table out."""
    if path is None:
        cache = Path(SofaConfig.from_env().db_path).parent / "cache"
        path = cache / "football_history.pkl"
    _fp, history = pickle.loads(path.read_bytes())
    out = list(history)
    return fr.without_awarded(out) if awarded_out else out


def k_table(markets: Iterable[str]) -> dict[str, float]:
    constants = json.loads(config_path("sofa_engine_constants.json").read_text())
    sport_k = float(constants["K_CENTRE"]["by_sport"]["football"])
    return {m: k_for_market(constants, "football", m, sport_k) for m in markets}


def nb_logloss_vec(y: F64, mu: F64, alpha: F64) -> F64:
    """-log P(Y = y), NB(mean mu, variance mu + alpha mu^2), integer y;
    vectorised centre_replay.nb_logloss (alpha floored at 1e-9 -> r 1e9)."""
    mu = np.maximum(mu, 1e-9)
    r = 1.0 / np.maximum(alpha, 1e-9)
    yi = np.rint(y).astype(np.int64)
    acc = np.zeros(len(y))
    for k in range(int(yi.max()) if len(yi) else 0):
        acc += np.where(k < yi, np.log(r + k), 0.0)
    top = int(yi.max()) + 1 if len(yi) else 1
    lgy = np.array([math.lgamma(v + 1) for v in range(top)])
    ll = acc - lgy[yi] + r * np.log(r / (r + mu)) + yi * np.log(mu / (r + mu))
    return -ll  # type: ignore[no-any-return]


@dataclass
class Rows:
    ts: I64
    event: I64
    comp: I64
    y: F64
    rating: F64  # NaN when not rated
    sample: F64
    alpha: F64

    def subset(self, mask: NDArray[np.bool_]) -> Rows:
        return Rows(self.ts[mask], self.event[mask], self.comp[mask], self.y[mask],
                    self.rating[mask], self.sample[mask], self.alpha[mask])


def collect(history: Sequence[fr.FootballResult], train_from: str, end: str,
            markets: Sequence[str]) -> dict[str, Rows]:
    """Per market, every row centre_replay.walk yields in [train_from, end]."""
    table = count_dispersion.load_table()
    cols: dict[str, dict[str, list[float]]] = {
        m: defaultdict(list) for m in markets}
    alpha_cache: dict[tuple[str, int], float] = {}
    for row in cr.walk(history, ts_of(train_from), ts_of(end) + 86400,
                       markets, k_table(markets)):
        c = cols[row.market]
        key = (row.market, row.competition_id)
        if key not in alpha_cache:
            disp = table.read("football", row.market, row.competition_id)
            alpha_cache[key] = disp.alpha if disp is not None else 0.0
        c["ts"].append(row.ts)
        c["event"].append(row.event_id)
        c["comp"].append(row.competition_id)
        c["y"].append(row.y)
        c["rating"].append(row.rating if row.rating is not None else math.nan)
        c["sample"].append(row.sample)
        c["alpha"].append(alpha_cache[key])
    out = {}
    for m, c in cols.items():
        out[m] = Rows(
            np.asarray(c["ts"], dtype=np.int64), np.asarray(c["event"], dtype=np.int64),
            np.asarray(c["comp"], dtype=np.int64), np.asarray(c["y"], dtype=np.float64),
            np.asarray(c["rating"], dtype=np.float64),
            np.asarray(c["sample"], dtype=np.float64),
            np.asarray(c["alpha"], dtype=np.float64))
    return out


def live_centre(rows: Rows, market: str, w: float | F64 = fr.W_FOOTBALL_RATING) -> F64:
    """SHEET's centre: W x rating + (1 - W) x sample where rated."""
    rated = np.isfinite(rows.rating) & (market not in fr.UNRATED_MARKETS)
    blend = w * np.where(rated, rows.rating, 0.0) + (1 - w) * rows.sample
    return np.where(rated, blend, rows.sample)


def boot_by_match(event: I64, d: F64, n_boot: int = N_BOOT,
                  seed: int = 0) -> tuple[float, float, float, int, int]:
    """(mean per row, 2.5%, 97.5%, rows, matches), resampling matches."""
    if not len(d):
        nan = float("nan")
        return nan, nan, nan, 0, 0
    uniq, inv = np.unique(event, return_inverse=True)
    sums = np.bincount(inv, weights=d)
    counts = np.bincount(inv).astype(np.float64)
    rng = np.random.default_rng(seed)
    stats = np.empty(n_boot)
    for b in range(n_boot):
        idx = rng.integers(0, len(uniq), len(uniq))
        stats[b] = sums[idx].sum() / counts[idx].sum()
    lo, hi = np.quantile(stats, [0.025, 0.975])
    return (float(sums.sum() / counts.sum()), float(lo), float(hi),
            int(counts.sum()), int(len(uniq)))


def phase_codes(rows: Rows, phases: dict[int, str | None]) -> I64:
    return np.array([PHASE_CODE[phases.get(int(e))] for e in rows.event],
                    dtype=np.int64)


def coefficients_before(centre: F64, y: F64, code: I64, mask: NDArray[np.bool_],
                        min_rows: int = sp.MIN_FIT_ROWS) -> dict[str, float]:
    """season_phase.fit_coefficients on the masked rows (numpy sums)."""
    out: dict[str, float] = {}
    mid = PHASE_CODE[sp.PHASE_MID]
    sel = mask & (code == mid)
    if sel.sum() < min_rows:
        return out
    base = math.log(y[sel].sum() / centre[sel].sum())
    for p in sp.PHASES:
        if p == sp.PHASE_MID:
            continue
        s = mask & (code == PHASE_CODE[p])
        if s.sum() < min_rows or y[s].sum() <= 0:
            continue
        c = math.log(y[s].sum() / centre[s].sum()) - base
        out[p] = max(-sp.MAX_ABS_COEFFICIENT, min(sp.MAX_ABS_COEFFICIENT, c))
    return out


def measure_market(rows: Rows, market: str, phases: dict[int, str | None],
                   start: str, end: str) -> dict[str, Any]:
    centre = live_centre(rows, market)
    code = phase_codes(rows, phases)
    new = centre.copy()
    in_eval = np.zeros(len(centre), dtype=bool)
    coefs: dict[str, dict[str, float]] = {}
    checked = False
    for label, lo, hi in months(start, end):
        before = rows.ts < lo
        cf = coefficients_before(centre, rows.y, code, before)
        if not checked:
            ref = sp.fit_coefficients(
                centre[before].tolist(), rows.y[before].tolist(),
                [sp.PHASES[c] if c >= 0 else None for c in code[before]])
            assert ref.keys() == cf.keys()
            assert all(abs(ref[k] - cf[k]) < 1e-9 for k in ref)
            checked = True
        coefs[label] = cf
        cur = (rows.ts >= lo) & (rows.ts < hi)
        in_eval |= cur
        for p, c in cf.items():
            sel = cur & (code == PHASE_CODE[p])
            new[sel] = centre[sel] * math.exp(c)
    ev = rows.subset(in_eval)
    c_old, c_new, cd = centre[in_eval], new[in_eval], code[in_eval]
    l_old = nb_logloss_vec(ev.y, c_old, ev.alpha)
    l_new = nb_logloss_vec(ev.y, c_new, ev.alpha)
    d = l_new - l_old
    phased = cd >= 0
    halves = {}
    split = ts_of("2026-03-01")
    for name, m in (("2025-08..2026-02", ev.ts < split),
                    ("2026-03..2026-10", ev.ts >= split)):
        halves[name] = list(boot_by_match(ev.event[m], d[m]))
    by_phase = {}
    for p in sp.PHASES:
        m = cd == PHASE_CODE[p]
        if not m.any():
            continue
        by_phase[p] = {
            "rows": int(m.sum()),
            "bias_old": float((c_old[m] - ev.y[m]).mean()),
            "bias_new": float((c_new[m] - ev.y[m]).mean()),
            "ratio_y_over_centre": float(ev.y[m].sum() / c_old[m].sum()),
            "d_logloss": list(boot_by_match(ev.event[m], d[m])),
        }
    return {
        "d_logloss": list(boot_by_match(ev.event, d)),
        "d_logloss_phased_rows": list(boot_by_match(ev.event[phased], d[phased])),
        "rows": int(len(d)), "phased_rows": int(phased.sum()),
        "logloss_old": float(l_old.mean()), "logloss_new": float(l_new.mean()),
        "mse_old": float(((c_old - ev.y) ** 2).mean()),
        "mse_new": float(((c_new - ev.y) ** 2).mean()),
        "rated_share": float(np.isfinite(ev.rating).mean()),
        "by_phase": by_phase, "halves": halves, "coefficients_by_month": coefs,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start", default="2025-08-01")
    ap.add_argument("--to", dest="end", default="2026-10-12")
    ap.add_argument("--train-from", default="2024-10-01")
    ap.add_argument("--history", help="the parsed history pickle (read-only)")
    ap.add_argument("--markets", nargs="+", default=list(sp.SEASON_PHASE_MARKETS))
    ap.add_argument("--json-out")
    args = ap.parse_args()
    history = load_history(Path(args.history) if args.history else None)
    print(f"history {len(history)}", flush=True)
    phases = sp.phases_by_event(history)
    rows = collect(history, args.train_from, args.end, args.markets)
    del history
    out: dict[str, Any] = {"window": [args.start, args.end],
                           "train_from": args.train_from}
    for m in args.markets:
        out[m] = measure_market(rows[m], m, phases, args.start, args.end)
        summary = {k: out[m][k] for k in ("d_logloss", "d_logloss_phased_rows",
                                          "rows", "phased_rows")}
        print(m, json.dumps(summary), flush=True)
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(out, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
