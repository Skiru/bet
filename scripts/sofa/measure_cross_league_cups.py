#!/usr/bin/env python3
"""Read-only measurement: does the football rating mis-rank sides from
different leagues in international club competitions?

Question (2026-10-15 build): on UEFA / AFC cup fixtures the analysts vetoed
legs where the rating put the side from the weaker league level with or above
the stronger one (Lech - Leverkusen 1X2 0.48 / 0.29), while the league
strength book gave near-zero gaps (POL-GER -0.09). Is that a systematic bias
on the history, and would a refitted gap fix it?

Nothing is written to the database or to config/. The football history is
the parsed pickle SHEET keeps (``data/cache/football_history.pkl``, read
only; friendlies out, second squads marked, league units assigned). With
``--db`` competition names are read from ``sofa_tournament_map`` (``mode=ro``).

Replay, as of each match: one ``football_rating.RatingBook`` with the shared-
league link rule (on since 2026-10-07) is updated on goals_for in time order;
every match of an international club competition (``INTL_COMPS``) is priced
BEFORE its kick-off time group is fed to the book. A row is cross-league when
both sides have a domain (modal league unit inside the link window) and the
two domains belong to different competitions, neither of them a cup of
``INTL_COMPS``. Its centres are the rating's pure goals_for centres
(``FootballForecast.centre``: league rate x strength factor x ratios^0.6),
the 1X2 from independent NB goals with the installed r
(``config/sofa_football_result.json``) - the arithmetic SHEET's
``result_1x2`` rows use.

League-strength proxy from the data alone (``CupLeagueElo``): an Elo on goal
difference over earlier cross-league international club matches - each
domestic competition s_c, expected home GD = s_h - s_a + home advantage
(the running mean home GD of these matches), s moved by ETA_ELO x the
surprise. Read only once both competitions have MIN_CUP_MATCHES matches.

Variants of the 1X2 (hyper-parameters chosen on TRAIN, scored on TEST):
  A  base     SHEET's centres as they are
  B  scaled   log gap x c and the cross-league ratio power k refitted
  C  proxy    log gap + b x (Elo gap in goals)
  D  cupgap   log gap + (d_h - d_a), d per domestic competition learnt
              online from cup matches only (step eta) on D's own residual
Log-loss of each against A on TEST, match bootstrap 95%.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_cross_league_cups.py \\
        --db data/sofa.db --json-out <f> --md-out <f>
"""

from __future__ import annotations

import argparse
import json
import math
import pickle
import sqlite3
import sys
from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from bet.sofa import football_rating as fr
from bet.sofa.football_result import count_pmf, load_config, market_probs, score_grid

F64 = NDArray[np.float64]

DEFAULT_HISTORY = Path("data/cache/football_history.pkl")
INTL_COMPS: dict[int, str] = {
    7: "UEFA Champions League",
    679: "UEFA Europa League",
    17015: "UEFA Conference League",
    463: "AFC Champions League Elite",
    668: "AFC Champions League Two",
    384: "CONMEBOL Libertadores",
    480: "CONMEBOL Sudamericana",
    1054: "CAF Champions League",
    498: "CONCACAF Champions Cup",
}
CONFEDERATION: dict[int, str] = {
    7: "UEFA", 679: "UEFA", 17015: "UEFA", 463: "AFC", 668: "AFC",
    384: "CONMEBOL", 480: "CONMEBOL", 1054: "CAF", 498: "CONCACAF",
}
METRIC = "goals_for"
FROM_DAY = "2024-07-01"   # the cups are densely cached from here on
TEST_FROM = "2025-07-01"  # 2025/26 and 2026/27 seasons
ETA_ELO = 0.05            # chosen, not fitted
MIN_CUP_MATCHES = 10
REPS = 1000
SEED = 11
GRID_C = (0.0, 0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0)
GRID_K = (0.4, 0.5, 0.6, 0.7, 0.8, 1.0)
GRID_B = (0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.7, 1.0)
GRID_ETA = (0.0, 0.02, 0.05, 0.1, 0.2)
# The 2026-10-15 cases: (weaker-by-book-reading side's league, opponent's)
# Lech - Leverkusen, Celje - Omonia, CSKA Sofia - Monaco, Egnatia - Midtjylland.
CITED_PAIRS: tuple[tuple[int, int, str], ...] = (
    (202, 35, "POL-GER"), (212, 171, "SLO-CYP"), (247, 34, "BUL-FRA"),
    (720, 39, "ALB-DEN"))
