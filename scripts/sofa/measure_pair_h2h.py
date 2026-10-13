#!/usr/bin/env python3
"""Does a pair's own past head-to-head carry information beyond the model?

Pre-registered in docs/sofa/evidence/pair_h2h_2026-10-13.md. Read-only: the
database is opened mode=ro by every reader used here, the football history
pickle in data/cache/ is only read (never rewritten), nothing under config/
or a run directory is written.

"Residual persistence": for every match the model's as-of centre c is rebuilt
one step ahead and its residual r = y - c is kept per pair (and per side). A
match whose pair met k >= 1 times in the previous MAX_GAP_DAYS (at most
K_MAX latest meetings, each with its own as-of centre) gets the adjusted
centre

    c' = c + w(k) x mean(previous residuals),  w(k) = k / (k + K)

the random-effect BLUP of a pair effect; K is fitted on the training rows
only (strictly before each evaluated month), from a fixed grid that includes
infinity (no adjustment). The primary metric is the difference new - old per
row, a 95% match bootstrap (2000, seed 0); also the Bonferroni interval for
the 17 pre-registered families and the two halves of the window.

A secondary family ``<family>~team_placebo`` (added after the first look,
not pre-registered) puts on the same rows, with the same k, the sides' own
latest residuals against OTHER opponents in place of the pair's: a gain
there too means a rating lag, not a pair effect.

Sports and centres (see the evidence doc for what each one approximates):

  football    bet.sofa.centre_replay.walk (SHEET-like centre, as B1 / B2),
              NB log-loss with the installed dispersion table
  tennis      tennis_rating.AsOfRating, mean of the 600 neighbours,
              squared error
  hockey / basketball / volleyball
              score_model's rating centre, regulation total and margin
              (volleyball: points per set), squared error
  cs2         sport_confidence.cs2_walk_forward_rows map_winner p, binary
              log-loss

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_pair_h2h.py \\
        --sport {football|tennis|hockey|basketball|volleyball|cs2} \\
        [--from 2025-08-01] [--to 2026-10-12] [--json-out f]
"""

from __future__ import annotations