PROXY_BINS = (0.0, 0.2, 0.5, 1.0, math.inf)   # |Elo gap|, goals a match
BOOK_BINS = (0.0, 0.1, 0.2, 0.4, math.inf)    # |log strength gap|


def ts_of(day: str) -> int:
    return int(datetime.fromisoformat(day).replace(tzinfo=UTC).timestamp())


def note(msg: str) -> None:
    print(f"[{datetime.now(UTC):%H:%M:%S}] {msg}", file=sys.stderr, flush=True)


# --------------------------------------------------------------------------
# pure pieces
# --------------------------------------------------------------------------


@dataclass
class CupLeagueElo:
    """A league's strength from its clubs' goal difference against other
    leagues' clubs in international club matches - nothing outside the data."""

    eta: float = ETA_ELO
    s: dict[int, float] = field(default_factory=lambda: defaultdict(float))
    n: dict[int, int] = field(default_factory=lambda: defaultdict(int))
    hfa_sum: float = 0.0
    hfa_n: int = 0

    @property
    def hfa(self) -> float:
        return self.hfa_sum / self.hfa_n if self.hfa_n else 0.0

    def gap(self, home: int, away: int, min_n: int = MIN_CUP_MATCHES) -> float | None:
        """s_home - s_away (goals a match, no home advantage), None if thin."""
        if self.n.get(home, 0) < min_n or self.n.get(away, 0) < min_n:
            return None
        return self.s.get(home, 0.0) - self.s.get(away, 0.0)

    def update(self, home: int, away: int, gd: float) -> None:
        if home == away:
            return
        err = gd - (self.s[home] - self.s[away] + self.hfa)
        self.s[home] += self.eta * err
        self.s[away] -= self.eta * err
        self.n[home] += 1
        self.n[away] += 1
        self.hfa_sum += gd
        self.hfa_n += 1


def centres(
    rate_h: float, rate_a: float, att_h: float, def_h: float,
    att_a: float, def_a: float, log_gap: float, power: float,
) -> tuple[float, float]:
    """The rating's goal centres (``RatingBook.expected``) for a given log
    strength gap and cross-league ratio power."""
    f = math.exp(log_gap)
    return (rate_h * f * (att_h * def_a) ** power,
            rate_a / f * (att_a * def_h) ** power)


def probs_1x2(lh: F64, la: F64, r: float) -> F64:
    """(N, 3) home / draw / away from independent NB goals."""
    res: F64 = market_probs(score_grid(count_pmf(lh, r), count_pmf(la, r)))
    return res


def outcome_index(x: float, y: float) -> int:
    return 0 if x > y else (2 if x < y else 1)


def log_losses(p: F64, outcome: NDArray[np.int64]) -> F64:
    picked = p[np.arange(len(outcome)), outcome]
    out: F64 = -np.log(np.clip(picked, 1e-12, 1.0))
    return out


def bin_of(value: float, edges: Sequence[float]) -> int:
    """Index of the half-open bin [edges[i], edges[i+1]) holding |value|."""
    v = abs(value)
    for i in range(len(edges) - 1):
        if edges[i] <= v < edges[i + 1]:
            return i
    return len(edges) - 2


def bin_label(edges: Sequence[float], i: int) -> str:
    hi = edges[i + 1]
    return f"{edges[i]:g}-{hi:g}" if math.isfinite(hi) else f">={edges[i]:g}"


def bootstrap_mean(
    v: F64, reps: int = REPS, seed: int = SEED,
) -> tuple[float, float, float]:
    """(mean, lo95, hi95) over matches resampled with replacement."""
    if len(v) == 0:
        return (math.nan, math.nan, math.nan)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(v), (reps, len(v)))
    means = v[idx].mean(axis=1)
    return (float(v.mean()), float(np.percentile(means, 2.5)),
            float(np.percentile(means, 97.5)))


# --------------------------------------------------------------------------
# replay
# --------------------------------------------------------------------------


ROW_KEYS = ("ts", "eid", "comp", "dh", "da", "ch", "ca", "status", "lf",
            "rate_h", "rate_a", "att_h", "def_h", "att_a", "def_a", "ok",
            "lh", "la", "x", "y")
STATUSES = (fr.LINKED, fr.LINKED_BY_STRENGTH, fr.UNLINKED)


@dataclass
class ReplayOut:
    rows: list[dict[str, float]]
    excluded: dict[str, int]
    book: fr.RatingBook


def _price(book: fr.RatingBook, r: fr.FootballResult) -> dict[str, float] | str:
    """The match's row as of now, or the reason it is not a cross-league row."""
    if r.women:
        return "women"
    if r.home_reserve or r.away_reserve:
        return "reserve"
    if METRIC not in r.values:
        return "no_goals"
    dh, da = book.domain(r.home_id), book.domain(r.away_id)
    if dh is None or da is None:
        return "no_domain"
    ch, ca = book.unit_competition(dh), book.unit_competition(da)
    if ch in INTL_COMPS or ca in INTL_COMPS:
        return "domain_is_a_cup"
    if ch == ca:
        return "same_league"
    status, lf = book.link(r.home_id, r.away_id, METRIC)
    rates = book.league_rates(r.competition_id, METRIC)
    th = book.teams[(r.home_id, METRIC)]
    ta = book.teams[(r.away_id, METRIC)]
    fc = fr.FootballForecast(book, r.competition_id, r.home_id, r.away_id)
    ch_c, ca_c = fc.centre(METRIC, "side_a"), fc.centre(METRIC, "side_b")
    ok = ch_c is not None and ca_c is not None and rates is not None
    x, y = r.values[METRIC]
    return {
        "ts": float(r.ts), "eid": float(r.event_id), "comp": float(r.competition_id),
        "dh": float(dh), "da": float(da), "ch": float(ch), "ca": float(ca),
        "status": float(STATUSES.index(status)), "lf": lf,
        "rate_h": rates[0] if rates else math.nan,
        "rate_a": rates[1] if rates else math.nan,
        "att_h": th.attack, "def_h": th.defence,
        "att_a": ta.attack, "def_a": ta.defence,
        "ok": float(ok),
        "lh": ch_c[0] if ch_c else math.nan, "la": ca_c[0] if ca_c else math.nan,
        "x": float(x), "y": float(y),
    }


def replay(history: Iterable[fr.FootballResult], from_ts: int) -> ReplayOut:
    book = fr.RatingBook(shared_league_link=True)
    rows: list[dict[str, float]] = []
    excluded: dict[str, int] = defaultdict(int)
    group: list[fr.FootballResult] = []

    def flush() -> None:
        for g in group:
            if g.competition_id in INTL_COMPS and g.ts >= from_ts:
                row = _price(book, g)
                if isinstance(row, str):
                    excluded[row] += 1
                else:
                    rows.append(row)
        for g in group:
            vals = {METRIC: g.values[METRIC]} if METRIC in g.values else {}
            book.update(replace(g, values=vals))
        group.clear()

    for r in history:
        if group and r.ts != group[0].ts:
            flush()
        group.append(r)
    flush()
    return ReplayOut(rows, dict(excluded), book)


# --------------------------------------------------------------------------
# post-processing: proxy and variant D, walk-forward over the cup rows
# --------------------------------------------------------------------------


def walk_cups(
    rows: Sequence[dict[str, float]], etas: Sequence[float],
) -> tuple[CupLeagueElo, dict[float, dict[int, float]]]:
    """Adds ``proxy`` (Elo gap, NaN when thin) and ``d_<eta>`` (variant D's
    log gap correction) to every row, each as of before the row's time group;
    returns the final Elo and D's per-competition corrections."""
    elo = CupLeagueElo()
    delta: dict[float, dict[int, float]] = {e: defaultdict(float) for e in etas}
    i = 0
    while i < len(rows):
        j = i
        while j < len(rows) and rows[j]["ts"] == rows[i]["ts"]:
            j += 1
        grp = rows[i:j]
        for row in grp:
            ch, ca = int(row["ch"]), int(row["ca"])
            g = elo.gap(ch, ca)
            row["proxy"] = math.nan if g is None else g
            for e in etas:
                row[f"d_{e}"] = delta[e][ch] - delta[e][ca]
        for row in grp:
            ch, ca = int(row["ch"]), int(row["ca"])
            elo.update(ch, ca, row["x"] - row["y"])
            if row["ok"] and row["status"] != STATUSES.index(fr.LINKED):
                for e in etas:
                    if e == 0.0:
                        continue
                    lh, la = centres(
                        row["rate_h"], row["rate_a"], row["att_h"], row["def_h"],
                        row["att_a"], row["def_a"], row["lf"] + row[f"d_{e}"],
                        fr.CROSS_RATIO_POWER)
                    resid = (math.log((row["x"] + 0.5) / (lh + 0.5))
                             - math.log((row["y"] + 0.5) / (la + 0.5))) / 2
                    delta[e][ch] += e * resid
                    delta[e][ca] -= e * resid
        i = j
    return elo, delta