import argparse
import json
import math
import pickle
import sys
import time
from array import array
from collections import defaultdict, deque
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO / "src"), str(_REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

FloatArr = npt.NDArray[np.float64]

MAX_GAP_DAYS = 1095
K_MAX = 5
SHORT_GAP_DAYS = 30
COUNT_FLOOR = 0.05
P_CLIP = (0.01, 0.99)
N_BOOT = 2000
SEED = 0
N_FAMILIES = 17
K_GRID: tuple[float, ...] = (0.5, 1, 2, 3, 5, 8, 12, 20, 30, 50, 80, 120, 200,
                             300, 500, 1000, math.inf)
FOOTBALL_MARKETS: tuple[str, ...] = (
    "goals_for", "goals_total", "corners_for", "corners_total", "shots_for",
    "shots_total", "cards_points_for", "cards_points_total")
HALF_CUT = "2026-03"


# ------------------------------------------------------------ pure helpers


def day_ts(day: str) -> int:
    return int(datetime.fromisoformat(day).replace(tzinfo=UTC).timestamp())


def months(start: str, end: str) -> list[tuple[str, int, int]]:
    """(YYYY-MM, first ts, next first ts) covering [start, end] by UTC day."""
    d = date.fromisoformat(start).replace(day=1)
    first = date.fromisoformat(start)
    stop = date.fromisoformat(end) + timedelta(days=1)
    out = []
    while d < stop:
        nxt = (d.replace(day=28) + timedelta(days=4)).replace(day=1)
        out.append((d.strftime("%Y-%m"), day_ts(max(d, first).isoformat()),
                    day_ts(min(nxt, stop).isoformat())))
        d = nxt
    return out


def pair_key(a: int, b: int) -> tuple[int, int]:
    return (a, b) if a <= b else (b, a)


def shrink_weight(k: int | FloatArr, big_k: float) -> Any:
    """w(k) = k / (k + K); K = inf is no adjustment."""
    if math.isinf(big_k):
        return k * 0.0
    return k / (k + big_k)


class PairMemory:
    """Per unordered pair, its meetings (ts, residual per subject index; nan =
    no residual), oldest first. ``prior`` reads before ``add`` writes, so a
    match never sees itself. Subjects are small ints the collector assigns
    (e.g. a market's side relative to the pair's lower id)."""

    def __init__(self, n_subjects: int, max_gap_days: int = MAX_GAP_DAYS,
                 k_max: int = K_MAX) -> None:
        self.n = n_subjects
        self.max_gap = max_gap_days * 86400
        self.k_max = k_max
        self._by_pair: dict[tuple[int, int], list[tuple[int, array[float]]]] = (
            defaultdict(list))

    def prior(self, pair: tuple[int, int], subject: int, ts: int,
              min_gap_s: int = 0) -> list[tuple[int, float]]:
        """(ts, residual) of the subject's latest meetings strictly before
        ``ts`` - inside the window, at least ``min_gap_s`` before - newest
        first, at most k_max."""
        out: list[tuple[int, float]] = []
        for m_ts, res in reversed(self._by_pair.get(pair, ())):
            if m_ts >= ts or ts - m_ts < min_gap_s:
                continue
            if ts - m_ts > self.max_gap:
                break
            r = res[subject]
            if math.isnan(r):
                continue
            out.append((m_ts, r))
            if len(out) >= self.k_max:
                break
        return out

    def add(self, pair: tuple[int, int], ts: int,
            residuals: Mapping[int, float]) -> None:
        arr = array("d", [math.nan] * self.n)
        for i, r in residuals.items():
            arr[i] = r
        meetings = self._by_pair[pair]
        meetings.append((ts, arr))
        if len(meetings) > 4 * self.k_max:
            del meetings[: len(meetings) - 2 * self.k_max]


def summarise(prior_all: Sequence[tuple[int, float]],
              prior_30: Sequence[tuple[int, float]]
              ) -> tuple[int, float, int, float]:
    """(k, mean residual, k of meetings >= SHORT_GAP_DAYS old, their mean)."""
    k, k30 = len(prior_all), len(prior_30)
    return (k, sum(r for _, r in prior_all) / k if k else 0.0,
            k30, sum(r for _, r in prior_30) / k30 if k30 else 0.0)


def pair_id(pair: tuple[int, int]) -> int:
    return (pair[0] << 32) | (pair[1] & 0xFFFFFFFF)


class Columns:
    """One family's rows with k >= 1 (columnar, compact) and the census of
    every row with a centre inside the evaluation window."""

    def __init__(self, start_ts: int, end_ts: int) -> None:
        self.start_ts, self.end_ts = start_ts, end_ts
        self.group: array[int] = array("q")
        self.pair: array[int] = array("q")
        self.ts: array[int] = array("q")
        self.centre: array[float] = array("d")
        self.y: array[float] = array("d")
        self.alpha: array[float] = array("d")
        self.k: array[float] = array("d")
        self.rbar: array[float] = array("d")
        self.k30: array[float] = array("d")
        self.rbar30: array[float] = array("d")
        self.window_rows = 0
        self.window_groups: set[int] = set()

    def add(self, group: int, pair: tuple[int, int], ts: int, centre: float,
            y: float, prior_all: Sequence[tuple[int, float]],
            prior_30: Sequence[tuple[int, float]], alpha: float = 0.0) -> None:
        if self.start_ts <= ts < self.end_ts:
            self.window_rows += 1
            self.window_groups.add(group)
        if not prior_all:
            return
        k, rbar, k30, rbar30 = summarise(prior_all, prior_30)
        self.group.append(group)
        self.pair.append(pair_id(pair))
        self.ts.append(ts)
        self.centre.append(centre)
        self.y.append(y)
        self.alpha.append(alpha)
        self.k.append(float(k))
        self.rbar.append(rbar)
        self.k30.append(float(k30))
        self.rbar30.append(rbar30)

    def __len__(self) -> int:
        return len(self.ts)


def loss_vec(kind: str, y: FloatArr, mu: FloatArr, alpha: FloatArr) -> FloatArr:
    """Per-row loss. ``nb``: NB negative log-likelihood up to terms that do
    not depend on mu (they cancel in every difference and in the fit);
    ``se``: squared error; ``bin``: binary log-loss of p = mu."""
    if kind == "se":
        out: FloatArr = (y - mu) ** 2
        return out
    if kind == "bin":
        p = np.clip(mu, P_CLIP[0], P_CLIP[1])
        out = -(y * np.log(p) + (1 - y) * np.log(1 - p))
        return out
    if kind == "nb":
        m = np.maximum(mu, COUNT_FLOOR)
        a = np.maximum(alpha, 1e-9)
        r = 1.0 / a
        nb = -(r * np.log(r / (r + m)) + y * np.log(m / (r + m)))
        pois = -(y * np.log(m) - m)
        out = np.where(alpha <= 1e-9, pois, nb)
        return out
    raise ValueError(kind)


def nb_constant(y: FloatArr, alpha: FloatArr) -> FloatArr:
    """The NB log-likelihood's terms ``loss_vec`` leaves out (they do not
    depend on the mean): loss_vec + nb_constant is the full -log P(Y = y)."""
    out = np.empty(len(y))
    for i, (yi, ai) in enumerate(zip(y.tolist(), alpha.tolist(), strict=True)):
        if ai <= 1e-9:
            out[i] = math.lgamma(yi + 1)
        else:
            r = 1.0 / ai
            out[i] = -(math.lgamma(yi + r) - math.lgamma(r) - math.lgamma(yi + 1))
    return out


def adjust(kind: str, centre: FloatArr, rbar: FloatArr, k: FloatArr,
           big_k: float) -> FloatArr:
    out: FloatArr = centre + shrink_weight(k, big_k) * rbar
    if kind == "nb":
        out = np.maximum(out, COUNT_FLOOR)
    elif kind == "bin":
        out = np.clip(out, P_CLIP[0], P_CLIP[1])
    return out


def fit_big_k(kind: str, y: FloatArr, centre: FloatArr, alpha: FloatArr,
              k: FloatArr, rbar: FloatArr, grid: Sequence[float] = K_GRID
              ) -> float:
    """The grid K minimising the summed loss of the adjusted centre; inf
    (no adjustment) when there are no rows or it wins."""
    if len(y) == 0:
        return math.inf
    best, best_loss = math.inf, math.inf
    for big_k in grid:
        total = float(loss_vec(kind, y, adjust(kind, centre, rbar, k, big_k),
                               alpha).sum())
        if total < best_loss - 1e-12:
            best, best_loss = big_k, total
    return best


def boot_groups(groups: npt.ArrayLike, values: FloatArr,
                extra: Mapping[str, FloatArr] | None = None,
                n_boot: int = N_BOOT, seed: int = SEED,
                q: Sequence[float] = (0.025, 0.975)) -> dict[str, Any]:
    """Mean of ``values`` per row and its quantiles from resampling groups
    (a group's rows go together)."""
    if len(values) == 0:
        return {"mean": None, "q": [None] * len(q), "rows": 0, "groups": 0}
    keys, inv = np.unique(np.asarray(groups), return_inverse=True)
    sums = np.bincount(inv, weights=values)
    counts = np.bincount(inv).astype(float)
    rng = np.random.default_rng(seed)
    stats = np.empty(n_boot)
    for b in range(n_boot):
        idx = rng.integers(0, len(keys), len(keys))
        stats[b] = sums[idx].sum() / counts[idx].sum()
    return {"mean": float(sums.sum() / counts.sum()),
            "q": [float(v) for v in np.quantile(stats, q)],
            "rows": int(counts.sum()), "groups": int(len(keys))}


def ols_slope(x: FloatArr, y: FloatArr) -> float:
    """Slope of y on x with an intercept; nan when x has no spread."""
    if len(x) < 2:
        return float("nan")
    xc = x - x.mean()
    sxx = float((xc * xc).sum())
    return float((xc * (y - y.mean())).sum() / sxx) if sxx > 0 else float("nan")


def boot_slope(groups: npt.ArrayLike, x: FloatArr, y: FloatArr,
               n_boot: int = N_BOOT, seed: int = SEED) -> dict[str, Any]:
    if len(x) < 2:
        return {"slope": None, "q": [None, None]}
    keys, inv = np.unique(np.asarray(groups), return_inverse=True)
    sx = np.bincount(inv, weights=x)
    sy = np.bincount(inv, weights=y)
    sxx = np.bincount(inv, weights=x * x)
    sxy = np.bincount(inv, weights=x * y)
    n = np.bincount(inv).astype(float)
    rng = np.random.default_rng(seed)
    stats = np.empty(n_boot)
    for b in range(n_boot):
        idx = rng.integers(0, len(keys), len(keys))
        nn, ax, ay = n[idx].sum(), sx[idx].sum(), sy[idx].sum()
        den = sxx[idx].sum() - ax * ax / nn
        stats[b] = (sxy[idx].sum() - ax * ay / nn) / den if den > 0 else np.nan
    lo, hi = np.nanquantile(stats, [0.025, 0.975])
    return {"slope": ols_slope(x, y), "q": [float(lo), float(hi)]}


def evaluate(cols: Columns, kind: str, start: str, end: str,
             short_gap: bool = False) -> dict[str, Any]:
    """Walk-forward by month: K from the rows strictly before the month's
    first day, applied to the month's rows. ``short_gap``: only meetings at
    least SHORT_GAP_DAYS before today (k30 / rbar30)."""
    if len(cols) == 0:
        return {"rows": 0}
    ts = np.frombuffer(cols.ts, dtype=np.int64)
    y = np.frombuffer(cols.y, dtype=float)
    c = np.frombuffer(cols.centre, dtype=float)
    a = np.frombuffer(cols.alpha, dtype=float)
    k = np.frombuffer(cols.k30 if short_gap else cols.k, dtype=float)
    rb = np.frombuffer(cols.rbar30 if short_gap else cols.rbar, dtype=float)
    grp = np.frombuffer(cols.group, dtype=np.int64)
    pid = np.frombuffer(cols.pair, dtype=np.int64)
    keep = k >= 1
    ts, grp, pid = ts[keep], grp[keep], pid[keep]
    y, c, a, k, rb = y[keep], c[keep], a[keep], k[keep], rb[keep]
    diff_parts: list[FloatArr] = []
    idx_parts: list[npt.NDArray[np.intp]] = []
    fitted: dict[str, float] = {}
    for label, lo, hi in months(start, end):
        train = ts < lo
        big_k = fit_big_k(kind, y[train], c[train], a[train], k[train], rb[train])
        fitted[label] = big_k
        test = np.nonzero((ts >= lo) & (ts < hi))[0]
        if len(test) == 0:
            continue
        old = loss_vec(kind, y[test], c[test], a[test])
        new = loss_vec(kind, y[test], adjust(kind, c[test], rb[test], k[test],
                                             big_k), a[test])
        diff_parts.append(new - old)
        idx_parts.append(test)
    if not idx_parts:
        return {"rows": 0}
    idx = np.concatenate(idx_parts)
    diff = np.concatenate(diff_parts)
    g = grp[idx]
    first = ts[idx] < day_ts(f"{HALF_CUT}-01")
    bonf = 0.05 / N_FAMILIES
    main = boot_groups(g, diff, q=(0.025, 0.975, bonf / 2, 1 - bonf / 2))
    resid = y[idx] - c[idx]
    out: dict[str, Any] = {
        "rows": main["rows"], "matches": main["groups"],
        "pairs": int(len(np.unique(pid[idx]))),
        "d_loss": [main["mean"], main["q"][0], main["q"][1]],
        "d_loss_bonferroni": [main["q"][2], main["q"][3]],
        "loss_old": float((loss_vec(kind, y[idx], c[idx], a[idx]) + (
            nb_constant(y[idx], a[idx]) if kind == "nb" else 0.0)).mean()),
        "halves": {
            f"..{HALF_CUT}": _short(boot_groups(g[first], diff[first])),
            f"{HALF_CUT}..": _short(boot_groups(g[~first], diff[~first]))},
        "slope_resid_on_rbar": boot_slope(g, rb[idx], resid),
        "k_distribution": {str(int(v)): int((k[idx] == v).sum())
                           for v in np.unique(k[idx])},
        "K_by_month": {m: ("inf" if math.isinf(v) else v)
                       for m, v in fitted.items()},
    }
    if kind == "se":
        out["mse_old"] = out["loss_old"]
    else:
        out["mse_old"] = float((resid ** 2).mean())
    return out


def _short(b: Mapping[str, Any]) -> list[Any]:
    return [b["mean"], b["q"][0], b["q"][1], b["groups"]]


def verdict(res: Mapping[str, Any]) -> str:
    """The pre-registered reading of one family's result."""
    d = res.get("d_loss")
    if not d or d[0] is None:
        return "NO_DATA"
    if d[2] >= 0:
        return "NO_GAIN"
    bonf_ok = res["d_loss_bonferroni"][1] < 0
    halves = [h[0] for h in res["halves"].values() if h[0] is not None]
    same_sign = len(halves) == 2 and all(h < 0 for h in halves)
    return "CANDIDATE" if bonf_ok and same_sign else "MAY_BE_CHANCE"


# ------------------------------------------------------------ collectors


PLACEBO = "~team_placebo"
PLACEBO_DEPTH = 3 * K_MAX
# (team, sign): a placebo reads each owner's own recent residuals against
# other opponents; ``diff`` sums sign x mean (a margin), else the mean of the
# owners' means (a total, or one side).
Owners = tuple[tuple[int, float], ...]


def placebo_value(recent: Mapping[int, Sequence[tuple[int, float]]],
                  owners: Owners, pair: tuple[int, int], k: int, diff: bool
                  ) -> float | None:
    """The placebo's prior mean: each owner's latest k residuals (oldest
    first in ``recent``, (opponent, residual)) from matches NOT against the
    other member of the pair; None if an owner has none."""
    means: list[float] = []
    for team, sign in owners:
        opp = pair[1] if team == pair[0] else pair[0]
        vals = [v for o, v in recent.get(team, ()) if o != opp][-k:]
        if not vals:
            return None
        means.append(sign * sum(vals) / len(vals))
    return sum(means) if diff else sum(means) / len(means)


class Collector:
    """The families' columns, the pair memory of one sport's walk and the
    sides' own recent residuals the placebo reads (secondary, not
    pre-registered: does a side's residual against ANY opponent predict as
    well as the pair's? then the persistence is a rating lag, not a pair
    effect)."""

    def __init__(self, n_subjects: int, start_ts: int, end_ts: int) -> None:
        self.memory = PairMemory(n_subjects)
        self.start_ts, self.end_ts = start_ts, end_ts
        self.cols: dict[str, Columns] = {}
        self.recent: dict[str, dict[int, deque[tuple[int, float]]]] = (
            defaultdict(lambda: defaultdict(lambda: deque(maxlen=PLACEBO_DEPTH))))

    def _cols(self, family: str) -> Columns:
        cols = self.cols.get(family)
        if cols is None:
            cols = self.cols[family] = Columns(self.start_ts, self.end_ts)
        return cols

    def record(self, family: str, pair: tuple[int, int], subject: int,
               group: int, ts: int, centre: float, y: float,
               alpha: float = 0.0, owners: Owners = (), diff: bool = False
               ) -> float:
        """Read the subject's prior meetings into the family's columns (and
        the placebo's, same rows, same k) and return today's residual (the
        caller files it with ``memory.add`` and ``note``)."""
        prior = self.memory.prior(pair, subject, ts)
        self.place(family, pair, group, ts, centre, y, prior,
                   self.memory.prior(pair, subject, ts, SHORT_GAP_DAYS * 86400),
                   alpha, owners, diff)
        return y - centre

    def place(self, family: str, pair: tuple[int, int], group: int, ts: int,
              centre: float, y: float, prior: Sequence[tuple[int, float]],
              prior30: Sequence[tuple[int, float]], alpha: float = 0.0,
              owners: Owners = (), diff: bool = False) -> None:
        self._cols(family).add(group, pair, ts, centre, y, prior, prior30, alpha)
        if prior and owners:
            ctl = placebo_value(self.recent[family], owners, pair, len(prior),
                                diff)
            if ctl is not None:
                fake = [(0, ctl)] * len(prior)
                self._cols(family + PLACEBO).add(group, pair, ts, centre, y,
                                                 fake, fake, alpha)

    def note(self, family: str, team: int, opp: int, residual: float) -> None:
        """File a side's own residual (oriented to it) for the placebo."""
        self.recent[family][team].append((opp, residual))


def side_subject(base: int, team: int, pair: tuple[int, int]) -> int:
    """A per-side subject: ``base`` for the pair's lower id, base + 1 else."""
    return base if team == pair[0] else base + 1


def collect_football(db: str, coll: Collector) -> None:
    from bet.sofa import centre_replay as cr
    from bet.sofa import count_dispersion
    from bet.sofa import football_rating as fr
    from scripts.sofa.measure_game_state import k_table, live_centre

    cache = Path(db).parent / "cache" / "football_history.pkl"
    history: list[fr.FootballResult]
    if cache.exists():  # read only; never rewritten here
        _, history = pickle.loads(cache.read_bytes())
    else:  # parse without writing a cache
        history = fr.load_history(db)
    table = count_dispersion.load_table()
    print(f"football history {len(history)}", flush=True)
    index = {m: 2 * i for i, m in enumerate(FOOTBALL_MARKETS)}
    teams = {r.event_id: (r.home_id, r.away_id) for r in history}
    current: int | None = None
    pending: dict[int, float] = {}
    pending_ts = 0

    def flush() -> None:
        if current is not None and pending:
            coll.memory.add(pair_key(*teams[current]), pending_ts, pending)

    for row in cr.walk(history, 0, coll.end_ts, FOOTBALL_MARKETS,
                       k_table(FOOTBALL_MARKETS)):
        if row.event_id != current:
            flush()
            current, pending, pending_ts = row.event_id, {}, row.ts
        h, a = teams[row.event_id]
        pair = pair_key(h, a)
        disp = table.read("football", row.market, row.competition_id)
        alpha = disp.alpha if disp is not None else 0.0
        if row.side:
            team = h if row.side == "side_a" else a
            subject = side_subject(index[row.market], team, pair)
            res = coll.record(row.market, pair, subject, row.event_id, row.ts,
                              live_centre(row), row.y, alpha, ((team, 1.0),))
            coll.note(row.market, team, a if team == h else h, res)
        else:
            subject = index[row.market]
            res = coll.record(row.market, pair, subject, row.event_id, row.ts,
                              live_centre(row), row.y, alpha,
                              ((h, 1.0), (a, 1.0)))
            coll.note(row.market, h, a, res)
            coll.note(row.market, a, h, res)
        pending[subject] = res
    flush()


def collect_tennis(db: str, coll: Collector) -> None:
    from bet.sofa import tennis_rating as tr
    from scripts.sofa.measure_tennis_outcome_model import is_team_cup, load

    history, meta = load(db)
    loaded = tr.load_coefficients()
    if loaded is None:
        raise SystemExit("no config/tennis_rating.json")
    coefficients, cfg = loaded
    rating = tr.AsOfRating(history, coefficients, cfg["features"], True,
                           cfg.get("tier_start"))
    count: dict[tuple[int, int], int] = defaultdict(int)
    for r in history:
        count[pair_key(r.home_id, r.away_id)] += 1
    print(f"tennis history {len(history)}, pairs met twice+ "
          f"{sum(1 for v in count.values() if v > 1)}", flush=True)
    for r in history:
        if r.ts >= coll.end_ts:
            break
        pair = pair_key(r.home_id, r.away_id)
        if not r.completed or len(r.sets) > 3:
            continue
        if max(sum(a > b for a, b in r.sets), sum(b > a for a, b in r.sets)) != 2:
            continue
        cat, text = meta.get(r.event_id, ("", ""))
        if is_team_cup(text):
            continue
        day = r.ts - r.ts % 86400
        fc = rating.model_at(day).forecast(r.home_id, r.away_id, cat, r.surface,
                                           datetime.fromtimestamp(r.ts, UTC))
        if fc is None or not fc.neighbours_home or not fc.neighbours_away:
            continue
        nh, na = fc.neighbours_home, fc.neighbours_away
        gh = float(sum(a for a, _ in r.sets))
        ga = float(sum(b for _, b in r.sets))
        res: dict[int, float] = {}
        c_tot = sum(o.games_for + o.games_against for o in nh) / len(nh)
        h, a = r.home_id, r.away_id
        res[0] = coll.record("games_total", pair, 0, r.event_id, r.ts, c_tot,
                             gh + ga, owners=((h, 1.0), (a, 1.0)))
        coll.note("games_total", h, a, res[0])
        coll.note("games_total", a, h, res[0])
        for pid, opp, pool, y in ((h, a, nh, gh), (a, h, na, ga)):
            subject = side_subject(1, pid, pair)
            c_side = sum(o.games_for for o in pool) / len(pool)
            res[subject] = coll.record("games_won_for", pair, subject,
                                       r.event_id, r.ts, c_side, y,
                                       owners=((pid, 1.0),))
            coll.note("games_won_for", pid, opp, res[subject])
        coll.memory.add(pair, r.ts, res)


def collect_score(db: str, sport_key: str, coll: Collector,
                  burn_in_days: int = 180) -> None:
    from bet.sofa import score_model as sm
    from bet.sofa.shadow import SPORTS

    sport = next(v for k, v in SPORTS.items() if k == sport_key)
    history = sm.load_history(db, sport)
    print(f"{sport_key} history {len(history)}", flush=True)
    if not history:
        return
    metric = sm._metrics(sport)[0]
    cut = history[0].ts + burn_in_days * 86400
    model = sm.build_model(history, sport, cut)
    for r in history:
        if r.ts < cut:
            continue
        if r.ts >= coll.end_ts:
            break
        exp = model.expected(r.competition_id, r.home_id, r.away_id, r.ts)
        if exp is not None and metric in r.values:
            eh, ea = sum(exp[0]), sum(exp[1])
            vh, va = r.values[metric]
            pair = pair_key(r.home_id, r.away_id)
            # the margin is read from the pair's lower id's side
            sign = 1.0 if r.home_id == pair[0] else -1.0
            lower, other = pair
            res_t = coll.record("total", pair, 0, r.event_id, r.ts, eh + ea,
                                vh + va, owners=((lower, 1.0), (other, 1.0)))
            res_m = coll.record("margin", pair, 1, r.event_id, r.ts,
                                sign * (eh - ea), sign * (vh - va),
                                owners=((lower, 1.0), (other, -1.0)), diff=True)
            coll.memory.add(pair, r.ts, {0: res_t, 1: res_m})
            # every side's own residuals, the margin from its own side
            for team, opp, own in ((lower, other, 1.0), (other, lower, -1.0)):
                coll.note("total", team, opp, res_t)
                coll.note("margin", team, opp, own * res_m)
        model.book.update(sm._rated_values(r, sport))


def collect_cs2(db: str, coll: Collector) -> None:
    from bet.sofa import sport_confidence as scf

    maps, series = scf.load_cs2(db, coll.end_ts)
    teams: dict[int, tuple[int, int]] = {}
    starts: dict[int, int] = {}
    for m in maps:
        teams.setdefault(m.event_id, (m.home_id, m.away_id))
        starts.setdefault(m.event_id, m.start_ts)
    rows = scf.cs2_walk_forward_rows(maps, series, 0, coll.end_ts, "m", True,
                                     False)
    by_series: dict[int, list[tuple[int, float, int]]] = defaultdict(list)
    for r in rows:
        if r["family"] != "map_winner" or r["side"] != "T1":
            continue
        eid = int(str(r["game"]).split(":")[-1])
        by_series[eid].append((int(r["period"]), float(r["p"]), int(r["y"])))
    print(f"cs2 maps {len(maps)}, series with map_winner rows {len(by_series)}",
          flush=True)
    for eid in sorted(by_series, key=lambda e: (starts.get(e, 0), e)):
        h, a = teams[eid]
        pair = pair_key(h, a)
        # residuals are kept from the pair's lower id's side; today's p is
        # the home side's, so the prior mean is turned to it by `sign`
        sign = 1.0 if h == pair[0] else -1.0
        ts = starts[eid]
        prior = [(t, sign * v) for t, v in coll.memory.prior(pair, 0, ts)]
        prior30 = [(t, sign * v) for t, v in
                   coll.memory.prior(pair, 0, ts, SHORT_GAP_DAYS * 86400)]
        rs: list[float] = []
        for _order, p, y in sorted(by_series[eid]):
            coll.place("map_winner", pair, eid, ts, p, float(y), prior, prior30,
                       owners=((h, 1.0), (a, -1.0)), diff=True)
            rs.append(sign * (y - p))
        r_low = sum(rs) / len(rs)
        coll.note("map_winner", pair[0], pair[1], r_low)
        coll.note("map_winner", pair[1], pair[0], -r_low)
        coll.memory.add(pair, ts, {0: sum(rs) / len(rs)})


KIND = {"football": "nb", "tennis": "se", "hockey": "se", "basketball": "se",
        "volleyball": "se", "cs2": "bin"}
SUBJECTS = {"football": 2 * len(FOOTBALL_MARKETS), "tennis": 3, "hockey": 2,
            "basketball": 2, "volleyball": 2, "cs2": 1}


def run(sport: str, db: str, start: str, end: str) -> dict[str, Any]:
    start_ts, end_ts = day_ts(start), day_ts(end) + 86400
    coll = Collector(SUBJECTS[sport], start_ts, end_ts)
    collectors: dict[str, Callable[[], None]] = {
        "football": lambda: collect_football(db, coll),
        "tennis": lambda: collect_tennis(db, coll),
        "cs2": lambda: collect_cs2(db, coll),
        "hockey": lambda: collect_score(db, "hockey", coll),
        "basketball": lambda: collect_score(db, "basketball", coll),
        "volleyball": lambda: collect_score(db, "volleyball", coll),
    }
    t0 = time.time()
    collectors[sport]()
    print(f"{sport}: walk done ({time.time() - t0:.0f}s)", flush=True)
    out: dict[str, Any] = {"sport": sport, "window": [start, end],
                           "metric": KIND[sport], "families": {}}
    for fam, cols in sorted(coll.cols.items()):
        res = evaluate(cols, KIND[sport], start, end)
        res["window_rows_with_centre"] = cols.window_rows
        res["window_matches_with_centre"] = len(cols.window_groups)
        res["verdict"] = verdict(res) if res.get("rows") else "NO_DATA"
        res["no_short_gap"] = evaluate(cols, KIND[sport], start, end,
                                       short_gap=True)
        out["families"][fam] = res
        print(fam, json.dumps({k: v for k, v in res.items()
                               if k != "K_by_month"}), flush=True)
    return out


def main() -> int:
    from bet.sofa.config import SofaConfig

    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--sport", choices=sorted(KIND), required=True)
    ap.add_argument("--from", dest="start", default=None)
    ap.add_argument("--to", dest="end", default="2026-10-12")
    ap.add_argument("--json-out")
    args = ap.parse_args()
    start = args.start or ("2026-01-01" if args.sport == "cs2" else "2025-08-01")
    db = str(SofaConfig.from_env().db_path)
    result = run(args.sport, db, start, args.end)
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(result, indent=1),
                                       encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