def arrays(rows: Sequence[dict[str, float]], keys: Iterable[str]) -> dict[str, F64]:
    return {k: np.asarray([row[k] for row in rows], dtype=np.float64) for k in keys}


Variant = Callable[[dict[str, F64]], tuple[F64, F64]]


def variant_centres(
    a: dict[str, F64], log_gap: F64, power: float = fr.CROSS_RATIO_POWER,
) -> tuple[F64, F64]:
    f = np.exp(log_gap)
    lh: F64 = a["rate_h"] * f * (a["att_h"] * a["def_a"]) ** power
    la: F64 = a["rate_a"] / f * (a["att_a"] * a["def_h"]) ** power
    return lh, la


def ll_of(a: dict[str, F64], lh: F64, la: F64, r_nb: float) -> F64:
    out = np.asarray(a["outcome"], dtype=np.int64)
    return log_losses(probs_1x2(lh, la, r_nb), out)


def fit_variants(train: dict[str, F64], r_nb: float) -> dict[str, dict[str, float]]:
    """Grid-search each variant's hyper-parameters on TRAIN 1X2 log-loss."""
    best: dict[str, dict[str, float]] = {}
    res: list[tuple[float, float, float]] = []
    for c in GRID_C:
        for k in GRID_K:
            lh, la = variant_centres(train, c * train["lf"], k)
            res.append((float(ll_of(train, lh, la, r_nb).mean()), c, k))
    ll, c, k = min(res)
    best["B"] = {"c": c, "k": k, "train_ll": ll}
    proxy = np.nan_to_num(train["proxy"], nan=0.0)
    res2 = []
    for b in GRID_B:
        lh, la = variant_centres(train, train["lf"] + b * proxy)
        res2.append((float(ll_of(train, lh, la, r_nb).mean()), b))
    ll, b = min(res2)
    best["C"] = {"b": b, "train_ll": ll}
    res3 = []
    for e in GRID_ETA:
        lh, la = variant_centres(train, train["lf"] + train[f"d_{e}"])
        res3.append((float(ll_of(train, lh, la, r_nb).mean()), e))
    ll, e = min(res3)
    best["D"] = {"eta": e, "train_ll": ll}
    return best


def variant_ll(a: dict[str, F64], best: dict[str, dict[str, float]],
               r_nb: float) -> dict[str, F64]:
    out = {"A": ll_of(a, a["lh"], a["la"], r_nb)}
    b = best["B"]
    out["B"] = ll_of(a, *variant_centres(a, b["c"] * a["lf"], b["k"]), r_nb)
    proxy = np.nan_to_num(a["proxy"], nan=0.0)
    out["C"] = ll_of(a, *variant_centres(a, a["lf"] + best["C"]["b"] * proxy), r_nb)
    e = best["D"]["eta"]
    out["D"] = ll_of(a, *variant_centres(a, a["lf"] + a[f"d_{e}"]), r_nb)
    return out


# --------------------------------------------------------------------------
# calibration tables, oriented to the side a gap favours
# --------------------------------------------------------------------------


def oriented(a: dict[str, F64], by: F64, r_nb: float) -> dict[str, F64]:
    """Per row, the side `by` favours (>= 0: home) as side S."""
    s_home = by >= 0
    sign = np.where(s_home, 1.0, -1.0)
    p = probs_1x2(a["lh"], a["la"], r_nb)
    out = a["outcome"].astype(np.int64)
    p_s_win = np.where(s_home, p[:, 0], p[:, 2])
    real_s_win = np.where(s_home, out == 0, out == 2).astype(np.float64)
    return {
        "pred_gd": sign * (a["lh"] - a["la"]),
        "real_gd": sign * (a["x"] - a["y"]),
        "pred_gs": np.where(s_home, a["lh"], a["la"]),
        "real_gs": np.where(s_home, a["x"], a["y"]),
        "pred_go": np.where(s_home, a["la"], a["lh"]),
        "real_go": np.where(s_home, a["y"], a["x"]),
        "p_s_win": p_s_win, "real_s_win": real_s_win,
        "p_draw": p[:, 1], "real_draw": (out == 1).astype(np.float64),
        "book_gap_s": sign * a["lf"],
        "proxy_s": sign * np.nan_to_num(a["proxy"], nan=0.0),
        "s_home": s_home.astype(np.float64),
    }


def calib_table(
    a: dict[str, F64], by: F64, edges: Sequence[float], r_nb: float,
) -> list[dict[str, Any]]:
    o = oriented(a, by, r_nb)
    bins = np.asarray([bin_of(v, edges) for v in by])
    out: list[dict[str, Any]] = []
    for i in range(len(edges) - 1):
        m = bins == i
        if not m.any():
            continue
        out.append(_calib_row(bin_label(edges, i), o, m))
    out.append(_calib_row("all", o, np.ones(len(by), dtype=bool)))
    return out


def _calib_row(label: str, o: dict[str, F64], m: NDArray[np.bool_]) -> dict[str, Any]:
    return {
        "bin": label, "n": int(m.sum()),
        "s_home_share": float(o["s_home"][m].mean()),
        "book_gap_s": float(o["book_gap_s"][m].mean()),
        "proxy_s": float(o["proxy_s"][m].mean()),
        "pred_gd": float(o["pred_gd"][m].mean()),
        "real_gd": float(o["real_gd"][m].mean()),
        "gd_resid": bootstrap_mean(o["real_gd"][m] - o["pred_gd"][m]),
        "gs_resid": bootstrap_mean(o["real_gs"][m] - o["pred_gs"][m]),
        "go_resid": bootstrap_mean(o["real_go"][m] - o["pred_go"][m]),
        "p_s_win": float(o["p_s_win"][m].mean()),
        "win_resid": bootstrap_mean(o["real_s_win"][m] - o["p_s_win"][m]),
        "p_draw": float(o["p_draw"][m].mean()),
        "real_draw": float(o["real_draw"][m].mean()),
    }


# --------------------------------------------------------------------------
# run
# --------------------------------------------------------------------------


def competition_names(db: Path | None, ids: Iterable[int]) -> dict[int, str]:
    names = dict(INTL_COMPS)
    if db is None:
        return names
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        for cid, name in conn.execute(
            "SELECT competition_id, sofascore_tournament FROM sofa_tournament_map "
            "WHERE sport = 'football' ORDER BY events DESC"
        ):
            if int(cid) in set(ids) and int(cid) not in names and name:
                names[int(cid)] = str(name).split(",")[0]
    finally:
        conn.close()
    return names


def ll_diffs(lls: dict[str, F64]) -> dict[str, Any]:
    out: dict[str, Any] = {"A_mean": float(lls["A"].mean()), "n": len(lls["A"])}
    for v in ("B", "C", "D"):
        out[v] = bootstrap_mean(lls[v] - lls["A"])
    return out


def run(args: argparse.Namespace) -> dict[str, Any]:
    r_nb = load_config().nb_r
    note(f"loading {args.history}")
    _fp, history = pickle.loads(Path(args.history).read_bytes())
    note(f"{len(history)} matches; replaying goals_for")
    rep = replay(history, ts_of(args.from_day))
    rows = rep.rows
    note(f"{len(rows)} cross-league cup rows; excluded {rep.excluded}")
    elo, delta = walk_cups(rows, GRID_ETA)
    keys = list(ROW_KEYS) + ["proxy"] + [f"d_{e}" for e in GRID_ETA]
    a_all = arrays(rows, keys)
    a_all["outcome"] = np.asarray(
        [outcome_index(x, y) for x, y in zip(a_all["x"], a_all["y"], strict=True)],
        dtype=np.float64)
    conf = np.asarray([CONFEDERATION[int(c)] for c in a_all["comp"]])
    lbs = STATUSES.index(fr.LINKED_BY_STRENGTH)
    counts: dict[str, Any] = {
        "cross_league_rows": len(rows), "excluded": rep.excluded,
        "with_centre": int(a_all["ok"].sum()),
        "by_status_with_centre": {
            s: int(((a_all["status"] == i) & (a_all["ok"] == 1)).sum())
            for i, s in enumerate(STATUSES)},
        "by_competition": {
            INTL_COMPS[c]: int(((a_all["comp"] == c) & (a_all["ok"] == 1)).sum())
            for c in INTL_COMPS},
        "with_proxy": int(((a_all["ok"] == 1) & np.isfinite(a_all["proxy"])).sum()),
    }

    def sub(mask: NDArray[np.bool_]) -> dict[str, F64]:
        return {k: v[mask] for k, v in a_all.items()}

    ok = a_all["ok"] == 1
    priced = ok & (a_all["status"] == lbs)
    # the variants' arithmetic must reproduce SHEET's centre at A
    chk_h, chk_a = variant_centres(sub(ok), sub(ok)["lf"])
    if not (np.allclose(chk_h, a_all["lh"][ok])
            and np.allclose(chk_a, a_all["la"][ok])):
        raise RuntimeError("re-derived centres differ from FootballForecast.centre")
    test_ts = ts_of(args.test_from)
    res: dict[str, Any] = {
        "params": {"from": args.from_day, "test_from": args.test_from,
                   "nb_r": r_nb, "eta_elo": ETA_ELO, "min_cup_matches": MIN_CUP_MATCHES,
                   "reps": REPS, "cross_ratio_power": fr.CROSS_RATIO_POWER},
        "counts": counts,
        "calibration": {},
        "loglosses": {},
    }
    for scope, mask in (
        ("LINKED_BY_STRENGTH", priced),
        ("LINKED_BY_STRENGTH_UEFA", priced & (conf == "UEFA")),
        ("LINKED_BY_STRENGTH_AFC", priced & (conf == "AFC")),
        ("UNLINKED", ok & (a_all["status"] == STATUSES.index(fr.UNLINKED))),
    ):
        a = sub(mask)
        if len(a["ts"]) == 0:
            continue
        have = np.isfinite(a["proxy"])
        res["calibration"][scope] = {
            "by_proxy": calib_table(
                {k: v[have] for k, v in a.items()}, a["proxy"][have], PROXY_BINS, r_nb),
            "by_book": calib_table(a, a["lf"], BOOK_BINS, r_nb),
        }
    # variants: fit on TRAIN (priced rows before test_from), score on TEST
    train = sub(priced & (a_all["ts"] < test_ts))
    test_mask = priced & (a_all["ts"] >= test_ts)
    best = fit_variants(train, r_nb)
    res["variants"] = best
    for scope, mask in (
        ("test_all", test_mask),
        ("test_UEFA", test_mask & (conf == "UEFA")),
        ("test_AFC", test_mask & (conf == "AFC")),
        ("test_proxy_ge_0.5",
         test_mask & (np.abs(np.nan_to_num(a_all["proxy"])) >= 0.5)),
    ):
        a = sub(mask)
        if len(a["ts"]) == 0:
            continue
        res["loglosses"][scope] = ll_diffs(variant_ll(a, best, r_nb))
    # does D remove the residual? its calibration on TEST, by the proxy
    a = sub(test_mask & np.isfinite(a_all["proxy"]))
    e = best["D"]["eta"]
    lh_d, la_d = variant_centres(a, a["lf"] + a[f"d_{e}"])
    res["calibration_test"] = {
        "A_by_proxy": calib_table(a, a["proxy"], PROXY_BINS, r_nb),
        "D_by_proxy": calib_table({**a, "lh": lh_d, "la": la_d}, a["proxy"],
                                  PROXY_BINS, r_nb),
    }
    # the book, the proxy and D side by side at the end of the history
    d_end = delta[e]
    leagues = sorted(elo.n, key=lambda c: -elo.n[c])[: args.top]
    leagues += [c for pair in CITED_PAIRS for c in pair[:2] if c not in leagues]
    names = competition_names(args.db, leagues)
    book = rep.book
    snap: list[dict[str, Any]] = []
    for c in leagues:
        st = book.strength.get((c, METRIC))
        snap.append({
            "competition": c, "name": names.get(c, str(c)),
            "cup_matches": elo.n[c], "elo": elo.s[c],
            "book_sigma": st.sigma if st else math.nan,
            "book_links": st.n if st else 0,
            "d_end": d_end.get(c, 0.0),
        })
    res["snapshot"] = snap
    by_c = {s["competition"]: s for s in snap}
    res["cited_pairs"] = [
        {"pair": lab, "book_gap": by_c[hc]["book_sigma"] - by_c[ac]["book_sigma"],
         "elo_gap": by_c[hc]["elo"] - by_c[ac]["elo"],
         "elo_n": [by_c[hc]["cup_matches"], by_c[ac]["cup_matches"]],
         "d_gap": by_c[hc]["d_end"] - by_c[ac]["d_end"]}
        for hc, ac, lab in CITED_PAIRS]
    if len(snap) >= 3:
        x = np.asarray([s["elo"] for s in snap])
        y = np.asarray([s["book_sigma"] for s in snap])
        fin = np.isfinite(y)
        res["snapshot_corr"] = float(np.corrcoef(x[fin], y[fin])[0, 1])
    return res


# --------------------------------------------------------------------------
# report
# --------------------------------------------------------------------------


def _ci(t: Sequence[float], fmt: str = "{:+.3f}") -> str:
    return f"{fmt.format(t[0])} [{fmt.format(t[1])}, {fmt.format(t[2])}]"


def markdown(res: dict[str, Any]) -> str:
    lines = ["# cross-league cups (measure_cross_league_cups.py)", ""]
    lines.append(f"params: `{json.dumps(res['params'])}`")
    lines.append(f"counts: `{json.dumps(res['counts'])}`")
    tables = [(f"{scope} - {name}", tab) for scope, tabs in res["calibration"].items()
              for name, tab in tabs.items()]
    tables += [(f"TEST {name}", tab) for name, tab in res["calibration_test"].items()]
    for title, tab in tables:
        lines += ["", f"## {title} (side S = the side the gap favours)", "",
                  "| bin | n | S home | book gap S | Elo gap S | pred GD | real GD | "
                  "real-pred GD | S goals real-pred | opp goals real-pred | "
                  "P(S win) | real-P(S win) | P(X) | real X |",
                  "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for r in tab:
            lines.append(
                f"| {r['bin']} | {r['n']} | {r['s_home_share']:.2f} | "
                f"{r['book_gap_s']:+.3f} | {r['proxy_s']:+.2f} | {r['pred_gd']:+.2f} | "
                f"{r['real_gd']:+.2f} | {_ci(r['gd_resid'])} | {_ci(r['gs_resid'])} | "
                f"{_ci(r['go_resid'])} | {r['p_s_win']:.3f} | {_ci(r['win_resid'])} | "
                f"{r['p_draw']:.3f} | {r['real_draw']:.3f} |")
    lines += ["", f"variants (TRAIN fit): `{json.dumps(res['variants'])}`", "",
              "| scope | n | LL A | B - A | C - A | D - A |",
              "|---|---|---|---|---|---|"]
    for scope, d in res["loglosses"].items():
        lines.append(f"| {scope} | {d['n']} | {d['A_mean']:.4f} | "
                     + " | ".join(_ci(d[v], "{:+.4f}") for v in ("B", "C", "D")) + " |")
    corr = res.get("snapshot_corr", math.nan)
    lines += ["", f"snapshot corr(Elo, book sigma) = {corr:.3f}", "",
              "| league | cup matches | Elo (goals) | book sigma (log) | book links "
              "| D d (log) |",
              "|---|---|---|---|---|---|"]
    for s in res["snapshot"]:
        lines.append(f"| {s['name']} ({s['competition']}) | {s['cup_matches']} | "
                     f"{s['elo']:+.2f} | {s['book_sigma']:+.3f} | {s['book_links']} | "
                     f"{s['d_end']:+.3f} |")
    lines += ["", "| cited pair | book gap (log) | D extra (log) | Elo gap (goals) | "
              "cup matches |", "|---|---|---|---|---|"]
    for c in res["cited_pairs"]:
        lines.append(f"| {c['pair']} | {c['book_gap']:+.3f} | {c['d_gap']:+.3f} | "
                     f"{c['elo_gap']:+.2f} | {c['elo_n']} |")
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0] if __doc__ else None)
    p.add_argument("--history", default=str(DEFAULT_HISTORY))
    p.add_argument("--db", type=Path, default=None,
                   help="read-only, for competition names only")
    p.add_argument("--from", dest="from_day", default=FROM_DAY)
    p.add_argument("--test-from", default=TEST_FROM)
    p.add_argument("--top", type=int, default=40)
    p.add_argument("--json-out", type=Path, default=None)
    p.add_argument("--md-out", type=Path, default=None)
    args = p.parse_args(argv)
    res = run(args)
    md = markdown(res)
    if args.json_out:
        args.json_out.write_text(json.dumps(res, indent=1, default=float))
    if args.md_out:
        args.md_out.write_text(md)
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
